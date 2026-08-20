from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime
import json
import re
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd

from lingxing_chatbi_check.cases.models import CaseSpec
from lingxing_chatbi_check.cleaners.base import CleanerContext
from lingxing_chatbi_check.cleaners.registry import cleaner_registry
from lingxing_chatbi_check.clients.doris_mysql import DorisMysqlClient
from lingxing_chatbi_check.clients.lingxing_mcp import LingxingMcpClient
from lingxing_chatbi_check.comparators.dataframe_compare import compare_dataframes
from lingxing_chatbi_check.config import get_mcp_user_config
from lingxing_chatbi_check.reports.excel_report import (
    MetricReportWriteResult,
    write_metric_report_files,
)
from lingxing_chatbi_check.scopes.argument_builder import (
    build_tool_argument_batches,
    database_scope_param,
    values_for_database_scope,
)
from lingxing_chatbi_check.scopes.shop_discovery import (
    AuthorizedShop,
    dedupe_authorized_shops,
    discover_authorized_shops,
)

DEFAULT_TOOL_BATCH_TIMEOUT_SECONDS = 300


def run_case(
    case: CaseSpec,
    env_config: dict[str, Any],
    output_dir: Path,
) -> MetricReportWriteResult:
    return asyncio.run(run_case_async(case, env_config, output_dir))


async def run_case_async(
    case: CaseSpec,
    env_config: dict[str, Any],
    output_dir: Path,
) -> MetricReportWriteResult:
    mcp_config = env_config["lingxing_mcp"]
    db_client = DorisMysqlClient.from_config(env_config["doris_mysql"])
    total_query_started_at = perf_counter()

    if case.auth.mode == "all_users":
        tool_query_started_at = perf_counter()
        raw_tool_output, scoped_shops = await _call_tool_for_all_users(
            case,
            env_config,
            output_dir,
        )
        tool_query_seconds = _elapsed_seconds(tool_query_started_at)
        db_params = dict(case.database.params)
        db_params[
            database_scope_param(case.tool.dynamic_arguments)
        ] = values_for_database_scope(scoped_shops, case.tool.dynamic_arguments)
        db_query_started_at = perf_counter()
        db_output = db_client.query(case.database.sql, db_params)
        db_query_seconds = _elapsed_seconds(db_query_started_at)
        user_key_context = "all_users"
    else:
        tool_query_started_at = perf_counter()
        async with _client_for_user(env_config, case.auth.user_key) as mcp_client:
            raw_tool_output = await mcp_client.call_tool(
                case.tool.name,
                case.tool.arguments,
            )
        tool_query_seconds = _elapsed_seconds(tool_query_started_at)
        db_query_started_at = perf_counter()
        db_output = db_client.query(case.database.sql, case.database.params)
        db_query_seconds = _elapsed_seconds(db_query_started_at)
        scoped_shops = []
        user_key_context = case.auth.user_key
    total_query_seconds = _elapsed_seconds(total_query_started_at)

    context = CleanerContext(tool_name=case.tool.name, table_name=case.database.table)
    cleaner = cleaner_registry.get(f"{case.tool.name}__{case.database.table}")
    tool_df = cleaner.clean(raw_tool_output, context)
    db_df = cleaner.clean(db_output, context)
    db_df = _filter_db_to_tool_scope(case=case, tool_df=tool_df, db_df=db_df)
    _log_tool_clean_summary(
        case=case,
        raw_tool_output=raw_tool_output,
        tool_df=tool_df,
        db_df=db_df,
    )
    tool_df, db_df = _add_missing_constant_compare_dimensions(
        tool_df=tool_df,
        db_df=db_df,
        case=case,
    )

    result = compare_dataframes(
        tool_df=tool_df,
        db_df=db_df,
        dimensions=case.compare.dimensions,
        metrics=case.compare.metrics,
        dimension_mappings=case.compare.dimension_mappings,
        metric_mappings=case.compare.metric_mappings,
        metric_dimension_mappings=case.compare.metric_dimension_mappings,
        tolerance=case.compare.tolerance,
    )

    return write_metric_report_files(
        output_dir,
        result,
        context={
            "case_name": case.name,
            "tool_name": case.tool.name,
            "table_name": case.database.table,
            "auth_mode": case.auth.mode,
            "user_key": user_key_context,
            "shop_count": len(scoped_shops),
            "dimensions": ", ".join(case.compare.dimensions),
            "metrics": ", ".join(case.compare.metrics),
            "dimension_mappings": _format_mapping(case.compare.dimension_mappings),
            "metric_mappings": _format_mapping(case.compare.metric_mappings),
            "period_label": _period_label_for_case(case),
            "tool_query_seconds": tool_query_seconds,
            "db_query_seconds": db_query_seconds,
            "total_query_seconds": total_query_seconds,
        },
    )


def _elapsed_seconds(started_at: float) -> float:
    return round(perf_counter() - started_at, 3)


def _log_tool_clean_summary(
    *,
    case: CaseSpec,
    raw_tool_output: Any,
    tool_df: pd.DataFrame,
    db_df: pd.DataFrame,
) -> None:
    raw_records = _extract_record_list(raw_tool_output)
    metric_counts = {
        tool_field: int(tool_df[tool_field].notna().sum())
        for tool_field in case.compare.metric_mappings
        if tool_field in tool_df.columns
    }
    print(
        f"tool_clean_summary case={case.name!r} "
        f"raw_tool_rows={len(raw_records) if raw_records is not None else 0} "
        f"clean_tool_rows={len(tool_df)} "
        f"db_rows={len(db_df)} "
        f"dimensions={case.compare.dimensions!r} "
        f"tool_metric_non_null={metric_counts}"
    )


def _filter_db_to_tool_scope(
    *,
    case: CaseSpec,
    tool_df: pd.DataFrame,
    db_df: pd.DataFrame,
) -> pd.DataFrame:
    if _uses_tool_sid_asin_scope(case):
        return _filter_db_to_tool_sid_item_scope(
            case=case,
            tool_df=tool_df,
            db_df=db_df,
            item_dimension="asin",
        )
    if _uses_tool_sid_msku_scope(case):
        return _filter_db_to_tool_sid_item_scope(
            case=case,
            tool_df=tool_df,
            db_df=db_df,
            item_dimension="msku",
        )
    if _uses_ad_tool_sid_scope(case):
        return _filter_db_to_tool_sid_scope(
            case=case,
            tool_df=tool_df,
            db_df=db_df,
        )
    return db_df


def _filter_db_to_tool_sid_item_scope(
    *,
    case: CaseSpec,
    tool_df: pd.DataFrame,
    db_df: pd.DataFrame,
    item_dimension: str,
) -> pd.DataFrame:
    if tool_df.empty or db_df.empty:
        return db_df.iloc[0:0].copy()

    dimension_pairs = _dimension_pairs_for_case(case)
    tool_sid, db_sid = _scope_dimension_pair(dimension_pairs, "sid")
    tool_item, db_item = _scope_dimension_pair(dimension_pairs, item_dimension)
    required_tool_columns = [tool_sid, tool_item]
    required_db_columns = [db_sid, db_item]
    if any(column not in tool_df.columns for column in required_tool_columns):
        return db_df.iloc[0:0].copy()
    if any(column not in db_df.columns for column in required_db_columns):
        return db_df.iloc[0:0].copy()

    tool_keys = set(
        _scope_keys(tool_df, sid_column=tool_sid, item_column=tool_item)
    )
    if not tool_keys:
        return db_df.iloc[0:0].copy()

    db_keys = _scope_keys(db_df, sid_column=db_sid, item_column=db_item)
    mask = [key in tool_keys for key in db_keys]
    return db_df.loc[mask].reset_index(drop=True)


def _filter_db_to_tool_sid_scope(
    *,
    case: CaseSpec,
    tool_df: pd.DataFrame,
    db_df: pd.DataFrame,
) -> pd.DataFrame:
    if tool_df.empty or db_df.empty:
        return db_df.iloc[0:0].copy()

    dimension_pairs = _dimension_pairs_for_case(case)
    tool_sid, db_sid = _scope_dimension_pair(dimension_pairs, "sid")
    if tool_sid not in tool_df.columns or db_sid not in db_df.columns:
        return db_df.iloc[0:0].copy()

    tool_sids = set(_scope_values(tool_df[tool_sid]))
    if not tool_sids:
        return db_df.iloc[0:0].copy()

    db_sids = _scope_values(db_df[db_sid])
    mask = [sid in tool_sids for sid in db_sids]
    return db_df.loc[mask].reset_index(drop=True)


def _uses_tool_sid_asin_scope(case: CaseSpec) -> bool:
    return (
        case.tool.name == "query_product_performance_asin_lists"
        and "sid" in case.compare.dimensions
        and "asin" in case.compare.dimensions
    )


def _uses_tool_sid_msku_scope(case: CaseSpec) -> bool:
    return (
        case.tool.name == "get_profit_report_msku"
        and "sid" in case.compare.dimensions
        and "msku" in case.compare.dimensions
    )


def _uses_ad_tool_sid_scope(case: CaseSpec) -> bool:
    return (
        case.tool.name
        in {
            "ad_campaign_keyword_report",
            "ad_campaign_targeting_report",
            "ad_campaign_search_term_report",
        }
        and "sid" in case.compare.dimensions
    )


def _listing_key_field_for_case(case: CaseSpec) -> str | None:
    if not case.scope.listing_mapping:
        return None
    if _uses_tool_sid_asin_scope(case):
        return "asin"
    if _uses_tool_sid_msku_scope(case):
        return "msku"
    return None


async def _listing_scope_keys_for_arguments(
    *,
    client: Any,
    listing_tool: str,
    arguments: dict[str, Any],
    dynamic_arguments: Any,
    shops: list[AuthorizedShop],
    cache_dir: Path,
    listing_scope_cache: dict[str, set[tuple[str, str]]],
    key_field: str,
) -> set[tuple[str, str]]:
    sid_values = _argument_values(arguments.get(dynamic_arguments.shop_argument))
    if not sid_values:
        sid_values = values_for_database_scope(shops, dynamic_arguments)
    keys: set[tuple[str, str]] = set()
    for sid in sid_values:
        normalized_sid = _normalize_scope_value(sid)
        if not normalized_sid:
            continue
        cache_key = f"{listing_tool}:{normalized_sid}:{key_field}"
        if cache_key not in listing_scope_cache:
            listing_scope_cache[cache_key] = await _load_listing_scope_keys(
                client=client,
                listing_tool=listing_tool,
                sid=normalized_sid,
                cache_dir=cache_dir,
                key_field=key_field,
            )
        keys.update(listing_scope_cache[cache_key])
    return keys


async def _load_listing_scope_keys(
    *,
    client: Any,
    listing_tool: str,
    sid: str,
    cache_dir: Path,
    key_field: str = "asin",
    page_size: int = 1000,
    max_pages: int = 1000,
) -> set[tuple[str, str]]:
    cache_suffix = "" if key_field == "asin" else f"_{key_field}"
    cache_path = (
        cache_dir
        / f"{_safe_filename(listing_tool)}_{_safe_filename(sid)}{cache_suffix}.json"
    )
    if cache_path.exists():
        output = json.loads(cache_path.read_text(encoding="utf-8"))
        if _listing_output_is_complete(output):
            return _listing_scope_keys(output, default_sid=sid, key_field=key_field)
    else:
        output = None

    output = await _call_listing_mapping_tool(
        client=client,
        listing_tool=listing_tool,
        sid=sid,
        page_size=page_size,
        max_pages=max_pages,
    )
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except TypeError:
        pass
    return _listing_scope_keys(output, default_sid=sid, key_field=key_field)


async def _call_listing_mapping_tool(
    *,
    client: Any,
    listing_tool: str,
    sid: str,
    page_size: int,
    max_pages: int,
) -> Any:
    records: list[Any] = []
    last_page: int | None = None
    last_returned = 0
    for page_offset in range(max_pages):
        offset = page_offset * page_size
        arguments = {"sid": sid, "offset": offset, "length": page_size}
        output = await _call_tool_with_retries(client, listing_tool, arguments)
        page_records = _extract_record_list(output) or []
        total = _extract_total_count(output)
        last_page = offset
        last_returned = len(page_records)
        if not page_records:
            break

        records.extend(page_records)
        if total is not None and len(records) >= total:
            break
        if len(page_records) < page_size:
            break
    else:
        _log_pagination_max_pages_reached(
            tool_name=listing_tool,
            arguments={"sid": sid},
            max_pages=max_pages,
            page_size=page_size,
            last_page=last_page,
            last_returned=last_returned,
            total=len(records),
        )
    return records


def _listing_output_is_complete(output: Any) -> bool:
    records = _extract_record_list(output) or []
    total = _extract_total_count(output)
    return total is None or len(records) >= total


def _listing_scope_keys(
    output: Any,
    *,
    default_sid: str,
    key_field: str = "asin",
) -> set[tuple[str, str]]:
    records = _extract_record_list(output) or []
    keys: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        sid = _normalize_scope_value(
            _first_record_value(record, ["sid", "s_id", "store_id"]) or default_sid
        )
        item = _normalize_scope_value(_first_record_value(record, _listing_key_names(key_field)))
        if sid and item and item != "-":
            keys.add((sid, item))
    return keys


def _filter_sales_records_to_listing_scope(
    records: list[Any],
    listing_keys: set[tuple[str, str]],
    key_field: str = "asin",
) -> list[Any]:
    filtered: list[Any] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        key = _sales_record_scope_key(record, key_field=key_field)
        if key is not None and key in listing_keys:
            filtered.append(record)
    return filtered


def _sales_record_scope_key(
    record: dict[str, Any],
    *,
    key_field: str = "asin",
) -> tuple[str, str] | None:
    sid = _normalize_scope_value(_first_record_value(record, ["sid", "store_id"]))
    item = _normalize_scope_value(_first_record_value(record, _listing_key_names(key_field)))
    if not sid:
        sid = _single_nested_sid_for_record(record)
    if not sid or not item or item == "-":
        return None
    return sid, item


def _listing_key_names(key_field: str) -> list[str]:
    if key_field == "msku":
        return ["msku", "seller_sku", "sellerSku", "local_sku", "localSku"]
    return ["asin", "amz_product_id"]


def _single_nested_sid_for_record(record: dict[str, Any]) -> str | None:
    values = _argument_values(record.get("sids"))
    if len(values) == 1:
        return _normalize_scope_value(values[0])
    return None


def _first_record_value(record: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalize_scope_value(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _scope_dimension_pair(
    dimension_pairs: list[tuple[str, str]],
    dimension: str,
) -> tuple[str, str]:
    for tool_field, db_field in dimension_pairs:
        if tool_field == dimension or db_field == dimension:
            return tool_field, db_field
    return dimension, dimension


def _scope_keys(
    frame: pd.DataFrame,
    *,
    sid_column: str,
    item_column: str,
) -> list[tuple[str, str]]:
    sid_values = frame[sid_column].astype("string").str.strip()
    item_values = frame[item_column].astype("string").str.strip()
    keys: list[tuple[str, str]] = []
    for sid, item in zip(sid_values, item_values):
        if pd.isna(sid) or pd.isna(item) or sid == "" or item == "":
            continue
        keys.append((str(sid), str(item)))
    return keys


def _scope_values(values: pd.Series) -> list[str]:
    normalized = values.astype("string").str.strip()
    result: list[str] = []
    for value in normalized:
        if pd.isna(value) or value == "":
            continue
        result.append(str(value))
    return result


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def _format_mapping(mapping: dict[str, str]) -> str:
    return "\n".join(f"{tool_field} -> {db_field}" for tool_field, db_field in mapping.items())


def _period_label_for_case(case: CaseSpec) -> str:
    start_date, end_date = _date_range_for_case(case)
    if start_date is None:
        return "unknown_period"
    if end_date is None:
        end_date = start_date
    start_label = f"{start_date.year}年{start_date.month}月"
    end_label = f"{end_date.year}年{end_date.month}月"
    if start_label == end_label:
        return start_label
    return f"{start_label}-{end_label}"


def _date_range_for_case(case: CaseSpec) -> tuple[datetime | None, datetime | None]:
    arguments = case.tool.arguments
    params = case.database.params
    start = _first_present_value(
        params,
        arguments,
        keys=["report_start_date", "start_date", "startDate", "settlement_start_date"],
    )
    end = _first_present_value(
        params,
        arguments,
        keys=["report_end_date", "end_date", "endDate", "settlement_end_date"],
    )
    if start is not None:
        return _parse_date(start), _parse_date(end)

    report_date = _first_present_value(params, arguments, keys=["report_date"])
    if report_date is None:
        return None, None
    dates = [_parse_date(value) for value in re.findall(r"\d{4}-\d{2}-\d{2}", str(report_date))]
    dates = [value for value in dates if value is not None]
    if not dates:
        return None, None
    if len(dates) == 1:
        return dates[0], dates[0]
    return dates[0], dates[1]


def _first_present_value(
    *mappings: dict[str, Any],
    keys: list[str],
) -> Any:
    for key in keys:
        for mapping in mappings:
            value = mapping.get(key)
            if value not in (None, ""):
                return value
    return None


def _parse_date(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d")
    except ValueError:
        return None


def _add_missing_constant_compare_dimensions(
    *,
    tool_df: pd.DataFrame,
    db_df: pd.DataFrame,
    case: CaseSpec,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    dimension_pairs = _dimension_pairs_for_case(case)
    tool_result = tool_df.copy()
    db_result = db_df.copy()
    for tool_field, db_field in dimension_pairs:
        value = _constant_compare_value(tool_field, case)
        if value is not None and tool_field not in tool_result.columns:
            tool_result[tool_field] = value
        value = _constant_compare_value(db_field, case)
        if value is not None and db_field not in db_result.columns:
            db_result[db_field] = value
    return tool_result, db_result


def _dimension_pairs_for_case(case: CaseSpec) -> list[tuple[str, str]]:
    if case.compare.dimension_mappings:
        return [
            (str(tool_field), str(db_field))
            for tool_field, db_field in case.compare.dimension_mappings.items()
        ]
    return [(dimension, dimension) for dimension in case.compare.dimensions]


def _constant_compare_value(field: str, case: CaseSpec) -> Any:
    arguments = case.tool.arguments
    params = case.database.params
    if field in arguments:
        return arguments[field]
    if field in params:
        return params[field]
    if field in {"date", "report_date"}:
        if "report_date" in arguments:
            return arguments["report_date"]
        if "report_date" in params:
            return params["report_date"]
        start_date = arguments.get("start_date", params.get("start_date"))
        end_date = arguments.get("end_date", params.get("end_date"))
        if start_date is not None and end_date is not None:
            return f"{start_date} - {end_date}"
    return None


async def _call_tool_for_all_users(
    case: CaseSpec,
    env_config: dict[str, Any],
    output_dir: Path,
) -> tuple[list[Any], list[AuthorizedShop]]:
    if not case.scope.shop_discovery:
        raise ValueError(f"Case must define scope.shop_discovery: {case.name}")

    scoped_shops = await discover_authorized_shops(
        env_config,
        discovery_tool=case.scope.shop_discovery,
        cache_path=output_dir / "_runtime" / f"{case.scope.shop_discovery}.json",
    )
    outputs: list[Any] = []
    listing_scope_cache: dict[str, set[tuple[str, str]]] = {}
    for user_key, shops in _group_shops_by_user(scoped_shops).items():
        async with _client_for_user(env_config, user_key) as client:
            for arguments in build_tool_argument_batches(
                base_arguments=case.tool.arguments,
                dynamic_arguments=case.tool.dynamic_arguments,
                shops=shops,
            ):
                output = await _call_tool_batch_with_timeout(
                    client=client,
                    tool_name=case.tool.name,
                    arguments=arguments,
                    pagination=case.tool.pagination,
                )
                if output is None:
                    continue
                outputs.append(
                    await _filter_tool_output_with_listing_scope(
                        case=case,
                        client=client,
                        output=output,
                        shops=shops,
                        arguments=arguments,
                        cache_dir=output_dir / "_runtime" / "listing_mapping",
                        listing_scope_cache=listing_scope_cache,
                    )
                )
    return _flatten_tool_outputs(outputs), scoped_shops


async def _call_tool_batch_with_timeout(
    *,
    client: Any,
    tool_name: str,
    arguments: dict[str, Any],
    pagination: Any,
) -> Any | None:
    call = _call_tool_with_optional_pagination(
        client=client,
        tool_name=tool_name,
        arguments=arguments,
        pagination=pagination,
    )
    timeout_seconds = getattr(
        pagination,
        "batch_timeout_seconds",
        DEFAULT_TOOL_BATCH_TIMEOUT_SECONDS,
    )
    if timeout_seconds is None:
        return await call

    try:
        return await asyncio.wait_for(call, timeout=timeout_seconds)
    except TimeoutError:
        reset_session = getattr(client, "reset_session", None)
        if reset_session is not None:
            await reset_session()
        _log_tool_batch_timeout(
            tool_name=tool_name,
            arguments=arguments,
            timeout_seconds=timeout_seconds,
        )
        return None


async def _filter_tool_output_with_listing_scope(
    *,
    case: CaseSpec,
    client: Any,
    output: Any,
    shops: list[AuthorizedShop],
    arguments: dict[str, Any],
    cache_dir: Path,
    listing_scope_cache: dict[str, set[tuple[str, str]]],
) -> list[Any]:
    annotated = _annotate_tool_output_with_shop_scope(
        output=output,
        dynamic_arguments=case.tool.dynamic_arguments,
        shops=shops,
        arguments=arguments,
    )
    records = _flatten_tool_outputs([annotated])
    key_field = _listing_key_field_for_case(case)
    if key_field is None:
        return records

    listing_keys = await _listing_scope_keys_for_arguments(
        client=client,
        listing_tool=str(case.scope.listing_mapping),
        arguments=arguments,
        dynamic_arguments=case.tool.dynamic_arguments,
        shops=shops,
        cache_dir=cache_dir,
        listing_scope_cache=listing_scope_cache,
        key_field=key_field,
    )
    return _filter_sales_records_to_listing_scope(
        records,
        listing_keys,
        key_field=key_field,
    )


async def _call_tool_with_optional_pagination(
    *,
    client: Any,
    tool_name: str,
    arguments: dict[str, Any],
    pagination: Any,
) -> Any:
    if pagination is None or not pagination.enabled:
        started_at = perf_counter()
        output = await _call_tool_with_retries(client, tool_name, arguments)
        records = _extract_record_list(output)
        _log_pagination_summary(
            tool_name=tool_name,
            arguments=arguments,
            pages=1,
            records=len(records) if records is not None else 1,
            total=_extract_total_count(output),
            seconds=_elapsed_seconds(started_at),
            max_pages_reached=False,
        )
        return output

    started_at = perf_counter()
    records: list[Any] = []
    last_page: int | None = None
    last_returned = 0
    last_total: int | None = None
    pages_requested = 0
    for page_offset in range(pagination.max_pages):
        page = _pagination_page_value(pagination, page_offset)
        page_arguments = {
            **arguments,
            pagination.page_argument: page,
            pagination.page_size_argument: pagination.page_size,
        }
        output = await _call_tool_with_retries(client, tool_name, page_arguments)
        pages_requested += 1
        page_records = _extract_record_list(output) or []
        total = _extract_total_count(output)
        last_total = total
        last_page = page
        last_returned = len(page_records)
        if not page_records:
            break

        records.extend(page_records)
        if total is not None and len(records) >= total:
            break
        if len(page_records) < pagination.page_size:
            break
    else:
        _log_pagination_max_pages_reached(
            tool_name=tool_name,
            arguments=arguments,
            max_pages=pagination.max_pages,
            page_size=pagination.page_size,
            last_page=last_page,
            last_returned=last_returned,
            total=len(records),
        )
    _log_pagination_summary(
        tool_name=tool_name,
        arguments=arguments,
        pages=pages_requested,
        records=len(records),
        total=last_total,
        seconds=_elapsed_seconds(started_at),
        max_pages_reached=pages_requested >= pagination.max_pages
        and last_returned >= pagination.page_size,
    )
    return records


def _pagination_page_value(pagination: Any, page_offset: int) -> int:
    if getattr(pagination, "page_value_mode", "page") == "offset":
        return pagination.page_start + page_offset * pagination.page_size
    return pagination.page_start + page_offset


def _log_pagination_max_pages_reached(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    max_pages: int,
    page_size: int,
    last_page: int | None,
    last_returned: int,
    total: int,
) -> None:
    print(
        f"pagination_warning tool={tool_name} "
        f"args={_format_pagination_arguments(arguments)} "
        f"reason=max_pages_reached max_pages={max_pages} page_size={page_size} "
        f"last_page={last_page} last_returned={last_returned} total={total}",
        flush=True,
    )


def _log_pagination_summary(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    pages: int,
    records: int,
    total: int | None,
    seconds: float,
    max_pages_reached: bool,
) -> None:
    print(
        f"pagination_summary tool={tool_name} "
        f"args={_format_pagination_arguments(arguments)} "
        f"pages={pages} records={records} total={total} "
        f"seconds={seconds} max_pages_reached={max_pages_reached}",
        flush=True,
    )


def _log_tool_batch_timeout(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    timeout_seconds: float,
) -> None:
    print(
        f"tool_batch_timeout tool={tool_name} "
        f"args={_format_pagination_arguments(arguments)} "
        f"timeout_seconds={timeout_seconds:g} action=skip",
        flush=True,
    )


def _format_pagination_arguments(arguments: dict[str, Any]) -> str:
    parts = [
        f"{key}={_format_pagination_value(value)}"
        for key, value in arguments.items()
    ]
    return ", ".join(parts)


def _format_pagination_value(value: Any) -> str:
    if isinstance(value, list):
        if len(value) <= 5:
            return repr(value)
        preview = ", ".join(repr(item) for item in value[:5])
        return f"[{preview}, ...]({len(value)})"
    return repr(value)


async def _call_tool_with_retries(
    client: Any,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    max_attempts: int = 3,
    retry_delay_seconds: float = 0.5,
) -> Any:
    last_error: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return await client.call_tool(tool_name, arguments)
        except BaseException as exc:
            if not _is_transient_mcp_error(exc) or attempt == max_attempts - 1:
                raise
            last_error = exc
            await asyncio.sleep(retry_delay_seconds * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise RuntimeError("MCP tool call retry loop exited without a result")


def _is_transient_mcp_error(exc: BaseException) -> bool:
    if isinstance(exc, BaseExceptionGroup):
        return any(_is_transient_mcp_error(error) for error in exc.exceptions)

    current: BaseException | None = exc
    while current is not None:
        name = type(current).__name__
        message = str(current)
        if name in {
            "RemoteProtocolError",
            "ReadTimeout",
            "ConnectTimeout",
            "ConnectError",
            "TimeoutException",
            "NetworkError",
        }:
            return True
        if "Server disconnected without sending a response" in message:
            return True
        if "getaddrinfo failed" in message:
            return True
        if name == "CancelledError" and "Cancelled via cancel scope" in message:
            return True
        current = current.__cause__ or current.__context__
    return False


def _client_for_user(
    env_config: dict[str, Any],
    user_key: str,
) -> LingxingMcpClient:
    mcp_config = env_config["lingxing_mcp"]
    mcp_user = get_mcp_user_config(env_config, user_key)
    return LingxingMcpClient(
        url=str(mcp_config["url"]),
        x_mcp_key=mcp_user["x_mcp_key"],
        timeout_seconds=float(mcp_config.get("timeout_seconds", 120)),
    )


def _group_shops_by_user(
    shops: list[AuthorizedShop],
) -> dict[str, list[AuthorizedShop]]:
    groups: dict[str, list[AuthorizedShop]] = {}
    for shop in dedupe_authorized_shops(shops):
        groups.setdefault(shop.source_user_key, []).append(shop)
    return groups


def _flatten_tool_outputs(outputs: list[Any]) -> list[Any]:
    flattened: list[Any] = []
    for output in outputs:
        records = _extract_record_list(output)
        if records is not None:
            flattened.extend(records)
            continue
        if isinstance(output, dict):
            flattened.append(output)
            continue
        flattened.append(output)
    return flattened


def _extract_record_list(output: Any) -> list[Any] | None:
    if isinstance(output, list):
        return output
    if isinstance(output, dict):
        for key in ("data", "rows", "list", "items", "records"):
            value = output.get(key)
            if isinstance(value, list):
                return value
            nested = _extract_record_list(value)
            if nested is not None:
                return nested
    return None


def _extract_total_count(output: Any) -> int | None:
    if not isinstance(output, dict):
        return None

    total = _extract_local_total_count(output)
    for key in ("data", "rows", "list", "items", "records"):
        value = output.get(key)
        if isinstance(value, list) and total is not None:
            return total
        nested_total = _extract_total_count(value)
        if nested_total is not None:
            return nested_total
    return total


def _extract_local_total_count(output: dict[str, Any]) -> int | None:
    for key in ("recordsFiltered", "total", "recordsTotal"):
        total = _coerce_int(output.get(key))
        if total is not None and total > 0:
            return total
    return None


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _annotate_tool_output_with_shop_scope(
    *,
    output: Any,
    dynamic_arguments: Any,
    shops: list[AuthorizedShop],
    arguments: dict[str, Any],
) -> Any:
    if dynamic_arguments is None:
        return output

    source_field = dynamic_arguments.source_field
    database_source_field = dynamic_arguments.database_source_field or source_field
    if not source_field:
        return output

    shops_by_source = {
        str(value): shop
        for shop in shops
        if (value := shop.value_for(source_field)) not in (None, "")
    }
    scoped_argument_values = [
        str(value)
        for value in _argument_values(arguments.get(dynamic_arguments.shop_argument))
    ]
    active_shops = [
        shops_by_source[value]
        for value in scoped_argument_values
        if value in shops_by_source
    ]
    default_shop = active_shops[0] if len(active_shops) == 1 else None

    annotated = deepcopy(output)
    for record in _iter_dict_records(annotated):
        shop = _shop_for_record(record, source_field, shops_by_source, default_shop)
        if shop is None:
            continue
        for field in dict.fromkeys([source_field, database_source_field]):
            value = shop.value_for(field)
            if value not in (None, "") and record.get(field) in (None, ""):
                record[field] = value
    return annotated


def _argument_values(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    if isinstance(value, str) and "," in value:
        return [part.strip() for part in value.split(",") if part.strip()]
    return [value]


def _shop_for_record(
    record: dict[str, Any],
    source_field: str,
    shops_by_source: dict[str, AuthorizedShop],
    default_shop: AuthorizedShop | None,
) -> AuthorizedShop | None:
    record_source = record.get(source_field)
    if record_source not in (None, ""):
        return shops_by_source.get(str(record_source), default_shop)
    return default_shop


def _iter_dict_records(value: Any):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _iter_dict_records(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_dict_records(item)
