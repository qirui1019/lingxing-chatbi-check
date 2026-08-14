from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from lingxing_chatbi_check.comparators.dataframe_compare import ComparisonResult


def write_excel_report(
    path: Path,
    result: ComparisonResult,
    context: Mapping[str, Any],
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)

    summary_rows = [{"key": key, "value": value} for key, value in result.summary.items()]
    context_rows = [{"key": key, "value": value} for key, value in context.items()]

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="summary", index=False)
        pd.DataFrame(context_rows).to_excel(writer, sheet_name="context", index=False)
        result.details.to_excel(writer, sheet_name="details", index=False)

    return path
