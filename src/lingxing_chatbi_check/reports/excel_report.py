from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re
from typing import Any

import pandas as pd

from lingxing_chatbi_check.comparators.dataframe_compare import ComparisonResult


@dataclass(frozen=True)
class MetricReportWriteResult:
    paths: list[Path]
    log_rows: list[dict[str, Any]]


def write_excel_report(
    path: Path,
    result: ComparisonResult,
    context: Mapping[str, Any],
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)

    context_rows = [{"key": key, "value": value} for key, value in context.items()]
    summary = _summary_frame(result, context)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="summary", index=False)
        pd.DataFrame(context_rows).to_excel(writer, sheet_name="context", index=False)
        if result.metric_details:
            used_sheet_names = {"summary", "context"}
            for metric, details in result.metric_details.items():
                sheet_name = _unique_sheet_name(f"metric_{metric}", used_sheet_names)
                details.to_excel(writer, sheet_name=sheet_name, index=False)
        else:
            result.details.to_excel(writer, sheet_name="details", index=False)

    return path


def write_metric_report_files(
    output_dir: Path,
    result: ComparisonResult,
    context: Mapping[str, Any],
    *,
    exception_threshold: float = 0.001,
) -> MetricReportWriteResult:
    output_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    log_rows: list[dict[str, Any]] = []
    prefix = _report_prefix(context)
    period_label = str(context.get("period_label") or "unknown_period")
    query_time = str(context.get("query_time") or _today_label())

    for summary_row in _metric_summary_records(result):
        tool_field = str(summary_row["tool_field"])
        db_field = str(summary_row["db_field"])
        details = result.metric_details[tool_field]
        table = _metric_report_table(details, tool_field=tool_field, db_field=db_field)
        report_name = _safe_filename(f"{prefix}_{db_field}_{period_label}.xlsx")
        report_path = output_dir / report_name
        _write_metric_workbook(report_path, table)
        paths.append(report_path)
        log_rows.append(
            {
                "case_name": context.get("case_name"),
                "tool_name": context.get("tool_name"),
                "table_name": context.get("table_name"),
                "metric": db_field,
                "tool_field": tool_field,
                "db_field": db_field,
                "report_file": report_name,
                "query_time": query_time,
                "result_count": int(len(table)),
                "exception_count": _exception_count(table, exception_threshold),
            }
        )

    return MetricReportWriteResult(paths=paths, log_rows=log_rows)


def write_run_log(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_excel(path, index=False)
    return path


def _write_metric_workbook(path: Path, table: pd.DataFrame) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        table.to_excel(writer, index=False)
        _format_diff_rate_as_percent(writer, table)


def _format_diff_rate_as_percent(writer: pd.ExcelWriter, table: pd.DataFrame) -> None:
    if "diff_rate" not in table.columns:
        return
    worksheet = writer.book.active
    column_index = table.columns.get_loc("diff_rate") + 1
    for row_index in range(2, len(table) + 2):
        worksheet.cell(row=row_index, column=column_index).number_format = "0.00%"


def _summary_frame(
    result: ComparisonResult,
    context: Mapping[str, Any],
) -> pd.DataFrame:
    if result.metric_summaries.empty:
        return pd.DataFrame(
            [{"key": key, "value": value} for key, value in result.summary.items()]
        )

    summary = result.metric_summaries.copy()
    insert_at = 3
    for field in ("tool_query_seconds", "db_query_seconds", "total_query_seconds"):
        summary.insert(insert_at, field, context.get(field))
        insert_at += 1
    return summary


def _metric_summary_records(result: ComparisonResult) -> list[dict[str, Any]]:
    if not result.metric_summaries.empty:
        return result.metric_summaries.to_dict("records")
    return [
        {
            "tool_field": metric,
            "db_field": metric,
        }
        for metric in result.metric_details
    ]


def _metric_report_table(
    details: pd.DataFrame,
    *,
    tool_field: str,
    db_field: str,
) -> pd.DataFrame:
    tool_col = f"tool.{tool_field}"
    db_col = f"db.{db_field}"
    table = details.copy()
    if "diff_rate" not in table.columns:
        table["diff_rate"] = _diff_rate(
            tool_values=table[tool_col],
            db_values=table[db_col],
            diff_values=table["diff"],
        )

    dimension_columns = _report_dimension_columns(table)
    columns = dimension_columns + [tool_col, db_col, "diff", "diff_rate"]
    table = table.loc[:, columns]
    return (
        table.sort_values(
            by=["diff_rate"],
            ascending=False,
            na_position="last",
            kind="stable",
        )
        .reset_index(drop=True)
    )


def _report_dimension_columns(table: pd.DataFrame) -> list[str]:
    return [
        column
        for column in table.columns
        if not column.startswith("tool.")
        and not column.startswith("db.")
        and column not in {"report_date", "diff", "diff_rate", "passed"}
    ]


def _diff_rate(
    *,
    tool_values: pd.Series,
    db_values: pd.Series,
    diff_values: pd.Series,
) -> pd.Series:
    tool = pd.to_numeric(tool_values, errors="coerce")
    db_raw = pd.to_numeric(db_values, errors="coerce")
    diff = pd.to_numeric(diff_values, errors="coerce")
    db = db_raw.abs()
    rate = diff.divide(db).where(db.ne(0))

    tool_empty_or_zero = tool.isna() | tool.eq(0)
    db_empty_or_zero = db_raw.isna() | db_raw.eq(0)
    equivalent_empty_zero = tool_empty_or_zero & db_empty_or_zero
    uncomputable = rate.isna()
    should_mark_full_diff = uncomputable & ~equivalent_empty_zero
    return rate.mask(should_mark_full_diff, 1.0)


def _exception_count(table: pd.DataFrame, threshold: float) -> int:
    diff_rate = pd.to_numeric(table["diff_rate"], errors="coerce")
    return int(diff_rate.gt(threshold).sum())


def _today_label() -> str:
    return date.today().strftime("%Y.%m.%d")


def _report_prefix(context: Mapping[str, Any]) -> str:
    explicit = context.get("report_prefix")
    if explicit:
        return str(explicit)

    table_name = str(context.get("table_name") or "report")
    stem = table_name.rsplit(".", 1)[-1]
    if stem.startswith("sp_"):
        stem = stem[3:]
    if stem.endswith("_report"):
        stem = stem[: -len("_report")]
    return stem or "report"


def _unique_sheet_name(value: str, used_sheet_names: set[str]) -> str:
    base = _safe_sheet_name(value)
    sheet_name = base
    index = 2
    while sheet_name in used_sheet_names:
        suffix = f"_{index}"
        sheet_name = f"{base[: 31 - len(suffix)]}{suffix}"
        index += 1
    used_sheet_names.add(sheet_name)
    return sheet_name


def _safe_filename(value: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1F]+', "_", str(value)).strip(" .")
    return safe or "report.xlsx"


def _safe_sheet_name(value: str) -> str:
    safe = "".join(
        "_" if char in r'[]:*?/\\' else char
        for char in str(value)
    ).strip("'")
    return (safe or "sheet")[:31]
