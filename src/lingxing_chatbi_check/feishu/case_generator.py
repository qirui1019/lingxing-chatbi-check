from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import yaml
from openpyxl import load_workbook


HELPER_TOOLS = {
    "ad_auth_shops",
    "get_my_sids",
    "erp_listing",
    "get_multi_platform_shop_list",
}


@dataclass(frozen=True)
class AvailableToolRow:
    category: str
    tool: str
    required_arguments: str
    optional_arguments: str
    test_arguments: str
    output_fields: str
    dimensions: str
    database_table: str
    database_fields: str


def load_available_tool_rows(path: Path) -> list[AvailableToolRow]:
    workbook = load_workbook(path, data_only=True)
    sheet = workbook["可用tool"]
    headers = [sheet.cell(1, column).value for column in range(1, sheet.max_column + 1)]

    rows: list[AvailableToolRow] = []
    last: dict[str, Any] = {}
    for row_index in range(2, sheet.max_row + 1):
        row = {
            str(headers[column - 1]): sheet.cell(row_index, column).value
            for column in range(1, len(headers) + 1)
            if headers[column - 1]
        }
        if not any(value is not None for value in row.values()):
            continue

        for key in ("表格类型", "Tool", "必填入参", "可选入参"):
            if row.get(key) in (None, "") and last.get(key) not in (None, ""):
                row[key] = last[key]
        last.update({key: value for key, value in row.items() if value not in (None, "")})

        tool = str(row.get("Tool") or "").strip()
        database_table = _normalize_database_table(str(row.get("对应数据库") or ""))
        if not tool or not database_table or database_table.startswith("tool返回"):
            continue

        rows.append(
            AvailableToolRow(
                category=str(row.get("表格类型") or ""),
                tool=tool,
                required_arguments=str(row.get("必填入参") or ""),
                optional_arguments=str(row.get("可选入参") or ""),
                test_arguments=str(row.get("实际测试入参") or ""),
                output_fields=str(row.get("出参字段") or ""),
                dimensions=str(row.get("聚合维度") or ""),
                database_table=database_table,
                database_fields=str(row.get("对应数据库字段") or ""),
            )
        )
    return rows


def write_case_templates(path: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for row in load_available_tool_rows(path):
        if row.tool in HELPER_TOOLS:
            continue
        case_data = build_case_template(row)
        filename = f"{row.tool}__{row.database_table}.yml".replace("/", "_")
        target = output_dir / filename
        target.write_text(
            yaml.safe_dump(case_data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        written.append(target)
    return written


def build_case_template(row: AvailableToolRow) -> dict[str, Any]:
    arguments = _parse_arguments(row.test_arguments)
    if "sponsored_type=sp" in row.dimensions:
        arguments.setdefault("sponsored_type", "sp")
    dynamic_arguments = _dynamic_arguments_for(row)
    return {
        "enabled": False,
        "name": f"{row.tool} vs {row.database_table}",
        "auth": {"mode": "all_users"},
        "scope": {
            "shop_discovery": _shop_discovery_for(row),
            "listing_mapping": "erp_listing"
            if any(key in row.dimensions.lower() for key in ("msku", "asin", "fnsku"))
            else None,
        },
        "tool": {
            "name": row.tool,
            "arguments": arguments,
            "dynamic_arguments": dynamic_arguments,
        },
        "database": {
            "table": row.database_table,
            "sql": _sql_template_for(row),
            "params": _database_params_for(arguments),
        },
        "compare": {
            "dimensions": _split_dimensions(row.dimensions),
            "metrics": _split_fields(row.database_fields),
            "tolerance": 0.01,
        },
        "notes": {
            "raw_dimensions": _split_lines(row.dimensions, split_plus=False),
            "tool_output_fields": _split_fields(row.output_fields),
            "source": "由 data/feishu/lingxing_mcp_tools.xlsx 的可用tool表生成，启用前请检查 SQL 和字段口径。",
        },
    }


def _dynamic_arguments_for(row: AvailableToolRow) -> dict[str, Any]:
    if row.category == "广告":
        return {
            "shop_argument": "profile_ids",
            "shop_batch_mode": "list",
            "source_field": "profile_id",
            "batch_size": 50,
            "database_param": "profile_id_values",
        }
    if "sids" in row.optional_arguments:
        return {
            "shop_argument": "sids",
            "shop_batch_mode": "list",
            "source_field": "sid",
            "batch_size": 50,
            "database_param": "sid_values",
        }
    return {
        "shop_argument": "sid",
        "shop_batch_mode": "single",
        "source_field": "sid",
        "batch_size": 1,
        "database_param": "sid_values",
    }


def _shop_discovery_for(row: AvailableToolRow) -> str:
    if row.category == "广告":
        return "ad_auth_shops"
    return "get_my_sids"


def _parse_arguments(text: str) -> dict[str, Any]:
    arguments: dict[str, Any] = {}
    for line in _split_lines(text):
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        clean_key = key.strip()
        if clean_key in {"sid", "sids", "profile_id", "profile_ids"}:
            continue
        clean_value = value.split("（", 1)[0].strip()
        arguments[clean_key] = _parse_value(clean_value)
    return arguments


def _parse_value(value: str) -> Any:
    if value in ("-", ""):
        return ""
    if value.startswith("[") and value.endswith("]"):
        try:
            return yaml.safe_load(value)
        except yaml.YAMLError:
            return value
    if value.isdigit():
        return int(value)
    return value


def _database_params_for(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in arguments.items()
        if key in {"start_date", "end_date", "report_date"}
    }


def _sql_template_for(row: AvailableToolRow) -> str:
    fields = _split_fields(row.database_fields)
    dimensions = _split_dimensions(row.dimensions)
    selected = list(dict.fromkeys(dimensions + fields)) or ["*"]
    where_field = "profile_id" if row.category == "广告" else "sid"
    param = "profile_id_values" if row.category == "广告" else "sid_values"
    return (
        "select\n  "
        + ",\n  ".join(selected)
        + f"\nfrom {row.database_table}\nwhere {where_field} in :{param}\n"
    )


def _split_dimensions(text: str) -> list[str]:
    return _split_lines(text, split_plus=True, identifiers_only=True)


def _split_fields(text: str) -> list[str]:
    return _split_lines(text, split_plus=False, identifiers_only=True)


def _split_lines(
    text: str,
    *,
    split_plus: bool = True,
    identifiers_only: bool = False,
) -> list[str]:
    values: list[str] = []
    normalized = str(text or "")
    if split_plus:
        normalized = _strip_parenthetical_notes(normalized).replace("+", "\n")
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line or line in {"/", "-"}:
            continue
        if identifiers_only:
            identifier = _first_identifier(line)
            if identifier:
                values.append(identifier)
        else:
            values.append(line)
    return values


def _normalize_database_table(value: str) -> str:
    return value.strip().replace("cahtbi.", "chatbi.")


def _strip_parenthetical_notes(value: str) -> str:
    value = re.sub(r"（[^）]*）", "", value)
    return re.sub(r"\([^)]*\)", "", value)


def _first_identifier(value: str) -> str | None:
    value = _strip_parenthetical_notes(value)
    match = re.search(r"[A-Za-z_][A-Za-z0-9_]*", value)
    if not match:
        return None
    return match.group(0)
