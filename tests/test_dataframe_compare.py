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
    assert result.details.loc[0, "sales_amount_passed"] is False
    assert result.details.loc[0, "sales_amount_diff"] == 2.34
