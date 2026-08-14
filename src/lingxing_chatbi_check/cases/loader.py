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

    return [load_case(path) for path in sorted(directory.glob("*.yml"))]


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
                batch_size=int(dynamic_arguments.get("batch_size", 50)),
                database_param=dynamic_arguments.get("database_param"),
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
            tolerance=float(compare.get("tolerance", 0.0)),
        ),
    )
