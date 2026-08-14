from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd


@dataclass(frozen=True)
class CleanerContext:
    tool_name: str
    table_name: str


class Cleaner(Protocol):
    def clean(self, data: Any, context: CleanerContext) -> pd.DataFrame:
        ...


class JsonNormalizeCleaner:
    def clean(self, data: Any, context: CleanerContext) -> pd.DataFrame:
        if isinstance(data, pd.DataFrame):
            return data.copy()
        if isinstance(data, list):
            return pd.json_normalize(data)
        if isinstance(data, dict):
            for key in ("data", "rows", "list", "items", "records"):
                value = data.get(key)
                if isinstance(value, list):
                    return pd.json_normalize(value)
            return pd.json_normalize(data)
        raise ValueError(
            f"Cannot normalize data for tool={context.tool_name}, table={context.table_name}"
        )
