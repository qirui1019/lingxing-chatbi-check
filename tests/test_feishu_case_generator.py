from pathlib import Path

from openpyxl import Workbook

from lingxing_chatbi_check.feishu.case_generator import load_available_tool_rows


def test_load_available_tool_rows_forward_fills_tool_for_continuation_rows(
    tmp_path: Path,
) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "可用tool"
    sheet.append(
        [
            "表格类型",
            "Tool",
            "Tool说明",
            "必填入参",
            "可选入参",
            "实际测试入参",
            "出参字段",
            "聚合维度",
            "对应数据库",
            "对应数据库字段",
        ]
    )
    sheet.append(
        [
            "销售",
            "query_product_performance_asin_lists",
            "说明",
            "length\noffset",
            "sids\nstart_date\nend_date",
            "start_date=2026-06-01\nend_date=2026-06-30",
            "amount",
            "sid\n+asin",
            "chatbi.sale_report_msku_order",
            "order_sales_amount",
        ]
    )
    sheet.append(
        [
            None,
            None,
            None,
            None,
            None,
            "start_date=2026-06-01\nend_date=2026-06-30",
            "rank_category",
            "sid\n+asin",
            "chatbi.sale_report_asin",
            "rank_category",
        ]
    )
    path = tmp_path / "tools.xlsx"
    workbook.save(path)

    rows = load_available_tool_rows(path)

    assert [row.tool for row in rows] == [
        "query_product_performance_asin_lists",
        "query_product_performance_asin_lists",
    ]
    assert [row.database_table for row in rows] == [
        "chatbi.sale_report_msku_order",
        "chatbi.sale_report_asin",
    ]


def test_build_case_template_maps_tool_and_database_fields_by_order() -> None:
    from lingxing_chatbi_check.feishu.case_generator import (
        AvailableToolRow,
        build_case_template,
    )

    case_data = build_case_template(
        AvailableToolRow(
            category="广告",
            tool="ad_campaign_keyword_report",
            required_arguments="profile_ids\nreport_date",
            optional_arguments="",
            test_arguments="report_date=2026-06-01 - 2026-06-30",
            output_fields="spends（花费）\nsales\nimpressions",
            dimensions="sid(领星中是profile_id)\n+campaign_id\n+report_date",
            database_table="chatbi.sp_keyword_report",
            database_fields="cost\nsales\nimpressions",
        )
    )

    assert case_data["compare"]["dimension_mappings"] == {
        "profile_id": "sid",
        "campaign_id": "campaign_id",
        "report_date": "report_date",
    }
    assert case_data["compare"]["metric_mappings"] == {
        "spends": "cost",
        "sales": "sales",
        "impressions": "impressions",
    }


def test_build_case_template_does_not_treat_date_range_note_as_output_field() -> None:
    from lingxing_chatbi_check.feishu.case_generator import (
        AvailableToolRow,
        build_case_template,
    )

    case_data = build_case_template(
        AvailableToolRow(
            category="销售",
            tool="query_product_performance_asin_lists",
            required_arguments="length\noffset",
            optional_arguments="sids\nstart_date\nend_date",
            test_arguments="start_date=2026-06-01\nend_date=2026-06-30",
            output_fields="amount",
            dimensions="sid\n+asin\n+report_date(领星中是start_date+end_date)",
            database_table="chatbi.sale_report_msku_order",
            database_fields="order_sales_amount",
        )
    )

    assert case_data["compare"]["dimension_mappings"] == {
        "sid": "sid",
        "asin": "asin",
        "report_date": "report_date",
    }
