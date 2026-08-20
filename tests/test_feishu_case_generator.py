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

    assert case_data["tool"]["dynamic_arguments"] == {
        "shop_argument": "profile_ids",
        "shop_batch_mode": "list",
        "source_field": "profile_id",
        "database_source_field": "sid",
        "batch_size": 3,
        "database_param": "sid_values",
    }
    assert case_data["database"]["params"] == {
        "report_date": "2026-06-01 - 2026-06-30",
        "report_start_date": "2026-06-01",
        "report_end_date": "2026-06-30",
    }
    assert case_data["compare"]["dimensions"] == ["sid", "report_date"]
    assert case_data["compare"]["dimension_mappings"] == {
        "sid": "sid",
        "report_date": "report_date",
    }
    assert case_data["compare"]["metric_mappings"] == {
        "spends": "cost",
        "sales": "sales",
        "impressions": "impressions",
    }
    assert ":report_date as report_date" in case_data["database"]["sql"]
    assert "sum(cost) as cost" in case_data["database"]["sql"]
    assert "where sid in :sid_values" in case_data["database"]["sql"]
    assert "report_date between :report_start_date and :report_end_date" in case_data["database"]["sql"]
    assert "group by\n  sid" in case_data["database"]["sql"]
    assert case_data["notes"]["inactive_dimensions"] == ["campaign_id"]


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

    assert case_data["tool"]["dynamic_arguments"]["shop_argument"] == "sids"
    assert case_data["tool"]["dynamic_arguments"]["shop_batch_mode"] == "list"
    assert case_data["tool"]["dynamic_arguments"]["batch_size"] == 2
    assert case_data["tool"]["pagination"] == {
        "enabled": True,
        "page_argument": "offset",
        "page_start": 0,
        "page_size_argument": "length",
        "page_size": 1000,
        "max_pages": 1000,
        "page_value_mode": "offset",
    }
    assert case_data["compare"]["dimensions"] == ["sid", "asin", "report_date"]
    assert case_data["compare"]["dimension_mappings"] == {
        "sid": "sid",
        "asin": "asin",
        "report_date": "report_date",
    }
    assert ":report_date as report_date" in case_data["database"]["sql"]
    assert case_data["database"]["params"]["report_date"] == "2026-06-01 - 2026-06-30"
    assert "report_date between :start_date and :end_date" in case_data["database"]["sql"]


def test_build_case_template_maps_search_term_target_id_from_keyword_or_target() -> None:
    from lingxing_chatbi_check.feishu.case_generator import (
        AvailableToolRow,
        build_case_template,
    )

    case_data = build_case_template(
        AvailableToolRow(
            category="广告",
            tool="ad_campaign_search_term_report",
            required_arguments="profile_ids\nreport_date",
            optional_arguments="",
            test_arguments="profile_ids=[\"p1\"]\nreport_date=2026-06-01 - 2026-06-30",
            output_fields="spends",
            dimensions="sid(领星中是profile_id)\n+ campaign_id\n+ ad_group_id\n+ target_id（领星中是keyword_id / target_id ）\n+ query\n+ report_date",
            database_table="chatbi.sp_search_term_report",
            database_fields="cost",
        )
    )

    assert case_data["compare"]["dimensions"] == ["sid", "report_date"]
    assert case_data["compare"]["dimension_mappings"] == {
        "sid": "sid",
        "report_date": "report_date",
    }
    assert case_data["notes"]["inactive_dimensions"] == [
        "campaign_id",
        "ad_group_id",
        "target_id",
        "query",
    ]


def test_build_case_template_keeps_sponsored_type_as_tool_only_filter() -> None:
    from lingxing_chatbi_check.feishu.case_generator import (
        AvailableToolRow,
        build_case_template,
    )

    case_data = build_case_template(
        AvailableToolRow(
            category="广告",
            tool="ad_campaign_search_term_report",
            required_arguments="profile_ids\nreport_date",
            optional_arguments="",
            test_arguments="report_date=2026-06-01 - 2026-06-30",
            output_fields="spends",
            dimensions=(
                "sid(领星中是profile_id)\n"
                "+ campaign_id\n"
                "+ ad_group_id\n"
                "+ target_id\n"
                "+ query\n"
                "+ report_date\n"
                "(+sponsored_type=sp 领星中查询时需要加上这个筛选条件)"
            ),
            database_table="chatbi.sp_search_term_report",
            database_fields="cost",
        )
    )

    assert case_data["tool"]["arguments"]["sponsored_type"] == "sp"
    assert "sponsored_type" not in case_data["database"]["params"]
    assert "sponsored_type" not in case_data["database"]["sql"]


def test_build_case_template_adds_pagination_when_tool_supports_page_and_length() -> None:
    from lingxing_chatbi_check.feishu.case_generator import (
        AvailableToolRow,
        build_case_template,
    )

    case_data = build_case_template(
        AvailableToolRow(
            category="广告",
            tool="ad_campaign_search_term_report",
            required_arguments="profile_ids\nreport_date",
            optional_arguments="query\npage\nlength",
            test_arguments="report_date=2026-06-01 - 2026-06-30",
            output_fields="spends",
            dimensions="sid\n+ campaign_id\n+ report_date",
            database_table="chatbi.sp_search_term_report",
            database_fields="cost",
        )
    )

    assert case_data["tool"]["pagination"] == {
        "enabled": True,
        "page_argument": "page",
        "page_start": 1,
        "page_size_argument": "length",
        "page_size": 500,
        "max_pages": 1000,
    }


def test_build_case_template_keeps_fba_metric_order_after_reserved_quantity() -> None:
    from lingxing_chatbi_check.feishu.case_generator import (
        AvailableToolRow,
        build_case_template,
    )

    case_data = build_case_template(
        AvailableToolRow(
            category="库存",
            tool="get_fba_stock_list",
            required_arguments="length",
            optional_arguments="sid",
            test_arguments="fulfillment_channel_type=FBA",
            output_fields="total_fulfillable_quantity\nafn_fulfillable_quantity\nafn_reserved_quantity\nreserved_fc_transfers\nreserved_fc_processing\nreserved_customerorders\nreal_transit_quantity\nafn_inbound_receiving_quantity",
            dimensions="sid\n+ msku（领星中是seller_sku ）\n+ fnsku",
            database_table="chatbi.fba_list",
            database_fields="total_fulfillable_quantity\nafn_fulfillable_quantity\nafn_reserved_quantity\nreserved_fc_transfers\nreserved_fc_processing\nreserved_customerorders\nafn_erp_real_shipped_quantity\nafn_inbound_receiving_quantity",
        )
    )

    assert case_data["compare"]["metric_mappings"] == {
        "total_fulfillable_quantity": "total_fulfillable_quantity",
        "afn_fulfillable_quantity": "afn_fulfillable_quantity",
        "afn_reserved_quantity": "afn_reserved_quantity",
        "reserved_fc_transfers": "reserved_fc_transfers",
        "reserved_fc_processing": "reserved_fc_processing",
        "reserved_customerorders": "reserved_customerorders",
        "real_transit_quantity": "afn_erp_real_shipped_quantity",
        "afn_inbound_receiving_quantity": "afn_inbound_receiving_quantity",
    }


def test_build_case_template_splits_multiple_output_fields_on_one_line() -> None:
    from lingxing_chatbi_check.feishu.case_generator import (
        AvailableToolRow,
        build_case_template,
    )

    case_data = build_case_template(
        AvailableToolRow(
            category="库存",
            tool="get_fba_stock_list",
            required_arguments="length",
            optional_arguments="sid",
            test_arguments="fulfillment_channel_type=FBA",
            output_fields=(
                "afn_fulfillable_quantity afn_reserved_quantity\n"
                "reserved_fc_processing reserved_customerorders"
            ),
            dimensions="sid",
            database_table="chatbi.fba_list",
            database_fields=(
                "afn_fulfillable_quantity\n"
                "afn_reserved_quantity\n"
                "reserved_fc_processing\n"
                "reserved_customerorders"
            ),
        )
    )

    assert case_data["compare"]["metric_mappings"] == {
        "afn_fulfillable_quantity": "afn_fulfillable_quantity",
        "afn_reserved_quantity": "afn_reserved_quantity",
        "reserved_fc_processing": "reserved_fc_processing",
        "reserved_customerorders": "reserved_customerorders",
    }


def test_build_case_template_ignores_field_names_inside_descriptions() -> None:
    from lingxing_chatbi_check.feishu.case_generator import (
        AvailableToolRow,
        build_case_template,
    )

    case_data = build_case_template(
        AvailableToolRow(
            category="销售",
            tool="query_product_performance_asin_lists",
            required_arguments="length",
            optional_arguments="sids\nstart_date\nend_date",
            test_arguments=(
                "start_date=2026-06-01\n"
                "end_date=2026-06-30\n"
                "sid=508344\n"
                "date_type=purchase\n"
                "summary_field=asin\n"
                "turn_on_summary=1"
            ),
            output_fields=(
                "volume 销量（总件数，FBA+FBM）\n"
                "amount\n"
                "net_amount\n"
                "promotion_discount"
            ),
            dimensions="sid\n+asin\n+report_date(领星中是start_date+end_date)",
            database_table="chatbi.sale_report_msku_order",
            database_fields=(
                "order_units\n"
                "order_sales_amount\n"
                "order_promotion_discount\n"
                "order_net_sales_amount"
            ),
        )
    )

    assert case_data["compare"]["metric_mappings"] == {
        "volume": "order_units",
        "amount": "order_sales_amount",
        "promotion_discount": "order_promotion_discount",
        "net_amount": "order_net_sales_amount",
    }


def test_build_case_template_uses_latest_day_fields_for_sale_report_asin() -> None:
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
            test_arguments=(
                "start_date=2026-06-01\n"
                "end_date=2026-06-30\n"
                "date_type=purchase\n"
                "summary_field=asin\n"
                "turn_on_summary=1"
            ),
            output_fields=(
                "cate_rank\n"
                "avg_star\n"
                "reviews_count\n"
                "sessions_total\n"
                "page_views_total"
            ),
            dimensions="sid\n+asin\n+report_date(领星中是start_date+end_date)",
            database_table="chatbi.sale_report_asin",
            database_fields=(
                "cate_rank\n"
                "avg_star\n"
                "reviews_count\n"
                "sessions_total\n"
                "page_views_total"
            ),
        )
    )

    sql = case_data["database"]["sql"]
    assert "row_number() over" in sql.lower()
    assert "order by report_date desc" in sql.lower()
    assert "latest.cate_rank as cate_rank" in sql
    assert "latest.avg_star as avg_star" in sql
    assert "latest.reviews_count as reviews_count" in sql
    assert "sum(cate_rank)" not in sql
    assert "sum(avg_star)" not in sql
    assert "sum(reviews_count)" not in sql
    assert "sum(sessions_total) as sessions_total" in sql
    assert "sum(page_views_total) as page_views_total" in sql


def test_build_case_template_uses_valid_sql_for_empty_result_cases() -> None:
    from lingxing_chatbi_check.feishu.case_generator import (
        AvailableToolRow,
        build_case_template,
    )

    case_data = build_case_template(
        AvailableToolRow(
            category="销售",
            tool="query_product_performance_asin_lists",
            required_arguments="length",
            optional_arguments="sids\nstart_date\nend_date",
            test_arguments="start_date=2026-06-01\nend_date=2026-06-30\nsid=508344",
            output_fields="查询结果为空",
            dimensions="/",
            database_table="chatbi.sale_report_msku_settlement",
            database_fields="/",
        )
    )

    assert "select\n  *" in case_data["database"]["sql"]
    assert "group by" not in case_data["database"]["sql"]
