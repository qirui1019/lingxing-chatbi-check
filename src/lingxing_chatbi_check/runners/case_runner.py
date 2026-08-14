from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from lingxing_chatbi_check.cases.models import CaseSpec
from lingxing_chatbi_check.cleaners.base import CleanerContext
from lingxing_chatbi_check.cleaners.registry import cleaner_registry
from lingxing_chatbi_check.clients.doris_mysql import DorisMysqlClient
from lingxing_chatbi_check.clients.lingxing_mcp import LingxingMcpClient
from lingxing_chatbi_check.comparators.dataframe_compare import compare_dataframes
from lingxing_chatbi_check.config import get_mcp_user_config
from lingxing_chatbi_check.reports.excel_report import write_excel_report
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


def run_case(case: CaseSpec, env_config: dict[str, Any], output_dir: Path) -> Path:
    return asyncio.run(run_case_async(case, env_config, output_dir))


async def run_case_async(
    case: CaseSpec,
    env_config: dict[str, Any],
    output_dir: Path,
) -> Path:
    mcp_config = env_config["lingxing_mcp"]
    db_client = DorisMysqlClient.from_config(env_config["doris_mysql"])

    if case.auth.mode == "all_users":
        raw_tool_output, scoped_shops = await _call_tool_for_all_users(
            case,
            env_config,
            output_dir,
        )
        db_params = dict(case.database.params)
        db_params[
            database_scope_param(case.tool.dynamic_arguments)
        ] = values_for_database_scope(scoped_shops, case.tool.dynamic_arguments)
        db_output = db_client.query(case.database.sql, db_params)
        user_key_context = "all_users"
    else:
        mcp_client = _client_for_user(env_config, case.auth.user_key)
        raw_tool_output = await mcp_client.call_tool(
            case.tool.name,
            case.tool.arguments,
        )
        db_output = db_client.query(case.database.sql, case.database.params)
        scoped_shops = []
        user_key_context = case.auth.user_key

    context = CleanerContext(tool_name=case.tool.name, table_name=case.database.table)
    cleaner = cleaner_registry.get(f"{case.tool.name}__{case.database.table}")
    tool_df = cleaner.clean(raw_tool_output, context)
    db_df = cleaner.clean(db_output, context)

    result = compare_dataframes(
        tool_df=tool_df,
        db_df=db_df,
        dimensions=case.compare.dimensions,
        metrics=case.compare.metrics,
        dimension_mappings=case.compare.dimension_mappings,
        metric_mappings=case.compare.metric_mappings,
        tolerance=case.compare.tolerance,
    )

    report_name = _safe_filename(f"{case.tool.name}__{case.database.table}.xlsx")
    return write_excel_report(
        output_dir / report_name,
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
        },
    )


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def _format_mapping(mapping: dict[str, str]) -> str:
    return "\n".join(f"{tool_field} -> {db_field}" for tool_field, db_field in mapping.items())


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
    for user_key, shops in _group_shops_by_user(scoped_shops).items():
        client = _client_for_user(env_config, user_key)
        for arguments in build_tool_argument_batches(
            base_arguments=case.tool.arguments,
            dynamic_arguments=case.tool.dynamic_arguments,
            shops=shops,
        ):
            outputs.append(await client.call_tool(case.tool.name, arguments))
    return _flatten_tool_outputs(outputs), scoped_shops


def _client_for_user(
    env_config: dict[str, Any],
    user_key: str,
) -> LingxingMcpClient:
    mcp_config = env_config["lingxing_mcp"]
    mcp_user = get_mcp_user_config(env_config, user_key)
    return LingxingMcpClient(
        url=str(mcp_config["url"]),
        x_mcp_key=mcp_user["x_mcp_key"],
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
        if isinstance(output, list):
            flattened.extend(output)
            continue
        if isinstance(output, dict):
            nested = None
            for key in ("data", "rows", "list", "items", "records"):
                value = output.get(key)
                if isinstance(value, list):
                    nested = value
                    break
            if nested is not None:
                flattened.extend(nested)
            else:
                flattened.append(output)
            continue
        flattened.append(output)
    return flattened
