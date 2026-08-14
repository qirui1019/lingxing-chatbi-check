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
                "auth": {"user_key": "user_a"},
                "tool": {
                    "name": "get_sales_summary",
                    "arguments": {
                        "start_date": "2026-08-01",
                        "end_date": "2026-08-07",
                        "shop_id": "shop_001",
                    },
                },
                "database": {
                    "table": "ads_sales_day",
                    "sql": "select * from ads_sales_day where shop_id = :shop_id",
                    "params": {"shop_id": "shop_001"},
                },
                "compare": {
                    "dimensions": ["shop_id", "date", "sku"],
                    "metrics": ["sales_amount", "order_count"],
                    "tolerance": 0.01,
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    case = load_case(case_path)

    assert case.name == "sales day check"
    assert case.auth.user_key == "user_a"
    assert case.tool.name == "get_sales_summary"
    assert case.tool.arguments["shop_id"] == "shop_001"
    assert case.database.table == "ads_sales_day"
    assert case.database.params == {"shop_id": "shop_001"}
    assert case.compare.dimensions == ["shop_id", "date", "sku"]
    assert case.compare.metrics == ["sales_amount", "order_count"]
    assert case.compare.tolerance == 0.01


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
