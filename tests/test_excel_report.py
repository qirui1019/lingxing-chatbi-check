from pathlib import Path

from openpyxl import load_workbook
import pandas as pd

from lingxing_chatbi_check.comparators.dataframe_compare import compare_dataframes
from lingxing_chatbi_check.reports.excel_report import (
    write_excel_report,
    write_metric_report_files,
    write_run_log,
)


def test_excel_report_writes_metric_sheets_and_metric_summary(tmp_path: Path) -> None:
    result = compare_dataframes(
        tool_df=pd.DataFrame(
            [
                {"sid": "101", "report_date": "2026-06-01 - 2026-06-30", "spends": 5},
                {"sid": "102", "report_date": "2026-06-01 - 2026-06-30", "spends": 9},
            ]
        ),
        db_df=pd.DataFrame(
            [
                {"sid": "101", "report_date": "2026-06-01 - 2026-06-30", "cost": 5},
                {"sid": "102", "report_date": "2026-06-01 - 2026-06-30", "cost": 7},
            ]
        ),
        dimensions=["sid", "report_date"],
        metric_mappings={"spends": "cost"},
    )

    report_path = write_excel_report(
        tmp_path / "report.xlsx",
        result,
        context={
            "tool_query_seconds": 1.2,
            "db_query_seconds": 0.3,
            "total_query_seconds": 1.5,
        },
    )

    workbook = pd.ExcelFile(report_path)
    assert workbook.sheet_names == ["summary", "context", "metric_spends"]

    summary = pd.read_excel(report_path, sheet_name="summary")
    assert summary.to_dict("records") == [
        {
            "metric": "spends",
            "tool_field": "spends",
            "db_field": "cost",
            "tool_query_seconds": 1.2,
            "db_query_seconds": 0.3,
            "total_query_seconds": 1.5,
            "total_rows": 2,
            "failed_rows": 1,
            "tool_only_rows": 0,
            "db_only_rows": 0,
            "passed": False,
        }
    ]

    metric = pd.read_excel(report_path, sheet_name="metric_spends")
    assert metric.columns.to_list() == [
        "sid",
        "report_date",
        "tool.spends",
        "db.cost",
        "diff",
        "passed",
    ]
    assert metric["passed"].to_list() == [False, True]


def test_metric_report_writer_creates_one_workbook_per_metric(tmp_path: Path) -> None:
    result = compare_dataframes(
        tool_df=pd.DataFrame(
            [
                {"sid": "101", "report_date": "2026-06-01 - 2026-06-30", "spends": 10, "sales": 50},
                {"sid": "102", "report_date": "2026-06-01 - 2026-06-30", "spends": 9, "sales": 30},
                {"sid": "103", "report_date": "2026-06-01 - 2026-06-30", "spends": 4, "sales": 0},
            ]
        ),
        db_df=pd.DataFrame(
            [
                {"sid": "101", "report_date": "2026-06-01 - 2026-06-30", "cost": 5, "sales": 50},
                {"sid": "102", "report_date": "2026-06-01 - 2026-06-30", "cost": 8, "sales": 20},
                {"sid": "103", "report_date": "2026-06-01 - 2026-06-30", "cost": 0, "sales": 0},
            ]
        ),
        dimensions=["sid", "report_date"],
        metric_mappings={"spends": "cost", "sales": "sales"},
    )

    write_result = write_metric_report_files(
        tmp_path,
        result,
        context={
            "case_name": "ad_campaign_search_term_report vs chatbi.sp_search_term_report",
            "tool_name": "ad_campaign_search_term_report",
            "table_name": "chatbi.sp_search_term_report",
            "period_label": "2026年6月",
            "query_time": "2026.08.17",
        },
    )

    report_names = [path.name for path in write_result.paths]
    assert report_names == [
        "search_term_cost_2026年6月.xlsx",
        "search_term_sales_2026年6月.xlsx",
    ]

    cost = pd.read_excel(tmp_path / "search_term_cost_2026年6月.xlsx")
    assert cost.columns.to_list() == [
        "sid",
        "tool.spends",
        "db.cost",
        "diff",
        "diff_rate",
    ]
    assert cost["sid"].astype(str).to_list() == ["101", "103", "102"]
    assert cost["diff"].to_list() == [5, 4, 1]
    assert cost["diff_rate"].to_list() == [1, 1, 0.125]
    workbook = load_workbook(tmp_path / "search_term_cost_2026年6月.xlsx")
    sheet = workbook.active
    assert sheet["E2"].number_format == "0.00%"

    assert write_result.log_rows == [
        {
            "case_name": "ad_campaign_search_term_report vs chatbi.sp_search_term_report",
            "tool_name": "ad_campaign_search_term_report",
            "table_name": "chatbi.sp_search_term_report",
            "metric": "cost",
            "tool_field": "spends",
            "db_field": "cost",
            "report_file": "search_term_cost_2026年6月.xlsx",
            "query_time": "2026.08.17",
            "result_count": 3,
            "exception_count": 3,
        },
        {
            "case_name": "ad_campaign_search_term_report vs chatbi.sp_search_term_report",
            "tool_name": "ad_campaign_search_term_report",
            "table_name": "chatbi.sp_search_term_report",
            "metric": "sales",
            "tool_field": "sales",
            "db_field": "sales",
            "report_file": "search_term_sales_2026年6月.xlsx",
            "query_time": "2026.08.17",
            "result_count": 3,
            "exception_count": 1,
        },
    ]


def test_metric_report_writer_marks_uncomputable_nonzero_diff_rate_as_100_percent(
    tmp_path: Path,
) -> None:
    result = compare_dataframes(
        tool_df=pd.DataFrame(
            [
                {"sid": "101", "spends": 5},
                {"sid": "102", "spends": None},
                {"sid": "103", "spends": None},
                {"sid": "104", "spends": 0},
            ]
        ),
        db_df=pd.DataFrame(
            [
                {"sid": "101", "cost": None},
                {"sid": "102", "cost": 5},
                {"sid": "103", "cost": 0},
                {"sid": "104", "cost": 0},
            ]
        ),
        dimensions=["sid"],
        metric_mappings={"spends": "cost"},
    )

    write_result = write_metric_report_files(
        tmp_path,
        result,
        context={
            "case_name": "ad",
            "tool_name": "ad_campaign_keyword_report",
            "table_name": "chatbi.sp_keyword_report",
            "period_label": "2026年6月",
        },
    )

    table = pd.read_excel(write_result.paths[0])
    rates_by_sid = {
        str(row["sid"]): row["diff_rate"]
        for row in table.to_dict("records")
    }
    assert rates_by_sid["101"] == 1
    assert rates_by_sid["102"] == 1
    assert pd.isna(rates_by_sid["103"])
    assert pd.isna(rates_by_sid["104"])
    assert write_result.log_rows[0]["exception_count"] == 2


def test_run_log_writer_records_metric_rows(tmp_path: Path) -> None:
    log_path = write_run_log(
        tmp_path / "run_log.xlsx",
        [
            {
                "case_name": "case a",
                "metric": "cost",
                "result_count": 2,
                "exception_count": 1,
            }
        ],
    )

    log = pd.read_excel(log_path)
    assert log.to_dict("records") == [
        {
            "case_name": "case a",
            "metric": "cost",
            "result_count": 2,
            "exception_count": 1,
        }
    ]
