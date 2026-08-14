from __future__ import annotations

from pathlib import Path

import pandas as pd


class FeishuSheetClient:
    def read_exported_excel(self, path: Path, sheet_name: str | int = 0) -> pd.DataFrame:
        if not path.exists():
            raise FileNotFoundError(f"Feishu export not found: {path}")
        return pd.read_excel(path, sheet_name=sheet_name)

    def read_remote_sheet(self) -> pd.DataFrame:
        raise NotImplementedError(
            "Remote Feishu access needs the final access method: API token, exported file, or connector."
        )
