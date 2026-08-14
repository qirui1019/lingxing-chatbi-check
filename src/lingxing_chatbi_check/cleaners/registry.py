from __future__ import annotations

from lingxing_chatbi_check.cleaners.base import Cleaner, JsonNormalizeCleaner


class CleanerRegistry:
    def __init__(self) -> None:
        self._cleaners: dict[str, Cleaner] = {}
        self._default = JsonNormalizeCleaner()

    def register(self, key: str, cleaner: Cleaner) -> None:
        self._cleaners[key] = cleaner

    def get(self, key: str) -> Cleaner:
        return self._cleaners.get(key, self._default)


cleaner_registry = CleanerRegistry()
