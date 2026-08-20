from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import re
from typing import Any

import pandas as pd

from lingxing_chatbi_check.clients.feishu_sheet import FeishuSheetClient


@dataclass(frozen=True)
class FeishuUploadSummary:
    matched_count: int
    unmatched_reports: list[str] = field(default_factory=list)
    mapping_path: Path | None = None


@dataclass(frozen=True)
class TemplateRow:
    row_number: int
    tool_name: str
    table_name: str
    tool_field: str
    db_field: str
    period: str | None
    result_column: str


def upload_report_dir_to_feishu(
    report_dir: Path,
    feishu_config: dict[str, Any],
    *,
    client: Any | None = None,
) -> FeishuUploadSummary:
    if not report_dir.exists():
        raise FileNotFoundError(f"Report directory not found: {report_dir}")

    log_path = report_dir / "run_log.xlsx"
    if not log_path.exists():
        raise FileNotFoundError(f"Run log not found: {log_path}")

    active_client = client or FeishuSheetClient.from_config(feishu_config)
    sheet_id = str(feishu_config.get("sheet_id") or "")
    folder_token = str(feishu_config.get("file_folder_token") or "")
    if not sheet_id:
        raise ValueError("feishu.sheet_id is required")
    template_rows = _load_rows_from_config(active_client, sheet_id, feishu_config)

    matched_count = 0
    unmatched_reports: list[str] = []
    mapping_rows: list[dict[str, Any]] = []
    upload_time_label = _upload_time_label(feishu_config)
    upload_folders: dict[str, tuple[str, str]] = {}
    for row in _run_log_records(log_path):
        report_file = str(row.get("report_file") or "")
        report_path = report_dir / report_file
        target = _find_template_row(template_rows, row)
        if target is None:
            unmatched_reports.append(report_file)
            mapping_rows.append(_mapping_row(row, report_path, None, "", "", "", ""))
            continue
        folder_prefix = _report_folder_prefix(row, report_path)
        if folder_prefix not in upload_folders:
            upload_folder_name = f"{folder_prefix}_{upload_time_label}"
            upload_folders[folder_prefix] = (
                upload_folder_name,
                active_client.create_folder(upload_folder_name, folder_token),
            )
        upload_folder_name, upload_folder_token = upload_folders[folder_prefix]
        link = active_client.upload_file(report_path, upload_folder_token)
        value = _result_cell_text(row, report_path, link)
        cell_range = (
            f"{sheet_id}!{target.result_column}{target.row_number}:"
            f"{target.result_column}{target.row_number}"
        )
        active_client.write_values(cell_range, [[value]])
        mapping_rows.append(
            _mapping_row(
                row,
                report_path,
                target,
                link,
                value,
                upload_folder_name,
                upload_folder_token,
            )
        )
        matched_count += 1

    mapping_path = write_mapping_file(report_dir / "feishu_mapping.xlsx", mapping_rows)
    return FeishuUploadSummary(
        matched_count=matched_count,
        unmatched_reports=unmatched_reports,
        mapping_path=mapping_path,
    )


def generate_feishu_mapping(
    report_dir: Path,
    feishu_config: dict[str, Any],
    *,
    client: Any | None = None,
) -> Path:
    if not report_dir.exists():
        raise FileNotFoundError(f"Report directory not found: {report_dir}")

    log_path = report_dir / "run_log.xlsx"
    if not log_path.exists():
        raise FileNotFoundError(f"Run log not found: {log_path}")

    active_client = client or FeishuSheetClient.from_config(feishu_config)
    sheet_id = str(feishu_config.get("sheet_id") or "")
    if not sheet_id:
        raise ValueError("feishu.sheet_id is required")

    template_rows = _load_rows_from_config(active_client, sheet_id, feishu_config)
    mapping_rows = [
        _mapping_row(
            row,
            report_dir / str(row.get("report_file") or ""),
            _find_template_row(template_rows, row),
            "",
            "",
        )
        for row in _run_log_records(log_path)
    ]
    return write_mapping_file(report_dir / "feishu_mapping.xlsx", mapping_rows)


def write_mapping_file(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_excel(path, index=False)
    return path


def _load_rows_from_config(
    client: Any,
    sheet_id: str,
    feishu_config: dict[str, Any],
) -> list[TemplateRow]:
    return load_remote_template_rows(
        client,
        sheet_id=sheet_id,
        result_header=str(feishu_config.get("result_header") or "查询结果"),
        read_range=str(feishu_config.get("read_range") or "A1:ZZ1000"),
    )


def _mapping_row(
    log_row: dict[str, Any],
    report_path: Path,
    target: TemplateRow | None,
    link: str,
    write_text: str,
    upload_folder_name: str = "",
    upload_folder_token: str = "",
) -> dict[str, Any]:
    feishu_cell = ""
    if target is not None:
        feishu_cell = f"{target.result_column}{target.row_number}"
    return {
        "report_file": str(log_row.get("report_file") or ""),
        "tool_name": str(log_row.get("tool_name") or ""),
        "table_name": str(log_row.get("table_name") or ""),
        "tool_field": str(log_row.get("tool_field") or ""),
        "db_field": str(log_row.get("db_field") or ""),
        "period": _period_from_report_file(str(log_row.get("report_file") or "")) or "",
        "matched": target is not None,
        "feishu_row": target.row_number if target is not None else "",
        "feishu_cell": feishu_cell,
        "query_time": _display_value(log_row.get("query_time")),
        "result_count": _display_value(log_row.get("result_count")),
        "exception_count": _display_value(log_row.get("exception_count")),
        "upload_folder_name": upload_folder_name,
        "upload_folder_token": upload_folder_token,
        "report_link": link,
        "write_text": write_text,
    }


def load_remote_template_rows(
    client: Any,
    *,
    sheet_id: str,
    result_header: str,
    read_range: str,
) -> list[TemplateRow]:
    values = client.read_values(f"{sheet_id}!{read_range}")
    if not values:
        return []
    if _looks_like_month_grouped_headers(values, result_header):
        return _load_month_grouped_template_rows(values, result_header)

    headers = [str(value or "") for value in values[0]]
    columns = _template_columns(headers, result_header)
    rows: list[TemplateRow] = []
    current_case_value: Any = None
    current_tool_field: Any = None
    current_db_field: Any = None
    for offset, values_row in enumerate(values[1:], start=2):
        case_value = _value_at(values_row, columns["case"])
        tool_field = _value_at(values_row, columns["tool_field"])
        db_field = _value_at(values_row, columns["db_field"])
        sample_date = _value_at(values_row, columns["date"])
        if case_value:
            current_case_value = case_value
        if tool_field:
            current_tool_field = tool_field
        if db_field:
            current_db_field = db_field
        case_value = case_value or current_case_value
        tool_field = tool_field or current_tool_field
        db_field = db_field or current_db_field
        if not case_value or not tool_field or not db_field:
            continue
        tool_name, table_name = _parse_case_cell(str(case_value))
        if not tool_name or not table_name:
            continue
        rows.append(
            TemplateRow(
                row_number=offset,
                tool_name=_normalize_key(tool_name),
                table_name=_normalize_table(table_name),
                tool_field=_normalize_key(str(tool_field)),
                db_field=_normalize_key(str(db_field)),
                period=_period_from_value(sample_date),
                result_column=_column_letter(columns["result"] + 1),
            )
        )
    return rows


def _looks_like_month_grouped_headers(
    values: list[list[Any]],
    result_header: str,
) -> bool:
    if len(values) < 2:
        return False
    first = [str(value or "") for value in values[0]]
    second = [str(value or "") for value in values[1]]
    if not any(_period_from_value(value) for value in first):
        return False
    return bool(_result_column_indexes(second, result_header))


def _load_month_grouped_template_rows(
    values: list[list[Any]],
    result_header: str,
) -> list[TemplateRow]:
    top_headers = [str(value or "") for value in values[0]]
    sub_headers = [str(value or "") for value in values[1]]
    combined_headers = [
        f"{_value_at(top_headers, index) or ''}{_value_at(sub_headers, index) or ''}"
        for index in range(max(len(top_headers), len(sub_headers)))
    ]
    columns = {
        "case": _find_header_index(
            [_normalize_header(value) for value in combined_headers],
            ["tool", "chatbi"],
        ),
        "tool_field": _find_header_index(
            [_normalize_header(value) for value in combined_headers],
            ["tool", "字段"],
        ),
        "db_field": _find_header_index(
            [_normalize_header(value) for value in combined_headers],
            ["chatbi", "字段"],
        ),
    }
    periods_by_column = _periods_by_column(top_headers)
    date_columns_by_period = {
        period: index
        for index, period in enumerate(periods_by_column)
        if period is not None and "日期" in _normalize_header(_value_at(sub_headers, index))
    }
    result_columns = [
        (index, periods_by_column[index])
        for index in _result_column_indexes(sub_headers, result_header)
    ]

    rows: list[TemplateRow] = []
    for offset, values_row in enumerate(values[2:], start=3):
        case_value = _value_at(values_row, columns["case"])
        tool_field = _value_at(values_row, columns["tool_field"])
        db_field = _value_at(values_row, columns["db_field"])
        if not case_value or not tool_field or not db_field:
            continue
        tool_name, table_name = _parse_case_cell(str(case_value))
        if not tool_name or not table_name:
            continue
        for result_column, header_period in result_columns:
            period = header_period
            date_column = date_columns_by_period.get(header_period or "")
            if period is None and date_column is not None:
                period = _period_from_value(_value_at(values_row, date_column))
            if period is None:
                continue
            rows.append(
                TemplateRow(
                    row_number=offset,
                    tool_name=_normalize_key(tool_name),
                    table_name=_normalize_table(table_name),
                    tool_field=_normalize_key(str(tool_field)),
                    db_field=_normalize_key(str(db_field)),
                    period=period,
                    result_column=_column_letter(result_column + 1),
                )
            )
    return rows


def _result_column_indexes(headers: list[str], result_header: str) -> list[int]:
    expected = _normalize_header(result_header)
    indexes: list[int] = []
    for index, header in enumerate(headers):
        normalized = _normalize_header(header)
        if expected in normalized or "查询结果" in normalized:
            indexes.append(index)
    return indexes


def _periods_by_column(headers: list[str]) -> list[str | None]:
    periods: list[str | None] = []
    active_period: str | None = None
    for header in headers:
        period = _period_from_value(header)
        if period is not None:
            active_period = period
        periods.append(active_period)
    return periods


def _template_columns(headers: list[str], result_header: str) -> dict[str, int]:
    normalized = [_normalize_header(value) for value in headers]
    return {
        "case": _find_header_index(normalized, ["tool", "chatbi"]),
        "tool_field": _find_header_index(normalized, ["tool", "字段"]),
        "db_field": _find_header_index(normalized, ["chatbi", "字段"]),
        "date": _find_header_index(normalized, ["日期"]),
        "result": _find_result_header_index(headers, result_header),
    }


def _find_header_index(normalized_headers: list[str], parts: list[str]) -> int:
    for index, header in enumerate(normalized_headers):
        if all(part in header for part in parts):
            return index
    raise ValueError(f"Feishu sheet missing header containing: {', '.join(parts)}")


def _find_result_header_index(headers: list[str], result_header: str) -> int:
    expected = _normalize_header(result_header)
    for index, header in enumerate(headers):
        normalized = _normalize_header(header)
        if expected in normalized or "查询结果" in normalized:
            return index
    raise ValueError(f"Feishu sheet missing result header: {result_header}")


def _value_at(values: list[Any], index: int) -> Any:
    if index >= len(values):
        return None
    return values[index]


def _column_letter(index: int) -> str:
    result = ""
    current = index
    while current:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _run_log_records(log_path: Path) -> list[dict[str, Any]]:
    return pd.read_excel(log_path).to_dict("records")


def _upload_time_label(feishu_config: dict[str, Any]) -> str:
    configured = str(feishu_config.get("upload_time_label") or "").strip()
    if configured:
        return _safe_drive_name(configured)
    return datetime.now().strftime("%Y.%m.%d_%H-%M-%S")


def _report_folder_prefix(log_row: dict[str, Any], report_path: Path) -> str:
    stem = report_path.stem
    parts = stem.split("_")
    if parts and re.match(r"^\d{4}", parts[-1]):
        stem = "_".join(parts[:-1])

    for field in (
        str(log_row.get("db_field") or ""),
        str(log_row.get("tool_field") or ""),
        str(log_row.get("metric") or ""),
    ):
        field = field.strip()
        if field and stem.endswith(f"_{field}"):
            return _safe_drive_name(stem[: -(len(field) + 1)])

    if "_" in stem:
        return _safe_drive_name(stem.rsplit("_", 1)[0])
    return _safe_drive_name(stem or "report")


def _safe_drive_name(value: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1F]+', "_", str(value)).strip(" .")
    return safe or "report"


def _find_template_row(
    template_rows: list[TemplateRow],
    log_row: dict[str, Any],
) -> TemplateRow | None:
    tool_name = _normalize_key(str(log_row.get("tool_name") or ""))
    table_name = _normalize_table(str(log_row.get("table_name") or ""))
    tool_field = _normalize_key(str(log_row.get("tool_field") or ""))
    db_field = _normalize_key(str(log_row.get("db_field") or ""))
    period = _period_from_report_file(str(log_row.get("report_file") or ""))

    for row in template_rows:
        if (
            row.tool_name == tool_name
            and row.table_name == table_name
            and row.tool_field == tool_field
            and row.db_field == db_field
            and _period_matches(row.period, period)
        ):
            return row
    return None


def _period_matches(template_period: str | None, report_period: str | None) -> bool:
    if report_period is None:
        return True
    return template_period == report_period


def _result_cell_text(
    log_row: dict[str, Any],
    report_path: Path,
    link: str,
) -> str:
    return "\n".join(
        [
            f"查询时间：{_display_value(log_row.get('query_time'))}",
            f"查询结果数量：{_display_value(log_row.get('result_count'))}",
            f"异常数量：{_display_value(log_row.get('exception_count'))}",
            report_path.stem,
            link,
        ]
    )


def _parse_case_cell(value: str) -> tuple[str | None, str | None]:
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if line.lower() == "vs" and index > 0 and index + 1 < len(lines):
            return lines[index - 1], lines[index + 1]
    match = re.search(r"([A-Za-z0-9_]+)\s+vs\s+([A-Za-z0-9_.]+)", value)
    if match:
        return match.group(1), match.group(2)
    return None, None


def _period_from_report_file(value: str) -> str | None:
    match = re.search(r"(\d{4})年(\d{1,2})月", value)
    if not match:
        return None
    return f"{match.group(1)}-{int(match.group(2)):02d}"


def _period_from_value(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m")
    if isinstance(value, (int, float)) and not pd.isna(value):
        return (datetime(1899, 12, 30) + timedelta(days=int(value))).strftime("%Y-%m")
    text = str(value)
    match = re.search(r"(\d{4})[-/.年](\d{1,2})", text)
    if not match:
        return None
    return f"{match.group(1)}-{int(match.group(2)):02d}"


def _normalize_table(value: str) -> str:
    return _normalize_key(value).replace("cahtbi.", "chatbi.")


def _normalize_key(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().lower())


def _normalize_header(value: str) -> str:
    return _normalize_key(str(value))


def _display_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
