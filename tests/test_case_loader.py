from pathlib import Path

import pytest
import yaml


def test_load_case_reads_tool_database_compare_and_auth(tmp_path: Path) -> None:
    from lingxing_chatbi_check.cases.loader import load_case

    case_path = tmp_path / "sales__ads_sales_day.yml"
    case_path.write_text(
        yaml.safe_dump(
            {
                "name": "sales day check",
                "enabled": True,
                "auth": {"mode": "all_users"},
                "scope": {
                    "shop_discovery": "get_my_sids",
                    "listing_mapping": "erp_listing",
                },
                "tool": {
                    "name": "get_sales_summary",
                    "arguments": {
                        "start_date": "2026-08-01",
                        "end_date": "2026-08-07",
                    },
                    "dynamic_arguments": {
                        "shop_argument": "sids",
                        "shop_batch_mode": "list",
                        "source_field": "sid",
                        "database_source_field": "sid",
                    },
                    "pagination": {
                        "enabled": True,
                        "page_argument": "page",
                        "page_start": 1,
                        "page_size_argument": "length",
                        "page_size": 500,
                        "max_pages": 10,
                    },
                },
                "database": {
                    "table": "ads_sales_day",
                    "sql": "select * from ads_sales_day where sid in :sid_values",
                    "params": {"start_date": "2026-08-01"},
                },
                "compare": {
                    "dimensions": ["shop_id", "date", "sku"],
                    "metrics": ["sales_amount", "order_count"],
                    "dimension_mappings": {"profile_id": "shop_id"},
                    "metric_mappings": {"spends": "sales_amount"},
                    "tolerance": 0.01,
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    case = load_case(case_path)

    assert case.name == "sales day check"
    assert case.enabled is True
    assert case.auth.mode == "all_users"
    assert case.scope.shop_discovery == "get_my_sids"
    assert case.scope.listing_mapping == "erp_listing"
    assert case.tool.name == "get_sales_summary"
    assert case.tool.arguments["start_date"] == "2026-08-01"
    assert case.tool.dynamic_arguments.shop_argument == "sids"
    assert case.tool.dynamic_arguments.shop_batch_mode == "list"
    assert case.tool.dynamic_arguments.source_field == "sid"
    assert case.tool.dynamic_arguments.database_source_field == "sid"
    assert case.tool.pagination is not None
    assert case.tool.pagination.enabled is True
    assert case.tool.pagination.page_argument == "page"
    assert case.tool.pagination.page_start == 1
    assert case.tool.pagination.page_size_argument == "length"
    assert case.tool.pagination.page_size == 500
    assert case.tool.pagination.max_pages == 10
    assert case.database.table == "ads_sales_day"
    assert case.database.params == {"start_date": "2026-08-01"}
    assert case.compare.dimensions == ["shop_id", "date", "sku"]
    assert case.compare.metrics == ["sales_amount", "order_count"]
    assert case.compare.dimension_mappings == {"profile_id": "shop_id"}
    assert case.compare.metric_mappings == {"spends": "sales_amount"}
    assert case.compare.tolerance == 0.01


def test_load_case_keeps_backward_compatible_default_user_key(tmp_path: Path) -> None:
    from lingxing_chatbi_check.cases.loader import load_case

    case_path = tmp_path / "legacy.yml"
    case_path.write_text(
        yaml.safe_dump(
            {
                "auth": {"user_key": "user_a"},
                "tool": {"name": "legacy_tool"},
                "database": {"table": "legacy_table", "sql": "select 1"},
                "compare": {"dimensions": ["sid"], "metrics": ["amount"]},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    case = load_case(case_path)

    assert case.auth.mode == "single_user"
    assert case.auth.user_key == "user_a"


def test_load_case_reads_database_source_field(tmp_path: Path) -> None:
    from lingxing_chatbi_check.cases.loader import load_case

    case_path = tmp_path / "ads.yml"
    case_path.write_text(
        yaml.safe_dump(
            {
                "tool": {
                    "name": "ad_campaign_keyword_report",
                    "dynamic_arguments": {
                        "shop_argument": "profile_ids",
                        "shop_batch_mode": "list",
                        "source_field": "profile_id",
                        "database_source_field": "sid",
                        "database_param": "sid_values",
                    },
                },
                "database": {
                    "table": "chatbi.sp_keyword_report",
                    "sql": "select 1",
                },
                "compare": {"dimensions": ["sid"], "metrics": ["cost"]},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    case = load_case(case_path)

    assert case.tool.dynamic_arguments.source_field == "profile_id"
    assert case.tool.dynamic_arguments.database_source_field == "sid"
    assert case.tool.dynamic_arguments.database_param == "sid_values"


def test_load_cases_reads_yml_and_yaml_files(tmp_path: Path) -> None:
    from lingxing_chatbi_check.cases.loader import load_cases

    base_case = {
        "tool": {"name": "tool_a"},
        "database": {"table": "table_a", "sql": "select 1"},
        "compare": {"dimensions": ["sid"], "metrics": ["amount"]},
    }
    (tmp_path / "a.yml").write_text(
        yaml.safe_dump({**base_case, "name": "a"}, allow_unicode=True),
        encoding="utf-8",
    )
    (tmp_path / "b.yaml").write_text(
        yaml.safe_dump({**base_case, "name": "b"}, allow_unicode=True),
        encoding="utf-8",
    )

    cases = load_cases(tmp_path)

    assert [case.name for case in cases] == ["a", "b"]


def test_sales_cases_compare_by_sid_asin_and_report_date() -> None:
    from lingxing_chatbi_check.cases.loader import load_case

    repo_root = Path(__file__).resolve().parents[1]
    for case_name in (
        "query_product_performance_asin_lists__chatbi.sale_report_asin.yml",
        "query_product_performance_asin_lists__chatbi.sale_report_msku_order.yml",
    ):
        case = load_case(repo_root / "configs" / "cases" / case_name)

        assert case.tool.dynamic_arguments.shop_argument == "sids"
        assert case.tool.dynamic_arguments.shop_batch_mode == "list"
        assert case.tool.dynamic_arguments.batch_size == 2
        assert case.tool.pagination is not None
        assert case.tool.pagination.page_argument == "offset"
        assert case.tool.pagination.page_start == 0
        assert case.tool.pagination.page_size_argument == "length"
        assert case.tool.pagination.page_value_mode == "offset"
        assert case.compare.dimensions == ["sid", "asin", "report_date"]
        assert case.compare.dimension_mappings == {
            "sid": "sid",
            "asin": "asin",
            "report_date": "report_date",
        }
        assert ":report_date as report_date" in case.database.sql
        expected_report_date = (
            f"{case.tool.arguments['start_date']} - {case.tool.arguments['end_date']}"
        )
        assert case.tool.arguments["currency_code"] == ""
        assert case.database.params["report_date"] == expected_report_date
        assert "sid" in case.database.sql
        assert "asin" in case.database.sql
        assert "group by" in case.database.sql.lower()


def test_sale_report_asin_uses_latest_day_for_rank_star_and_reviews() -> None:
    from lingxing_chatbi_check.cases.loader import load_case

    repo_root = Path(__file__).resolve().parents[1]
    case = load_case(
        repo_root
        / "configs"
        / "cases"
        / "query_product_performance_asin_lists__chatbi.sale_report_asin.yml"
    )

    sql = case.database.sql
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


def test_sale_report_msku_order_disables_inventory_snapshot_fields() -> None:
    from lingxing_chatbi_check.cases.loader import load_case

    repo_root = Path(__file__).resolve().parents[1]
    case = load_case(
        repo_root
        / "configs"
        / "cases"
        / "query_product_performance_asin_lists__chatbi.sale_report_msku_order.yml"
    )

    sql = case.database.sql
    assert "row_number() over" not in sql.lower()
    assert "latest." not in sql
    assert "sum(afn_fulfillable_quantity)" not in sql
    assert "sum(reserved_fc_transfers)" not in sql
    assert "sum(reserved_fc_processing)" not in sql
    assert "sum(afn_inbound_receiving_quantity)" not in sql
    disabled_fields = {
        "afn_fulfillable_quantity",
        "reserved_fc_transfers",
        "reserved_fc_processing",
        "afn_inbound_receiving_quantity",
    }
    assert disabled_fields.isdisjoint(case.compare.metrics)
    assert disabled_fields.isdisjoint(case.compare.metric_mappings)
    assert case.compare.metric_dimension_mappings == {}


def test_profit_report_msku_case_compares_by_sid_msku_and_month() -> None:
    from lingxing_chatbi_check.cases.loader import load_case

    repo_root = Path(__file__).resolve().parents[1]
    case = load_case(repo_root / "configs" / "cases" / "get_profit_report_msku.yaml")

    assert case.name == "get_profit_report_msku vs chatbi.sale_report_msku_settlement"
    assert case.scope.shop_discovery == "get_my_sids"
    assert case.scope.listing_mapping == "erp_listing"
    assert case.tool.name == "get_profit_report_msku"
    assert "startDate" in case.tool.arguments
    assert "endDate" in case.tool.arguments
    assert case.tool.dynamic_arguments.shop_argument is None
    assert case.tool.dynamic_arguments.shop_batch_mode == "none"
    assert case.tool.dynamic_arguments.database_param == "sid_values"
    assert case.tool.pagination is not None
    assert case.tool.pagination.page_argument == "current"
    assert case.tool.pagination.page_start == 1
    assert case.tool.pagination.page_size_argument == "size"
    assert case.tool.pagination.batch_timeout_seconds is None
    assert case.database.table == "chatbi.sale_report_msku_settlement"
    assert "date_format(settlement_date, '%Y-%m') as settlement_date" in case.database.sql
    assert "settlement_date between :settlement_start_date and :settlement_end_date" in case.database.sql
    assert case.compare.dimensions == ["sid", "msku", "reportDateMonth"]
    assert case.compare.dimension_mappings == {
        "sid": "sid",
        "msku": "msku",
        "reportDateMonth": "settlement_date",
    }
    assert {
        "totalSalesAmount": "settlement_sales_amount",
        "totalSalesQuantity": "settlement_units",
        "grossProfit": "settlement_gross_profit",
    }.items() <= case.compare.metric_mappings.items()


def test_ad_cases_compare_by_sid_and_report_date() -> None:
    from lingxing_chatbi_check.cases.loader import load_case

    repo_root = Path(__file__).resolve().parents[1]
    for case_name in (
        "ad_campaign_keyword_report__chatbi.sp_keyword_report.yml",
        "ad_campaign_search_term_report__chatbi.sp_search_term_report.yml",
        "ad_campaign_targeting_report__chatbi.sp_target_report.yml",
    ):
        case = load_case(repo_root / "configs" / "cases" / case_name)

        assert case.compare.dimensions == ["sid", "report_date"]
        assert case.compare.dimension_mappings == {
            "sid": "sid",
            "report_date": "report_date",
        }
        assert ":report_date as report_date" in case.database.sql
        assert case.database.params["report_date"] == case.tool.arguments["report_date"]
        start_date, end_date = str(case.tool.arguments["report_date"]).split(" - ")
        assert case.database.params["report_start_date"] == start_date
        assert case.database.params["report_end_date"] == end_date


def test_mcp_user_config_contains_key_without_shop_binding() -> None:
    from lingxing_chatbi_check.config import get_mcp_user_config

    config = {
        "lingxing_mcp": {
            "users": {
                "user_a": {
                    "x_mcp_key": "secret-key",
                }
            }
        }
    }

    user_config = get_mcp_user_config(config, "user_a")

    assert user_config == {"x_mcp_key": "secret-key"}
    assert "shops" not in user_config


def test_mcp_user_config_raises_for_unknown_alias() -> None:
    from lingxing_chatbi_check.config import get_mcp_user_config

    with pytest.raises(KeyError, match="user_a"):
        get_mcp_user_config({"lingxing_mcp": {"users": {}}}, "user_a")
