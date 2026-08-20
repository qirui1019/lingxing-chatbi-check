from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class ComparisonResult:
    passed: bool
    summary: dict[str, int | float | bool]
    details: pd.DataFrame
    metric_details: dict[str, pd.DataFrame] = field(default_factory=dict)
    metric_summaries: pd.DataFrame = field(default_factory=pd.DataFrame)


def compare_dataframes(
    tool_df: pd.DataFrame,
    db_df: pd.DataFrame,
    dimensions: list[str] | None = None,
    metrics: list[str] | None = None,
    dimension_mappings: dict[str, str] | None = None,
    metric_mappings: dict[str, str] | None = None,
    metric_dimension_mappings: dict[str, dict[str, str]] | None = None,
    tolerance: float = 0.0,
) -> ComparisonResult:
    dimension_pairs = _mapping_pairs(dimensions, dimension_mappings)
    metric_pairs = _mapping_pairs(metrics, metric_mappings)
    if metric_dimension_mappings:
        return _compare_dataframes_by_metric_dimensions(
            tool_df=tool_df,
            db_df=db_df,
            dimension_pairs=dimension_pairs,
            metric_pairs=metric_pairs,
            metric_dimension_mappings=metric_dimension_mappings,
            tolerance=tolerance,
        )

    tool_df = _with_empty_columns(
        tool_df,
        [pair[0] for pair in dimension_pairs + metric_pairs],
    )
    db_df = _with_empty_columns(
        db_df,
        [pair[1] for pair in dimension_pairs + metric_pairs],
    )

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
    prepared_tool = _aggregate_prepared_frame(
        prepared_tool,
        join_columns=join_columns,
        metric_columns=[f"tool.{tool_field}" for tool_field, _ in metric_pairs],
    )
    prepared_db = _aggregate_prepared_frame(
        prepared_db,
        join_columns=join_columns,
        metric_columns=[f"db.{db_field}" for _, db_field in metric_pairs],
    )

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
    metric_details: dict[str, pd.DataFrame] = {}
    metric_summary_rows: list[dict[str, object]] = []
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

        metric_detail_columns: dict[str, object] = {}
        for pair in dimension_pairs:
            metric_detail_columns[pair[0]] = merged[_dimension_standard_name(pair)]
        metric_detail_columns[tool_col] = merged[tool_col]
        metric_detail_columns[db_col] = merged[db_col]
        metric_detail_columns["diff"] = diff_values
        metric_detail_columns["passed"] = passed_values.map(bool).astype(object)
        metric_detail = pd.DataFrame(metric_detail_columns)
        metric_detail = metric_detail.sort_values(
            by=["passed"],
            ascending=True,
            kind="stable",
        ).reset_index(drop=True)
        metric_details[tool_field] = metric_detail
        metric_summary_rows.append(
            {
                "metric": tool_field,
                "tool_field": tool_field,
                "db_field": db_field,
                "total_rows": int(len(metric_detail)),
                "failed_rows": int((~passed_values).sum()),
                "tool_only_rows": int((merged["_merge"] == "left_only").sum()),
                "db_only_rows": int((merged["_merge"] == "right_only").sum()),
                "passed": bool(passed_values.all()),
            }
        )

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
        metric_details=metric_details,
        metric_summaries=pd.DataFrame(metric_summary_rows),
    )


def _compare_dataframes_by_metric_dimensions(
    *,
    tool_df: pd.DataFrame,
    db_df: pd.DataFrame,
    dimension_pairs: list[tuple[str, str]],
    metric_pairs: list[tuple[str, str]],
    metric_dimension_mappings: dict[str, dict[str, str]],
    tolerance: float,
) -> ComparisonResult:
    metric_details: dict[str, pd.DataFrame] = {}
    metric_summary_rows: list[dict[str, object]] = []
    detail_frames: list[pd.DataFrame] = []

    for metric_pair in metric_pairs:
        tool_field, db_field = metric_pair
        active_dimension_pairs = _dimension_pairs_for_metric(
            metric_pair,
            default_dimension_pairs=dimension_pairs,
            metric_dimension_mappings=metric_dimension_mappings,
        )
        merged = _prepared_metric_merge(
            tool_df=tool_df,
            db_df=db_df,
            dimension_pairs=active_dimension_pairs,
            metric_pair=metric_pair,
        )

        tool_col = f"tool.{tool_field}"
        db_col = f"db.{db_field}"
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

        metric_detail_columns: dict[str, object] = {}
        for pair in active_dimension_pairs:
            metric_detail_columns[pair[0]] = merged[_dimension_standard_name(pair)]
        metric_detail_columns[tool_col] = merged[tool_col]
        metric_detail_columns[db_col] = merged[db_col]
        metric_detail_columns["diff"] = diff_values
        metric_detail_columns["passed"] = passed_values.map(bool).astype(object)
        metric_detail = pd.DataFrame(metric_detail_columns)
        metric_detail = metric_detail.sort_values(
            by=["passed"],
            ascending=True,
            kind="stable",
        ).reset_index(drop=True)
        metric_details[tool_field] = metric_detail

        detail_frames.append(metric_detail.assign(metric=tool_field))
        metric_summary_rows.append(
            {
                "metric": tool_field,
                "tool_field": tool_field,
                "db_field": db_field,
                "total_rows": int(len(metric_detail)),
                "failed_rows": int((~passed_values).sum()),
                "tool_only_rows": int((merged["_merge"] == "left_only").sum()),
                "db_only_rows": int((merged["_merge"] == "right_only").sum()),
                "passed": bool(passed_values.all()),
            }
        )

    details = (
        pd.concat(detail_frames, ignore_index=True, sort=False)
        if detail_frames
        else pd.DataFrame()
    )
    failed_rows = sum(int(row["failed_rows"]) for row in metric_summary_rows)
    summary = {
        "passed": failed_rows == 0,
        "total_rows": int(sum(int(row["total_rows"]) for row in metric_summary_rows)),
        "failed_rows": failed_rows,
        "tool_only_rows": int(
            sum(int(row["tool_only_rows"]) for row in metric_summary_rows)
        ),
        "db_only_rows": int(
            sum(int(row["db_only_rows"]) for row in metric_summary_rows)
        ),
    }

    return ComparisonResult(
        passed=bool(summary["passed"]),
        summary=summary,
        details=details,
        metric_details=metric_details,
        metric_summaries=pd.DataFrame(metric_summary_rows),
    )


def _dimension_pairs_for_metric(
    metric_pair: tuple[str, str],
    *,
    default_dimension_pairs: list[tuple[str, str]],
    metric_dimension_mappings: dict[str, dict[str, str]],
) -> list[tuple[str, str]]:
    tool_field, db_field = metric_pair
    mapping = (
        metric_dimension_mappings.get(tool_field)
        or metric_dimension_mappings.get(db_field)
    )
    if not mapping:
        return default_dimension_pairs
    return [(str(tool_dimension), str(db_dimension)) for tool_dimension, db_dimension in mapping.items()]


def _prepared_metric_merge(
    *,
    tool_df: pd.DataFrame,
    db_df: pd.DataFrame,
    dimension_pairs: list[tuple[str, str]],
    metric_pair: tuple[str, str],
) -> pd.DataFrame:
    tool_field, db_field = metric_pair
    required_tool_columns = [pair[0] for pair in dimension_pairs] + [tool_field]
    required_db_columns = [pair[1] for pair in dimension_pairs] + [db_field]
    scoped_tool_df = _with_empty_columns(tool_df, required_tool_columns)
    scoped_db_df = _with_empty_columns(db_df, required_db_columns)
    _require_columns(scoped_tool_df, required_tool_columns, "tool_df")
    _require_columns(scoped_db_df, required_db_columns, "db_df")

    prepared_tool = _prepare_frame(
        scoped_tool_df,
        dimension_pairs=dimension_pairs,
        metric_pairs=[metric_pair],
        side="tool",
    )
    prepared_db = _prepare_frame(
        scoped_db_df,
        dimension_pairs=dimension_pairs,
        metric_pairs=[metric_pair],
        side="db",
    )
    join_columns = [_dimension_standard_name(pair) for pair in dimension_pairs]
    prepared_tool = _aggregate_prepared_frame(
        prepared_tool,
        join_columns=join_columns,
        metric_columns=[f"tool.{tool_field}"],
    )
    prepared_db = _aggregate_prepared_frame(
        prepared_db,
        join_columns=join_columns,
        metric_columns=[f"db.{db_field}"],
    )
    return prepared_tool.merge(
        prepared_db,
        on=join_columns,
        how="outer",
        indicator=True,
    )


def _require_columns(df: pd.DataFrame, columns: list[str], frame_name: str) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"{frame_name} missing columns: {', '.join(missing)}")


def _with_empty_columns(
    df: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    if not df.empty:
        return df
    result = df.copy()
    for column in columns:
        if column not in result.columns:
            result[column] = pd.Series(dtype="object")
    return result


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
        columns[_dimension_standard_name(pair)] = _normalize_dimension_values(
            df[source_field]
        )
    for tool_field, db_field in metric_pairs:
        source_field = tool_field if side == "tool" else db_field
        output_field = f"{side}.{source_field}"
        columns[output_field] = df[source_field]
    return pd.DataFrame(columns)


def _aggregate_prepared_frame(
    df: pd.DataFrame,
    *,
    join_columns: list[str],
    metric_columns: list[str],
) -> pd.DataFrame:
    if df.empty:
        return df

    prepared = df.copy()
    for metric_column in metric_columns:
        prepared[metric_column] = pd.to_numeric(
            prepared[metric_column],
            errors="coerce",
        )

    if not metric_columns:
        return prepared.drop_duplicates(subset=join_columns).reset_index(drop=True)

    if not join_columns:
        return pd.DataFrame(
            [
                {
                    metric_column: prepared[metric_column].sum(min_count=1)
                    for metric_column in metric_columns
                }
            ]
        )

    return (
        prepared.groupby(join_columns, dropna=False, as_index=False)[metric_columns]
        .sum(min_count=1)
        .reset_index(drop=True)
    )


def _normalize_dimension_values(values: pd.Series) -> pd.Series:
    return values.astype("string")


def _dimension_standard_name(pair: tuple[str, str]) -> str:
    tool_field, db_field = pair
    return tool_field if tool_field == db_field else f"{tool_field}__{db_field}"
