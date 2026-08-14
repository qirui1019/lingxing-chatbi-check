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
