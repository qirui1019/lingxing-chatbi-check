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


def test_compare_dataframes_normalizes_dimension_types_before_merge() -> None:
    from lingxing_chatbi_check.comparators.dataframe_compare import compare_dataframes

    tool_df = pd.DataFrame(
        [{"sid": "508344", "campaign_id": "123", "spends": 12.34}]
    )
    db_df = pd.DataFrame(
        [{"sid": 508344, "campaign_id": 123, "cost": 12.34}]
    )

    result = compare_dataframes(
        tool_df,
        db_df,
        dimensions=["sid", "campaign_id"],
        metric_mappings={"spends": "cost"},
    )

    assert result.passed is True
    assert result.summary["failed_rows"] == 0


def test_compare_dataframes_sums_tool_rows_before_comparing_grouped_database() -> None:
    from lingxing_chatbi_check.comparators.dataframe_compare import compare_dataframes

    tool_df = pd.DataFrame(
        [
            {"sid": "508278", "campaign_id": "c1", "keyword_id": "k1", "spends": "10"},
            {"sid": "508278", "campaign_id": "c1", "keyword_id": "k1", "spends": "5"},
        ]
    )
    db_df = pd.DataFrame(
        [{"sid": 508278, "campaign_id": "c1", "keyword_id": "k1", "cost": 15}]
    )

    result = compare_dataframes(
        tool_df,
        db_df,
        dimensions=["sid", "campaign_id", "keyword_id"],
        metric_mappings={"spends": "cost"},
    )

    assert result.passed is True
    assert result.summary["total_rows"] == 1
    assert result.details.loc[0, "tool.spends"] == 15


def test_compare_dataframes_builds_one_detail_frame_per_metric() -> None:
    from lingxing_chatbi_check.comparators.dataframe_compare import compare_dataframes

    result = compare_dataframes(
        tool_df=pd.DataFrame(
            [
                {
                    "sid": "101",
                    "report_date": "2026-06-01 - 2026-06-30",
                    "spends": 5,
                    "sales": 20,
                },
                {
                    "sid": "102",
                    "report_date": "2026-06-01 - 2026-06-30",
                    "spends": 9,
                    "sales": 30,
                },
            ]
        ),
        db_df=pd.DataFrame(
            [
                {
                    "sid": "101",
                    "report_date": "2026-06-01 - 2026-06-30",
                    "cost": 5,
                    "sales": 20,
                },
                {
                    "sid": "102",
                    "report_date": "2026-06-01 - 2026-06-30",
                    "cost": 7,
                    "sales": 30,
                },
            ]
        ),
        dimensions=["sid", "report_date"],
        metric_mappings={"spends": "cost", "sales": "sales"},
    )

    assert list(result.metric_details) == ["spends", "sales"]
    assert result.metric_details["spends"].columns.to_list() == [
        "sid",
        "report_date",
        "tool.spends",
        "db.cost",
        "diff",
        "passed",
    ]
    assert result.metric_details["spends"]["passed"].to_list() == [False, True]
    assert result.metric_summaries.to_dict("records") == [
        {
            "metric": "spends",
            "tool_field": "spends",
            "db_field": "cost",
            "total_rows": 2,
            "failed_rows": 1,
            "tool_only_rows": 0,
            "db_only_rows": 0,
            "passed": False,
        },
        {
            "metric": "sales",
            "tool_field": "sales",
            "db_field": "sales",
            "total_rows": 2,
            "failed_rows": 0,
            "tool_only_rows": 0,
            "db_only_rows": 0,
            "passed": True,
        },
    ]


def test_compare_dataframes_supports_metric_specific_dimensions() -> None:
    from lingxing_chatbi_check.comparators.dataframe_compare import compare_dataframes

    result = compare_dataframes(
        tool_df=pd.DataFrame(
            [
                {
                    "sid": "101",
                    "asin": "A1",
                    "report_date": "2026-07-01 - 2026-07-31",
                    "msku": "M1",
                    "fnsku": "F1",
                    "volume": 1,
                    "afn_fulfillable_quantity": 5,
                },
                {
                    "sid": "101",
                    "asin": "A1",
                    "report_date": "2026-07-01 - 2026-07-31",
                    "msku": "M2",
                    "fnsku": "F2",
                    "volume": 2,
                    "afn_fulfillable_quantity": 7,
                },
            ]
        ),
        db_df=pd.DataFrame(
            [
                {
                    "sid": 101,
                    "asin": "A1",
                    "report_date": "2026-07-01 - 2026-07-31",
                    "msku": "M1",
                    "fnsku": "F1",
                    "order_units": 1,
                    "afn_fulfillable_quantity": 5,
                },
                {
                    "sid": 101,
                    "asin": "A1",
                    "report_date": "2026-07-01 - 2026-07-31",
                    "msku": "M2",
                    "fnsku": "F2",
                    "order_units": 2,
                    "afn_fulfillable_quantity": 7,
                },
            ]
        ),
        dimensions=["sid", "asin", "report_date"],
        metric_mappings={
            "volume": "order_units",
            "afn_fulfillable_quantity": "afn_fulfillable_quantity",
        },
        metric_dimension_mappings={
            "afn_fulfillable_quantity": {
                "sid": "sid",
                "msku": "msku",
                "fnsku": "fnsku",
            }
        },
    )

    assert result.metric_details["volume"].columns.to_list() == [
        "sid",
        "asin",
        "report_date",
        "tool.volume",
        "db.order_units",
        "diff",
        "passed",
    ]
    assert result.metric_details["volume"].loc[0, "tool.volume"] == 3
    assert result.metric_details["afn_fulfillable_quantity"].columns.to_list() == [
        "sid",
        "msku",
        "fnsku",
        "tool.afn_fulfillable_quantity",
        "db.afn_fulfillable_quantity",
        "diff",
        "passed",
    ]
    assert result.metric_details["afn_fulfillable_quantity"][
        ["sid", "msku", "fnsku", "tool.afn_fulfillable_quantity"]
    ].to_dict("records") == [
        {
            "sid": "101",
            "msku": "M1",
            "fnsku": "F1",
            "tool.afn_fulfillable_quantity": 5,
        },
        {
            "sid": "101",
            "msku": "M2",
            "fnsku": "F2",
            "tool.afn_fulfillable_quantity": 7,
        },
    ]


def test_compare_dataframes_treats_empty_tool_frame_as_db_only_rows() -> None:
    from lingxing_chatbi_check.comparators.dataframe_compare import compare_dataframes

    result = compare_dataframes(
        tool_df=pd.DataFrame(),
        db_df=pd.DataFrame(
            [
                {
                    "sid": "101",
                    "report_date": "2026-06-01 - 2026-06-30",
                    "cost": 5,
                }
            ]
        ),
        dimensions=["sid", "report_date"],
        metric_mappings={"spends": "cost"},
    )

    assert result.passed is False
    assert result.summary["db_only_rows"] == 1
    detail = result.metric_details["spends"]
    assert detail.loc[0, "sid"] == "101"
    assert detail.loc[0, "report_date"] == "2026-06-01 - 2026-06-30"
    assert pd.isna(detail.loc[0, "tool.spends"])
    assert detail.loc[0, "db.cost"] == 5
    assert pd.isna(detail.loc[0, "diff"])
    assert detail.loc[0, "passed"] is False
