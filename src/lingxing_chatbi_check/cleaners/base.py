from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd


@dataclass(frozen=True)
class CleanerContext:
    tool_name: str
    table_name: str


class Cleaner(Protocol):
    def clean(self, data: Any, context: CleanerContext) -> pd.DataFrame:
        ...


class JsonNormalizeCleaner:
    def clean(self, data: Any, context: CleanerContext) -> pd.DataFrame:
        if isinstance(data, pd.DataFrame):
            return _apply_tool_specific_cleanups(data.copy(), context)
        if isinstance(data, list):
            return _apply_tool_specific_cleanups(pd.json_normalize(data), context)
        if isinstance(data, dict):
            for key in ("data", "rows", "list", "items", "records"):
                value = data.get(key)
                if isinstance(value, list):
                    return _apply_tool_specific_cleanups(
                        pd.json_normalize(value),
                        context,
                    )
            return _apply_tool_specific_cleanups(pd.json_normalize(data), context)
        raise ValueError(
            f"Cannot normalize data for tool={context.tool_name}, table={context.table_name}"
        )


def _apply_tool_specific_cleanups(
    df: pd.DataFrame,
    context: CleanerContext,
) -> pd.DataFrame:
    ad_tools = {
        "ad_campaign_keyword_report",
        "ad_campaign_targeting_report",
        "ad_campaign_search_term_report",
    }
    if context.tool_name in ad_tools:
        if "sponsored_type" in df.columns:
            df = df.loc[
                df["sponsored_type"].astype("string").str.lower().str.strip() == "sp"
            ].reset_index(drop=True)

    if (
        context.tool_name == "ad_campaign_search_term_report"
        and "keyword_id" in df.columns
        and "target_id" in df.columns
    ):
        df["target_id"] = df["target_id"].where(
            df["target_id"].notna() & (df["target_id"] != ""),
            df["keyword_id"],
        )

    if context.tool_name in ad_tools and "profile_id" in df.columns:
        profile_id = df["profile_id"].astype("string").str.strip()
        df = df.loc[profile_id.notna() & profile_id.ne("")].reset_index(drop=True)

    if context.tool_name == "query_product_performance_asin_lists":
        df = _cleanup_sales_product_performance_rows(df)
    if context.tool_name == "get_profit_report_msku":
        df = _cleanup_profit_report_msku_rows(df)

    return df


def _cleanup_sales_product_performance_rows(df: pd.DataFrame) -> pd.DataFrame:
    if "asin" not in df.columns:
        return df

    result = df.copy()
    asin_values = result["asin"].astype("string").str.strip()
    result = result.loc[
        asin_values.notna() & ~asin_values.isin(["", "-"])
    ].reset_index(drop=True)
    if result.empty:
        return result

    if "sid" not in result.columns:
        result["sid"] = None
    result["sid"] = [
        _sales_sid_for_record(record)
        for record in result.to_dict("records")
    ]
    result = result.loc[
        result["sid"].notna() & (result["sid"].astype("string").str.strip() != "")
    ].reset_index(drop=True)
    return result


def _sales_sid_for_record(record: dict[str, object]) -> str | None:
    sid = record.get("sid")
    if sid not in (None, "") and not pd.isna(sid):
        return str(sid)

    row_asin = str(record.get("asin") or "").strip()
    matching_asin_sids = _unique_sids_from_nested_items(
        record.get("asins"),
        asin=row_asin,
        asin_key="asin",
    )
    if len(matching_asin_sids) == 1:
        return matching_asin_sids[0]

    sids = _unique_values(record.get("sids"))
    if len(sids) == 1:
        return sids[0]

    matching_parent_sids = _unique_sids_from_nested_items(
        record.get("parent_asins"),
        asin=row_asin,
        asin_key="parent_asin",
    )
    if len(matching_parent_sids) == 1:
        return matching_parent_sids[0]

    return None


def _cleanup_profit_report_msku_rows(df: pd.DataFrame) -> pd.DataFrame:
    required_columns = ["sid", "msku", "reportDateMonth"]
    if any(column not in df.columns for column in required_columns):
        return df

    result = df.copy()
    mask = pd.Series(True, index=result.index)
    for column in required_columns:
        values = result[column].astype("string").str.strip()
        mask = mask & values.notna() & ~values.isin(["", "-"])
    return result.loc[mask].reset_index(drop=True)


def _unique_sids_from_nested_items(
    value: object,
    *,
    asin: str,
    asin_key: str,
) -> list[str]:
    if not isinstance(value, list):
        return []
    sids: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        if str(item.get(asin_key) or "").strip() != asin:
            continue
        sid = item.get("sid")
        if sid not in (None, ""):
            sids.append(str(sid))
    return list(dict.fromkeys(sids))


def _unique_values(value: object) -> list[str]:
    if isinstance(value, list):
        return list(dict.fromkeys(str(item) for item in value if item not in (None, "")))
    if value in (None, ""):
        return []
    return [str(value)]
