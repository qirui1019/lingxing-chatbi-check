import pandas as pd


def test_compare_dataframes_passes_when_metrics_match() -> None:
    from lingxing_chatbi_check.comparators.dataframe_compare import compare_dataframes

    tool_df = pd.DataFrame(
        [{"shop_id": "shop_001", "date": "2026-08-01", "sales_amount": 12.34}]
    )
    db_df = pd.DataFrame(
        [{"shop_id": "shop_001", "date": "2026-08-01", "sales_amount": 12.34}]
    )

    result = compare_dataframes(
        tool_df,
        db_df,
        dimensions=["shop_id", "date"],
        metrics=["sales_amount"],
    )

    assert result.passed is True
    assert result.summary["failed_rows"] == 0


def test_compare_dataframes_reports_metric_mismatch() -> None:
    from lingxing_chatbi_check.comparators.dataframe_compare import compare_dataframes

    tool_df = pd.DataFrame(
        [{"shop_id": "shop_001", "date": "2026-08-01", "sales_amount": 12.34}]
    )
    db_df = pd.DataFrame(
        [{"shop_id": "shop_001", "date": "2026-08-01", "sales_amount": 10.0}]
    )

    result = compare_dataframes(
        tool_df,
        db_df,
        dimensions=["shop_id", "date"],
        metrics=["sales_amount"],
        tolerance=0.01,
    )

    assert result.passed is False
    assert result.summary["failed_rows"] == 1
    assert result.details.loc[0, "sales_amount__sales_amount_passed"] is False
    assert result.details.loc[0, "sales_amount__sales_amount_diff"] == 2.34


def test_compare_dataframes_uses_tool_to_database_field_mappings() -> None:
    from lingxing_chatbi_check.comparators.dataframe_compare import compare_dataframes

    tool_df = pd.DataFrame(
        [
            {
                "profile_id": "p001",
                "report_date": "2026-06-01",
                "spends": 12.34,
            }
        ]
    )
    db_df = pd.DataFrame(
        [
            {
                "sid": "p001",
                "report_date": "2026-06-01",
                "cost": 12.34,
            }
        ]
    )

    result = compare_dataframes(
        tool_df,
        db_df,
        dimension_mappings={"profile_id": "sid", "report_date": "report_date"},
        metric_mappings={"spends": "cost"},
    )

    assert result.passed is True
    assert result.details.loc[0, "profile_id"] == "p001"
    assert result.details.loc[0, "tool.spends"] == 12.34
    assert result.details.loc[0, "db.cost"] == 12.34
    assert result.details.loc[0, "spends__cost_passed"] is True
