from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from lingxing_chatbi_check.cases.models import CaseSpec
from lingxing_chatbi_check.cleaners.base import CleanerContext
from lingxing_chatbi_check.cleaners.registry import cleaner_registry
from lingxing_chatbi_check.clients.doris_mysql import DorisMysqlClient
from lingxing_chatbi_check.clients.lingxing_mcp import LingxingMcpClient
from lingxing_chatbi_check.comparators.dataframe_compare import compare_dataframes
from lingxing_chatbi_check.config import get_mcp_user_config
from lingxing_chatbi_check.reports.excel_report import write_excel_report


def run_case(case: CaseSpec, env_config: dict[str, Any], output_dir: Path) -> Path:
    return asyncio.run(run_case_async(case, env_config, output_dir))


async def run_case_async(
    case: CaseSpec,
    env_config: dict[str, Any],
    output_dir: Path,
) -> Path:
    mcp_config = env_config["lingxing_mcp"]
    mcp_user = get_mcp_user_config(env_config, case.auth.user_key)

    mcp_client = LingxingMcpClient(
        url=str(mcp_config["url"]),
        x_mcp_key=mcp_user["x_mcp_key"],
    )
    db_client = DorisMysqlClient.from_config(env_config["doris_mysql"])

    raw_tool_output = await mcp_client.call_tool(case.tool.name, case.tool.arguments)
    db_output = db_client.query(case.database.sql, case.database.params)

    context = CleanerContext(tool_name=case.tool.name, table_name=case.database.table)
    cleaner = cleaner_registry.get(f"{case.tool.name}__{case.database.table}")
    tool_df = cleaner.clean(raw_tool_output, context)
    db_df = cleaner.clean(db_output, context)

    result = compare_dataframes(
        tool_df=tool_df,
        db_df=db_df,
        dimensions=case.compare.dimensions,
        metrics=case.compare.metrics,
        tolerance=case.compare.tolerance,
    )

    report_name = _safe_filename(f"{case.tool.name}__{case.database.table}.xlsx")
    return write_excel_report(
        output_dir / report_name,
        result,
        context={
            "case_name": case.name,
            "tool_name": case.tool.name,
            "table_name": case.database.table,
            "user_key": case.auth.user_key,
            "dimensions": ", ".join(case.compare.dimensions),
            "metrics": ", ".join(case.compare.metrics),
        },
    )


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
