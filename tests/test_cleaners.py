from lingxing_chatbi_check.cleaners.base import CleanerContext, JsonNormalizeCleaner


def test_search_term_cleaner_uses_keyword_id_when_target_id_is_missing() -> None:
    cleaner = JsonNormalizeCleaner()

    df = cleaner.clean(
        [
            {
                "campaign_id": "c1",
                "ad_group_id": "a1",
                "keyword_id": "k1",
                "target_id": None,
                "query": "fish camera",
                "spends": 1.23,
            }
        ],
        CleanerContext(
            tool_name="ad_campaign_search_term_report",
            table_name="chatbi.sp_search_term_report",
        ),
    )

    assert df.loc[0, "target_id"] == "k1"


def test_search_term_cleaner_keeps_scoped_rows_when_target_id_comes_from_keyword_id() -> None:
    cleaner = JsonNormalizeCleaner()

    df = cleaner.clean(
        [
            {
                "profile_id": "p1",
                "campaign_id": "c1",
                "ad_group_id": "a1",
                "keyword_id": "k1",
                "target_id": None,
                "query": "fish camera",
                "spends": 1.23,
            }
        ],
        CleanerContext(
            tool_name="ad_campaign_search_term_report",
            table_name="chatbi.sp_search_term_report",
        ),
    )

    assert df.to_dict("records") == [
        {
            "profile_id": "p1",
            "campaign_id": "c1",
            "ad_group_id": "a1",
            "keyword_id": "k1",
            "target_id": "k1",
            "query": "fish camera",
            "spends": 1.23,
        }
    ]


def test_ad_keyword_cleaner_drops_tool_summary_row_without_dimensions() -> None:
    cleaner = JsonNormalizeCleaner()

    df = cleaner.clean(
        [
            {
                "profile_id": None,
                "campaign_id": None,
                "ad_group_id": None,
                "keyword_id": None,
                "spends": "4645.05",
            },
            {
                "profile_id": "p1",
                "campaign_id": "c1",
                "ad_group_id": "a1",
                "keyword_id": "k1",
                "spends": 1.23,
            },
        ],
        CleanerContext(
            tool_name="ad_campaign_keyword_report",
            table_name="chatbi.sp_keyword_report",
        ),
    )

    assert df.to_dict("records") == [
        {
            "profile_id": "p1",
            "campaign_id": "c1",
            "ad_group_id": "a1",
            "keyword_id": "k1",
            "spends": 1.23,
        }
    ]


def test_ad_cleaner_keeps_rows_with_profile_id_even_when_detail_dimensions_are_blank() -> None:
    cleaner = JsonNormalizeCleaner()

    cases = [
        (
            "ad_campaign_keyword_report",
            "chatbi.sp_keyword_report",
            {
                "profile_id": "p1",
                "campaign_id": None,
                "ad_group_id": None,
                "keyword_id": None,
                "spends": 1.23,
            },
        ),
        (
            "ad_campaign_targeting_report",
            "chatbi.sp_target_report",
            {
                "profile_id": "p2",
                "campaign_id": "",
                "ad_group_id": "",
                "target_id": "",
                "spends": 2.34,
            },
        ),
        (
            "ad_campaign_search_term_report",
            "chatbi.sp_search_term_report",
            {
                "profile_id": "p3",
                "campaign_id": None,
                "ad_group_id": None,
                "target_id": None,
                "query": "",
                "spends": 3.45,
            },
        ),
    ]

    for tool_name, table_name, row in cases:
        df = cleaner.clean(
            [row],
            CleanerContext(tool_name=tool_name, table_name=table_name),
        )

        assert df.to_dict("records") == [row]


def test_ad_keyword_cleaner_filters_non_sp_sponsored_type_rows() -> None:
    cleaner = JsonNormalizeCleaner()

    df = cleaner.clean(
        [
            {
                "profile_id": "p1",
                "campaign_id": "c1",
                "ad_group_id": "a1",
                "keyword_id": "k1",
                "sponsored_type": "sp",
                "spends": 1.23,
            },
            {
                "profile_id": "p1",
                "campaign_id": "c1",
                "ad_group_id": "a1",
                "keyword_id": "k2",
                "sponsored_type": "sb",
                "spends": 2.34,
            },
        ],
        CleanerContext(
            tool_name="ad_campaign_keyword_report",
            table_name="chatbi.sp_keyword_report",
        ),
    )

    assert df["keyword_id"].to_list() == ["k1"]


def test_ad_keyword_cleaner_keeps_database_rows_without_profile_id_column() -> None:
    cleaner = JsonNormalizeCleaner()

    df = cleaner.clean(
        [
            {
                "sid": "101",
                "campaign_id": "c1",
                "ad_group_id": "a1",
                "keyword_id": "k1",
                "cost": 1.23,
            }
        ],
        CleanerContext(
            tool_name="ad_campaign_keyword_report",
            table_name="chatbi.sp_keyword_report",
        ),
    )

    assert len(df) == 1


def test_sales_cleaner_filters_blank_asin_and_derives_sid_from_sids() -> None:
    cleaner = JsonNormalizeCleaner()

    df = cleaner.clean(
        [
            {
                "asin": "-",
                "sids": [508344, 508279],
                "gross_profit": "-15.08",
            },
            {
                "asin": "B001",
                "sid": None,
                "sids": [508279],
                "amount": "10.00",
            },
            {
                "asin": "B002",
                "sid": None,
                "sids": [508344, 508279],
                "asins": [{"asin": "B002", "sid": "508344"}],
                "amount": "20.00",
            },
        ],
        CleanerContext(
            tool_name="query_product_performance_asin_lists",
            table_name="chatbi.sale_report_msku_order",
        ),
    )

    assert df[["sid", "asin", "amount"]].to_dict("records") == [
        {"sid": "508279", "asin": "B001", "amount": "10.00"},
        {"sid": "508344", "asin": "B002", "amount": "20.00"},
    ]


def test_profit_report_msku_cleaner_filters_blank_scope_fields() -> None:
    cleaner = JsonNormalizeCleaner()

    df = cleaner.clean(
        [
            {
                "sid": "508277",
                "msku": "M1",
                "reportDateMonth": "2026-06",
                "totalSalesAmount": 1,
            },
            {
                "sid": "508277",
                "msku": "",
                "reportDateMonth": "2026-06",
                "totalSalesAmount": 2,
            },
            {
                "sid": "",
                "msku": "M2",
                "reportDateMonth": "2026-06",
                "totalSalesAmount": 3,
            },
        ],
        CleanerContext(
            tool_name="get_profit_report_msku",
            table_name="chatbi.sale_report_msku_settlement",
        ),
    )

    assert df.to_dict("records") == [
        {
            "sid": "508277",
            "msku": "M1",
            "reportDateMonth": "2026-06",
            "totalSalesAmount": 1,
        }
    ]
