from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AuthSpec:
    mode: str = "single_user"
    user_key: str = "default"


@dataclass(frozen=True)
class ScopeSpec:
    shop_discovery: str | None = None
    listing_mapping: str | None = None


@dataclass(frozen=True)
class DynamicArgumentsSpec:
    shop_argument: str | None = None
    shop_batch_mode: str = "none"
    source_field: str = "sid"
    batch_size: int = 50
    database_param: str | None = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    dynamic_arguments: DynamicArgumentsSpec = field(
        default_factory=DynamicArgumentsSpec
    )


@dataclass(frozen=True)
class DatabaseSpec:
    table: str
    sql: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CompareSpec:
    dimensions: list[str]
    metrics: list[str]
    dimension_mappings: dict[str, str] = field(default_factory=dict)
    metric_mappings: dict[str, str] = field(default_factory=dict)
    tolerance: float = 0.0


@dataclass(frozen=True)
class CaseSpec:
    name: str
    enabled: bool
    auth: AuthSpec
    scope: ScopeSpec
    tool: ToolSpec
    database: DatabaseSpec
    compare: CompareSpec
