from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from lingxing_chatbi_check.cases.models import (
    AuthSpec,
    CaseSpec,
    CompareSpec,
    DatabaseSpec,
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
        tool = data["tool"]
        database = data["database"]
        compare = data["compare"]
    except KeyError as exc:
        raise ValueError(f"Missing required section {exc!s} in {source}") from exc

    return CaseSpec(
        name=str(data.get("name") or source.stem),
        auth=AuthSpec(user_key=str(auth.get("user_key", "default"))),
        tool=ToolSpec(
            name=str(tool["name"]),
            arguments=dict(tool.get("arguments") or {}),
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
