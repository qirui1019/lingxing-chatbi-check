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
    database_source_field: str | None = None
    batch_size: int = 50
    database_param: str | None = None


@dataclass(frozen=True)
class PaginationSpec:
    enabled: bool = False
    page_argument: str = "page"
    page_start: int = 1
    page_size_argument: str = "length"
    page_size: int = 1000
    max_pages: int = 1000
    page_value_mode: str = "page"
    batch_timeout_seconds: float | None = 300


@dataclass(frozen=True)
class ToolSpec:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    dynamic_arguments: DynamicArgumentsSpec = field(
        default_factory=DynamicArgumentsSpec
    )
    pagination: PaginationSpec | None = None


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
    metric_dimension_mappings: dict[str, dict[str, str]] = field(default_factory=dict)
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
