from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from lingxing_chatbi_check.cases.models import (
    AuthSpec,
    CaseSpec,
    CompareSpec,
    DatabaseSpec,
    DynamicArgumentsSpec,
    PaginationSpec,
    ScopeSpec,
    ToolSpec,
)


def load_case(path: Path) -> CaseSpec:
    if not path.exists():
        raise FileNotFoundError(f"Case config not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Case config must be a YAML mapping: {path}")

    return _case_from_mapping(data, source=path)


def load_cases(directory: Path) -> list[CaseSpec]:
    if not directory.exists():
        raise FileNotFoundError(f"Case directory not found: {directory}")

    paths = sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")])
    return [load_case(path) for path in paths]


def _case_from_mapping(data: dict[str, Any], source: Path) -> CaseSpec:
    try:
        auth = data.get("auth") or {}
        scope = data.get("scope") or {}
        tool = data["tool"]
        database = data["database"]
        compare = data["compare"]
    except KeyError as exc:
        raise ValueError(f"Missing required section {exc!s} in {source}") from exc

    dynamic_arguments = tool.get("dynamic_arguments") or {}
    pagination = tool.get("pagination") or {}
    auth_mode = str(auth.get("mode") or "single_user")
    user_key = str(auth.get("user_key", "default"))
    if auth_mode == "all_users" and "user_key" not in auth:
        user_key = ""

    return CaseSpec(
        name=str(data.get("name") or source.stem),
        enabled=bool(data.get("enabled", True)),
        auth=AuthSpec(mode=auth_mode, user_key=user_key),
        scope=ScopeSpec(
            shop_discovery=scope.get("shop_discovery"),
            listing_mapping=scope.get("listing_mapping"),
        ),
        tool=ToolSpec(
            name=str(tool["name"]),
            arguments=dict(tool.get("arguments") or {}),
            dynamic_arguments=DynamicArgumentsSpec(
                shop_argument=dynamic_arguments.get("shop_argument"),
                shop_batch_mode=str(
                    dynamic_arguments.get("shop_batch_mode", "none")
                ),
                source_field=str(dynamic_arguments.get("source_field", "sid")),
                database_source_field=(
                    str(dynamic_arguments["database_source_field"])
                    if dynamic_arguments.get("database_source_field") is not None
                    else None
                ),
                batch_size=int(dynamic_arguments.get("batch_size", 50)),
                database_param=dynamic_arguments.get("database_param"),
            ),
            pagination=(
                PaginationSpec(
                    enabled=bool(pagination.get("enabled", False)),
                    page_argument=str(pagination.get("page_argument", "page")),
                    page_start=int(pagination.get("page_start", 1)),
                    page_size_argument=str(
                        pagination.get("page_size_argument", "length")
                    ),
                    page_size=int(pagination.get("page_size", 1000)),
                    max_pages=int(pagination.get("max_pages", 1000)),
                    page_value_mode=str(pagination.get("page_value_mode", "page")),
                    batch_timeout_seconds=_pagination_batch_timeout_seconds(
                        pagination
                    ),
                )
                if pagination
                else None
            ),
        ),
        database=DatabaseSpec(
            table=str(database["table"]),
            sql=str(database["sql"]),
            params=dict(database.get("params") or {}),
        ),
        compare=CompareSpec(
            dimensions=[str(item) for item in compare["dimensions"]],
            metrics=[str(item) for item in compare["metrics"]],
            dimension_mappings={
                str(key): str(value)
                for key, value in (compare.get("dimension_mappings") or {}).items()
            },
            metric_mappings={
                str(key): str(value)
                for key, value in (compare.get("metric_mappings") or {}).items()
            },
            metric_dimension_mappings={
                str(metric): {
                    str(tool_field): str(db_field)
                    for tool_field, db_field in (mapping or {}).items()
                }
                for metric, mapping in (
                    compare.get("metric_dimension_mappings") or {}
                ).items()
            },
            tolerance=float(compare.get("tolerance", 0.0)),
        ),
    )


def _pagination_batch_timeout_seconds(
    pagination: dict[str, Any],
) -> float | None:
    if "batch_timeout_seconds" not in pagination:
        return 300
    value = pagination["batch_timeout_seconds"]
    if value is None:
        return None
    return float(value)
