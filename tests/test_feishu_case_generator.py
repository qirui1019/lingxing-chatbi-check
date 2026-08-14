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
