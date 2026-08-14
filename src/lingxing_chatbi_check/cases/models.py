from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AuthSpec:
    user_key: str = "default"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DatabaseSpec:
    table: str
    sql: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CompareSpec:
    dimensions: list[str]
    metrics: list[str]
    tolerance: float = 0.0


@dataclass(frozen=True)
class CaseSpec:
    name: str
    auth: AuthSpec
    tool: ToolSpec
    database: DatabaseSpec
    compare: CompareSpec
