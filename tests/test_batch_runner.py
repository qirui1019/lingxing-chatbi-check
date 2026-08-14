from datetime import datetime
from pathlib import Path

from lingxing_chatbi_check.runners.batch_runner import (
    create_run_output_dir,
    report_filename_for_case,
)
from lingxing_chatbi_check.cases.models import (
    AuthSpec,
    CaseSpec,
    CompareSpec,
    DatabaseSpec,
    ScopeSpec,
    ToolSpec,
)


def test_create_run_output_dir_uses_timestamp(tmp_path: Path) -> None:
    output_dir = create_run_output_dir(
        tmp_path,
        now=datetime(2026, 8, 14, 14, 35, 20),
    )

    assert output_dir == tmp_path / "2026-08-14_14-35-20"
    assert output_dir.exists()


def test_report_filename_for_case_uses_tool_and_table() -> None:
    case = CaseSpec(
        name="广告关键词",
        enabled=True,
        auth=AuthSpec(mode="all_users"),
        scope=ScopeSpec(shop_discovery="ad_auth_shops"),
        tool=ToolSpec(name="ad_campaign_keyword_report"),
        database=DatabaseSpec(table="chatbi.sp_keyword_report", sql="select 1"),
        compare=CompareSpec(dimensions=["sid"], metrics=["cost"]),
    )

    assert (
        report_filename_for_case(case)
        == "ad_campaign_keyword_report__chatbi.sp_keyword_report.xlsx"
    )
