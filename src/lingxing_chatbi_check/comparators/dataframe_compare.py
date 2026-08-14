from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ComparisonResult:
    passed: bool
    summary: dict[str, int | float | bool]
    details: pd.DataFrame


def compare_dataframes(
    tool_df: pd.DataFrame,
    db_df: pd.DataFrame,
    dimensions: list[str] | None = None,
    metrics: list[str] | None = None,
    dimension_mappings: dict[str, str] | None = None,
    metric_mappings: dict[str, str] | None = None,
    tolerance: float = 0.0,
) -> ComparisonResult:
    dimension_pairs = _mapping_pairs(dimensions, dimension_mappings)
    metric_pairs = _mapping_pairs(metrics, metric_mappings)

    _require_columns(tool_df, [pair[0] for pair in dimension_pairs + metric_pairs], "tool_df")
    _require_columns(db_df, [pair[1] for pair in dimension_pairs + metric_pairs], "db_df")

    prepared_tool = _prepare_frame(
        tool_df,
        dimension_pairs=dimension_pairs,
        metric_pairs=metric_pairs,
        side="tool",
    )
    prepared_db = _prepare_frame(
        db_df,
        dimension_pairs=dimension_pairs,
        metric_pairs=metric_pairs,
        side="db",
    )

    join_columns = [_dimension_standard_name(pair) for pair in dimension_pairs]

    merged = prepared_tool.merge(
        prepared_db,
        on=join_columns,
        how="outer",
        indicator=True,
    )

    detail_columns: dict[str, object] = {}
    for pair in dimension_pairs:
        standard_name = _dimension_standard_name(pair)
        detail_columns[pair[0]] = merged[standard_name]

    row_pass_masks = []
    for metric_pair in metric_pairs:
        tool_field, db_field = metric_pair
        tool_col = f"tool.{tool_field}"
        db_col = f"db.{db_field}"
        diff_col = f"{tool_field}__{db_field}_diff"
        passed_col = f"{tool_field}__{db_field}_passed"

        tool_values = pd.to_numeric(merged[tool_col], errors="coerce")
        db_values = pd.to_numeric(merged[db_col], errors="coerce")
        diff_values = (tool_values - db_values).abs().round(12)
        passed_values = (
            (merged["_merge"] == "both")
            & (
                diff_values.le(tolerance)
                | (tool_values.isna() & db_values.isna())
            )
        )

        detail_columns[tool_col] = merged[tool_col]
        detail_columns[db_col] = merged[db_col]
        detail_columns[diff_col] = diff_values
        detail_columns[passed_col] = passed_values.map(bool).astype(object)
        row_pass_masks.append(passed_values)

    if row_pass_masks:
        all_passed = row_pass_masks[0]
        for mask in row_pass_masks[1:]:
            all_passed = all_passed & mask
    else:
        all_passed = merged["_merge"] == "both"

    details = pd.DataFrame(detail_columns)
    details["row_status"] = all_passed.map(lambda value: "pass" if bool(value) else "fail")

    failed_rows = int((~all_passed).sum())
    summary = {
        "passed": failed_rows == 0,
        "total_rows": int(len(details)),
        "failed_rows": failed_rows,
        "tool_only_rows": int((merged["_merge"] == "left_only").sum()),
        "db_only_rows": int((merged["_merge"] == "right_only").sum()),
    }

    return ComparisonResult(
        passed=bool(summary["passed"]),
        summary=summary,
        details=details,
    )


def _require_columns(df: pd.DataFrame, columns: list[str], frame_name: str) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"{frame_name} missing columns: {', '.join(missing)}")


def _mapping_pairs(
    fields: list[str] | None,
    mappings: dict[str, str] | None,
) -> list[tuple[str, str]]:
    if mappings:
        return [(str(tool_field), str(db_field)) for tool_field, db_field in mappings.items()]
    return [(field, field) for field in (fields or [])]


def _prepare_frame(
    df: pd.DataFrame,
    *,
    dimension_pairs: list[tuple[str, str]],
    metric_pairs: list[tuple[str, str]],
    side: str,
) -> pd.DataFrame:
    columns: dict[str, object] = {}
    for pair in dimension_pairs:
        source_field = pair[0] if side == "tool" else pair[1]
        columns[_dimension_standard_name(pair)] = df[source_field]
    for tool_field, db_field in metric_pairs:
        source_field = tool_field if side == "tool" else db_field
        output_field = f"{side}.{source_field}"
        columns[output_field] = df[source_field]
    return pd.DataFrame(columns)


def _dimension_standard_name(pair: tuple[str, str]) -> str:
    tool_field, db_field = pair
    return tool_field if tool_field == db_field else f"{tool_field}__{db_field}"
