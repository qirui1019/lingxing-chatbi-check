from datetime import datetime
from pathlib import Path

from lingxing_chatbi_check.runners.batch_runner import (
    create_run_output_dir,
    report_filename_for_case,
    run_cases,
)
from lingxing_chatbi_check.reports.excel_report import MetricReportWriteResult
from lingxing_chatbi_check.reports.feishu_uploader import FeishuUploadSummary
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


def test_run_cases_collects_metric_reports_and_writes_run_log(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import lingxing_chatbi_check.runners.batch_runner as batch_runner

    case = CaseSpec(
        name="ad search term",
        enabled=True,
        auth=AuthSpec(mode="all_users"),
        scope=ScopeSpec(shop_discovery="ad_auth_shops"),
        tool=ToolSpec(name="ad_campaign_search_term_report"),
        database=DatabaseSpec(table="chatbi.sp_search_term_report", sql="select 1"),
        compare=CompareSpec(dimensions=["sid"], metrics=["cost"]),
    )
    metric_path = tmp_path / "reports" / "search_term_cost_2026年6月.xlsx"

    monkeypatch.setattr(batch_runner, "load_env_config", lambda _path: {})
    monkeypatch.setattr(batch_runner, "load_cases", lambda _path: [case])
    monkeypatch.setattr(
        batch_runner,
        "create_run_output_dir",
        lambda reports_root: reports_root / "2026-08-17_14-00-00",
    )
    monkeypatch.setattr(
        batch_runner,
        "run_case",
        lambda _case, _env, _output_dir: MetricReportWriteResult(
            paths=[metric_path],
            log_rows=[
                {
                    "case_name": "ad search term",
                    "metric": "cost",
                    "result_count": 3,
                    "exception_count": 1,
                }
            ],
        ),
    )

    reports = run_cases(
        case_dir=tmp_path / "cases",
        env_config_path=tmp_path / "env.yml",
        reports_root=tmp_path / "reports",
    )

    assert reports == [
        metric_path,
        tmp_path / "reports" / "2026-08-17_14-00-00" / "run_log.xlsx",
    ]


def test_run_cases_uploads_feishu_after_report_generation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import lingxing_chatbi_check.runners.batch_runner as batch_runner

    case = CaseSpec(
        name="ad search term",
        enabled=True,
        auth=AuthSpec(mode="all_users"),
        scope=ScopeSpec(shop_discovery="ad_auth_shops"),
        tool=ToolSpec(name="ad_campaign_search_term_report"),
        database=DatabaseSpec(table="chatbi.sp_search_term_report", sql="select 1"),
        compare=CompareSpec(dimensions=["sid"], metrics=["cost"]),
    )
    output_dir = tmp_path / "reports" / "2026-08-17_14-00-00"
    metric_path = output_dir / "search_term_cost_2026年6月.xlsx"
    upload_calls = []

    monkeypatch.setattr(
        batch_runner,
        "load_env_config",
        lambda _path: {"feishu": {"sheet_id": "sheet123"}},
    )
    monkeypatch.setattr(batch_runner, "load_cases", lambda _path: [case])
    monkeypatch.setattr(
        batch_runner,
        "create_run_output_dir",
        lambda reports_root: output_dir,
    )
    monkeypatch.setattr(
        batch_runner,
        "run_case",
        lambda _case, _env, _output_dir: MetricReportWriteResult(
            paths=[metric_path],
            log_rows=[
                {
                    "case_name": "ad search term",
                    "metric": "cost",
                    "result_count": 3,
                    "exception_count": 1,
                }
            ],
        ),
    )
    def fake_upload_report_dir_to_feishu(report_dir, feishu_config):
        upload_calls.append((report_dir, feishu_config))
        return FeishuUploadSummary(
            matched_count=1,
            mapping_path=report_dir / "feishu_mapping.xlsx",
        )

    monkeypatch.setattr(
        batch_runner,
        "upload_report_dir_to_feishu",
        fake_upload_report_dir_to_feishu,
    )

    reports = run_cases(
        case_dir=tmp_path / "cases",
        env_config_path=tmp_path / "env.yml",
        reports_root=tmp_path / "reports",
        upload_feishu=True,
    )

    assert upload_calls == [(output_dir, {"sheet_id": "sheet123"})]
    assert reports[-1] == output_dir / "feishu_mapping.xlsx"
