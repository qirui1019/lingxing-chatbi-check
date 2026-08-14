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
    dimensions: list[str],
    metrics: list[str],
    tolerance: float = 0.0,
) -> ComparisonResult:
    _require_columns(tool_df, dimensions + metrics, "tool_df")
    _require_columns(db_df, dimensions + metrics, "db_df")

    merged = tool_df.merge(
        db_df,
        on=dimensions,
        how="outer",
        suffixes=("_tool", "_db"),
        indicator=True,
    )

    detail_columns: dict[str, object] = {}
    for dimension in dimensions:
        detail_columns[dimension] = merged[dimension]

    row_pass_masks = []
    for metric in metrics:
        tool_col = f"{metric}_tool"
        db_col = f"{metric}_db"
        diff_col = f"{metric}_diff"
        passed_col = f"{metric}_passed"

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
