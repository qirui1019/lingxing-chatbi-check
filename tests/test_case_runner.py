import asyncio
import json

import pytest
import pandas as pd

from lingxing_chatbi_check.cases.models import (
    CaseSpec,
    AuthSpec,
    CompareSpec,
    DatabaseSpec,
    DynamicArgumentsSpec,
    PaginationSpec,
    ScopeSpec,
    ToolSpec,
)
from lingxing_chatbi_check.runners.case_runner import (
    _add_missing_constant_compare_dimensions,
    _annotate_tool_output_with_shop_scope,
    _call_tool_for_all_users,
    _call_tool_with_optional_pagination,
    _client_for_user,
    _filter_db_to_tool_scope,
    _filter_sales_records_to_listing_scope,
    _flatten_tool_outputs,
    _load_listing_scope_keys,
    _period_label_for_case,
)
from lingxing_chatbi_check.scopes.shop_discovery import AuthorizedShop


def test_flatten_tool_outputs_extracts_nested_lingxing_record_lists() -> None:
    flattened = _flatten_tool_outputs(
        [
            {
                "data": {
                    "data": {
                        "list": [
                            {"asin": "B001", "sid": None},
                            {"asin": "B002", "sid": None},
                        ]
                    }
                }
            }
        ]
    )

    assert flattened == [
        {"asin": "B001", "sid": None},
        {"asin": "B002", "sid": None},
    ]


def test_annotate_tool_output_adds_database_scope_field_from_shop_mapping() -> None:
    output = {"data": {"list": [{"profile_id": "p1", "campaign_id": "c1"}]}}
    dynamic_arguments = DynamicArgumentsSpec(
        shop_argument="profile_ids",
        shop_batch_mode="list",
        source_field="profile_id",
        database_source_field="sid",
    )
    shops = [
        AuthorizedShop(source_user_key="user_a", sid="101", profile_id="p1"),
    ]

    annotated = _annotate_tool_output_with_shop_scope(
        output=output,
        dynamic_arguments=dynamic_arguments,
        shops=shops,
        arguments={"profile_ids": ["p1"]},
    )

    assert _flatten_tool_outputs([annotated]) == [
        {"profile_id": "p1", "campaign_id": "c1", "sid": "101"}
    ]


def test_annotate_tool_output_adds_single_sid_when_rows_omit_scope() -> None:
    output = {"data": [{"asin": "B001", "sid": None}]}
    dynamic_arguments = DynamicArgumentsSpec(
        shop_argument="sid",
        shop_batch_mode="single",
        source_field="sid",
    )
    shops = [
        AuthorizedShop(source_user_key="user_a", sid="101"),
    ]

    annotated = _annotate_tool_output_with_shop_scope(
        output=output,
        dynamic_arguments=dynamic_arguments,
        shops=shops,
        arguments={"sid": "101"},
    )

    assert _flatten_tool_outputs([annotated]) == [{"asin": "B001", "sid": "101"}]


def test_transient_mcp_error_detects_exception_group_wrapping_disconnect() -> None:
    from lingxing_chatbi_check.runners.case_runner import _is_transient_mcp_error

    error = ExceptionGroup(
        "unhandled errors in a TaskGroup",
        [RemoteProtocolError("Server disconnected without sending a response.")],
    )

    assert _is_transient_mcp_error(error) is True


def test_transient_mcp_error_detects_exception_group_wrapping_dns_failure() -> None:
    from lingxing_chatbi_check.runners.case_runner import _is_transient_mcp_error

    class ConnectError(Exception):
        pass

    error = ExceptionGroup(
        "unhandled errors in a TaskGroup",
        [ConnectError("[Errno 11001] getaddrinfo failed")],
    )

    assert _is_transient_mcp_error(error) is True


def test_transient_mcp_error_detects_cancel_scope_cancellation() -> None:
    from lingxing_chatbi_check.runners.case_runner import _is_transient_mcp_error

    error = asyncio.CancelledError("Cancelled via cancel scope 24294a1cf50")

    assert _is_transient_mcp_error(error) is True


def test_add_missing_constant_compare_dimensions_adds_report_date_from_tool_arguments() -> None:
    case = CaseSpec(
        name="ad keyword",
        enabled=True,
        auth=AuthSpec(),
        scope=ScopeSpec(),
        tool=ToolSpec(
            name="ad_campaign_keyword_report",
            arguments={"report_date": "2026-06-01 - 2026-06-30"},
        ),
        database=DatabaseSpec(table="chatbi.sp_keyword_report", sql="select 1"),
        compare=CompareSpec(
            dimensions=["sid", "report_date"],
            metrics=["cost"],
            dimension_mappings={"sid": "sid", "report_date": "report_date"},
        ),
    )

    tool_df, db_df = _add_missing_constant_compare_dimensions(
        tool_df=pd.DataFrame([{"sid": "101", "spends": 1}]),
        db_df=pd.DataFrame([{"sid": "101", "cost": 1}]),
        case=case,
    )

    assert tool_df.loc[0, "report_date"] == "2026-06-01 - 2026-06-30"
    assert db_df.loc[0, "report_date"] == "2026-06-01 - 2026-06-30"


def test_filter_db_to_tool_scope_uses_sales_sid_and_asin_as_baseline() -> None:
    case = CaseSpec(
        name="sales asin",
        enabled=True,
        auth=AuthSpec(),
        scope=ScopeSpec(),
        tool=ToolSpec(name="query_product_performance_asin_lists"),
        database=DatabaseSpec(table="chatbi.sale_report_asin", sql="select 1"),
        compare=CompareSpec(
            dimensions=["sid", "asin", "report_date"],
            metrics=["page_views_total"],
            dimension_mappings={
                "sid": "sid",
                "asin": "asin",
                "report_date": "report_date",
            },
        ),
    )

    db_df = _filter_db_to_tool_scope(
        case=case,
        tool_df=pd.DataFrame(
            [
                {
                    "sid": "508344",
                    "asin": "B001",
                    "report_date": "2026-06-01 - 2026-06-30",
                }
            ]
        ),
        db_df=pd.DataFrame(
            [
                {
                    "sid": 508344,
                    "asin": "B001",
                    "report_date": "2026-06-01 - 2026-06-30",
                    "page_views_total": 1,
                },
                {
                    "sid": 508344,
                    "asin": "B002",
                    "report_date": "2026-06-01 - 2026-06-30",
                    "page_views_total": 2,
                },
            ]
        ),
    )

    assert db_df[["sid", "asin", "page_views_total"]].to_dict("records") == [
        {"sid": 508344, "asin": "B001", "page_views_total": 1}
    ]


def test_filter_db_to_tool_scope_uses_profit_sid_and_msku_as_baseline() -> None:
    case = CaseSpec(
        name="profit msku",
        enabled=True,
        auth=AuthSpec(),
        scope=ScopeSpec(),
        tool=ToolSpec(name="get_profit_report_msku"),
        database=DatabaseSpec(
            table="chatbi.sale_report_msku_settlement",
            sql="select 1",
        ),
        compare=CompareSpec(
            dimensions=["sid", "msku", "reportDateMonth"],
            metrics=["settlement_sales_amount"],
            dimension_mappings={
                "sid": "sid",
                "msku": "msku",
                "reportDateMonth": "settlement_date",
            },
        ),
    )

    db_df = _filter_db_to_tool_scope(
        case=case,
        tool_df=pd.DataFrame(
            [
                {
                    "sid": "508277",
                    "msku": "03US-CP1A0603US-N",
                    "reportDateMonth": "2026-06",
                }
            ]
        ),
        db_df=pd.DataFrame(
            [
                {
                    "sid": 508277,
                    "msku": "03US-CP1A0603US-N",
                    "settlement_date": "2026-06",
                    "settlement_sales_amount": 1,
                },
                {
                    "sid": 508277,
                    "msku": "OTHER",
                    "settlement_date": "2026-06",
                    "settlement_sales_amount": 2,
                },
            ]
        ),
    )

    assert db_df[["sid", "msku", "settlement_sales_amount"]].to_dict("records") == [
        {
            "sid": 508277,
            "msku": "03US-CP1A0603US-N",
            "settlement_sales_amount": 1,
        }
    ]


def test_filter_db_to_tool_scope_uses_ad_tool_sid_as_baseline() -> None:
    case = CaseSpec(
        name="ad target",
        enabled=True,
        auth=AuthSpec(),
        scope=ScopeSpec(),
        tool=ToolSpec(name="ad_campaign_targeting_report"),
        database=DatabaseSpec(table="chatbi.sp_target_report", sql="select 1"),
        compare=CompareSpec(
            dimensions=["sid", "report_date"],
            metrics=["cost"],
            dimension_mappings={"sid": "sid", "report_date": "report_date"},
        ),
    )

    db_df = _filter_db_to_tool_scope(
        case=case,
        tool_df=pd.DataFrame(
            [
                {
                    "sid": "101",
                    "report_date": "2026-07-01 - 2026-07-31",
                    "spends": 1,
                }
            ]
        ),
        db_df=pd.DataFrame(
            [
                {
                    "sid": 101,
                    "report_date": "2026-07-01 - 2026-07-31",
                    "cost": 1,
                },
                {
                    "sid": 102,
                    "report_date": "2026-07-01 - 2026-07-31",
                    "cost": 2,
                },
            ]
        ),
    )

    assert db_df[["sid", "cost"]].to_dict("records") == [
        {"sid": 101, "cost": 1}
    ]


def test_filter_sales_records_to_listing_scope_keeps_only_sid_asin_pairs() -> None:
    records = [
        {"sid": "508344", "asin": "B001", "amount": 1},
        {"sid": "508344", "asin": "B002", "amount": 2},
        {"sid": "508279", "asin": "B002", "amount": 3},
        {"sid": "508279", "asin": "-", "amount": 4},
    ]

    filtered = _filter_sales_records_to_listing_scope(
        records,
        {("508344", "B001"), ("508279", "B002")},
    )

    assert filtered == [
        {"sid": "508344", "asin": "B001", "amount": 1},
        {"sid": "508279", "asin": "B002", "amount": 3},
    ]


def test_filter_sales_records_to_listing_scope_keeps_only_sid_msku_pairs() -> None:
    records = [
        {"sid": "508277", "msku": "M1", "amount": 1},
        {"sid": "508277", "msku": "M2", "amount": 2},
        {"sid": "508278", "sellerSku": "M2", "amount": 3},
        {"sid": "508278", "msku": "-", "amount": 4},
    ]

    filtered = _filter_sales_records_to_listing_scope(
        records,
        {("508277", "M1"), ("508278", "M2")},
        key_field="msku",
    )

    assert filtered == [
        {"sid": "508277", "msku": "M1", "amount": 1},
        {"sid": "508278", "sellerSku": "M2", "amount": 3},
    ]


def test_client_for_user_uses_configured_mcp_timeout() -> None:
    client = _client_for_user(
        {
            "lingxing_mcp": {
                "url": "https://example.test/mcp",
                "timeout_seconds": 180,
                "users": {
                    "user_a": {
                        "x_mcp_key": "secret-key",
                    }
                },
            }
        },
        "user_a",
    )

    assert client.timeout_seconds == 180


def test_period_label_for_case_uses_database_month_range() -> None:
    case = CaseSpec(
        name="ad search term",
        enabled=True,
        auth=AuthSpec(),
        scope=ScopeSpec(),
        tool=ToolSpec(
            name="ad_campaign_search_term_report",
            arguments={"report_date": "2026-06-01 - 2026-06-30"},
        ),
        database=DatabaseSpec(
            table="chatbi.sp_search_term_report",
            sql="select 1",
            params={
                "report_start_date": "2026-06-01",
                "report_end_date": "2026-06-30",
            },
        ),
        compare=CompareSpec(dimensions=["sid"], metrics=["cost"]),
    )

    assert _period_label_for_case(case) == "2026年6月"


def test_period_label_for_case_handles_cross_month_range() -> None:
    case = CaseSpec(
        name="sales",
        enabled=True,
        auth=AuthSpec(),
        scope=ScopeSpec(),
        tool=ToolSpec(
            name="query_product_performance_asin_lists",
            arguments={"start_date": "2026-06-20", "end_date": "2026-07-10"},
        ),
        database=DatabaseSpec(table="chatbi.sale_report_asin", sql="select 1"),
        compare=CompareSpec(dimensions=["sid"], metrics=["amount"]),
    )

    assert _period_label_for_case(case) == "2026年6月-2026年7月"


class RecordingClient:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    async def call_tool(self, tool_name, arguments):
        self.calls.append((tool_name, dict(arguments)))
        output = self.outputs.pop(0)
        if isinstance(output, BaseException):
            raise output
        return output


class RemoteProtocolError(Exception):
    pass


@pytest.mark.anyio
async def test_call_tool_for_all_users_reuses_one_client_session_per_user(
    monkeypatch,
    tmp_path,
) -> None:
    import lingxing_chatbi_check.runners.case_runner as case_runner

    class ContextRecordingClient:
        def __init__(self):
            self.enter_count = 0
            self.exit_count = 0
            self.calls = []

        async def __aenter__(self):
            self.enter_count += 1
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            self.exit_count += 1
            return False

        async def call_tool(self, tool_name, arguments):
            self.calls.append((tool_name, dict(arguments)))
            return [{"sid": arguments["sid"], "value": 1}]

    client = ContextRecordingClient()

    async def fake_discover_authorized_shops(*_args, **_kwargs):
        return [
            AuthorizedShop(source_user_key="user_a", sid="101"),
            AuthorizedShop(source_user_key="user_a", sid="102"),
        ]

    monkeypatch.setattr(
        case_runner,
        "discover_authorized_shops",
        fake_discover_authorized_shops,
    )
    monkeypatch.setattr(case_runner, "_client_for_user", lambda *_args: client)

    case = CaseSpec(
        name="sales",
        enabled=True,
        auth=AuthSpec(mode="all_users"),
        scope=ScopeSpec(shop_discovery="get_my_sids"),
        tool=ToolSpec(
            name="query_product_performance_asin_lists",
            arguments={"start_date": "2026-06-01", "end_date": "2026-06-30"},
            dynamic_arguments=DynamicArgumentsSpec(
                shop_argument="sid",
                shop_batch_mode="single",
                source_field="sid",
            ),
        ),
        database=DatabaseSpec(table="chatbi.sale_report_asin", sql="select 1"),
        compare=CompareSpec(dimensions=["sid"], metrics=["value"]),
    )

    output, shops = await _call_tool_for_all_users(case, {}, tmp_path)

    assert client.enter_count == 1
    assert client.exit_count == 1
    assert client.calls == [
        (
            "query_product_performance_asin_lists",
            {"start_date": "2026-06-01", "end_date": "2026-06-30", "sid": "101"},
        ),
        (
            "query_product_performance_asin_lists",
            {"start_date": "2026-06-01", "end_date": "2026-06-30", "sid": "102"},
        ),
    ]
    assert output == [{"sid": "101", "value": 1}, {"sid": "102", "value": 1}]
    assert shops == [
        AuthorizedShop(source_user_key="user_a", sid="101"),
        AuthorizedShop(source_user_key="user_a", sid="102"),
    ]


@pytest.mark.anyio
async def test_call_tool_for_all_users_filters_sales_rows_by_erp_listing(
    monkeypatch,
    tmp_path,
) -> None:
    import lingxing_chatbi_check.runners.case_runner as case_runner

    class ContextRecordingClient:
        def __init__(self):
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def call_tool(self, tool_name, arguments):
            self.calls.append((tool_name, dict(arguments)))
            if tool_name == "query_product_performance_asin_lists":
                return [
                    {"sid": "101", "asin": "B001", "amount": 1},
                    {"sid": "101", "asin": "B999", "amount": 9},
                ]
            if tool_name == "erp_listing":
                return {"data": {"data": {"list": [{"store_id": 101, "asin": "B001"}]}}}
            raise AssertionError(f"unexpected tool: {tool_name}")

    client = ContextRecordingClient()

    async def fake_discover_authorized_shops(*_args, **_kwargs):
        return [AuthorizedShop(source_user_key="user_a", sid="101")]

    monkeypatch.setattr(
        case_runner,
        "discover_authorized_shops",
        fake_discover_authorized_shops,
    )
    monkeypatch.setattr(case_runner, "_client_for_user", lambda *_args: client)

    case = CaseSpec(
        name="sales",
        enabled=True,
        auth=AuthSpec(mode="all_users"),
        scope=ScopeSpec(shop_discovery="get_my_sids", listing_mapping="erp_listing"),
        tool=ToolSpec(
            name="query_product_performance_asin_lists",
            arguments={"start_date": "2026-06-01", "end_date": "2026-06-30"},
            dynamic_arguments=DynamicArgumentsSpec(
                shop_argument="sids",
                shop_batch_mode="list",
                source_field="sid",
            ),
        ),
        database=DatabaseSpec(table="chatbi.sale_report_asin", sql="select 1"),
        compare=CompareSpec(dimensions=["sid", "asin"], metrics=["amount"]),
    )

    output, _shops = await _call_tool_for_all_users(case, {}, tmp_path)

    assert client.calls == [
        (
            "query_product_performance_asin_lists",
            {"start_date": "2026-06-01", "end_date": "2026-06-30", "sids": "101"},
        ),
        ("erp_listing", {"sid": "101", "offset": 0, "length": 1000}),
    ]
    assert output == [{"sid": "101", "asin": "B001", "amount": 1}]


@pytest.mark.anyio
async def test_call_tool_for_all_users_filters_profit_rows_by_erp_listing_msku(
    monkeypatch,
    tmp_path,
) -> None:
    import lingxing_chatbi_check.runners.case_runner as case_runner

    class ContextRecordingClient:
        def __init__(self):
            self.calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def call_tool(self, tool_name, arguments):
            self.calls.append((tool_name, dict(arguments)))
            if tool_name == "get_profit_report_msku":
                return [
                    {"sid": "101", "msku": "M1", "totalSalesAmount": 1},
                    {"sid": "102", "msku": "M2", "totalSalesAmount": 2},
                    {"sid": "101", "msku": "M999", "totalSalesAmount": 9},
                ]
            if tool_name == "erp_listing":
                if str(arguments["sid"]) == "101":
                    return {"data": {"data": {"list": [{"store_id": 101, "msku": "M1"}]}}}
                if str(arguments["sid"]) == "102":
                    return {"data": {"data": {"list": [{"store_id": 102, "msku": "M2"}]}}}
            raise AssertionError(f"unexpected tool: {tool_name}")

    client = ContextRecordingClient()

    async def fake_discover_authorized_shops(*_args, **_kwargs):
        return [
            AuthorizedShop(source_user_key="user_a", sid="101"),
            AuthorizedShop(source_user_key="user_a", sid="102"),
        ]

    monkeypatch.setattr(
        case_runner,
        "discover_authorized_shops",
        fake_discover_authorized_shops,
    )
    monkeypatch.setattr(case_runner, "_client_for_user", lambda *_args: client)

    case = CaseSpec(
        name="profit msku",
        enabled=True,
        auth=AuthSpec(mode="all_users"),
        scope=ScopeSpec(shop_discovery="get_my_sids", listing_mapping="erp_listing"),
        tool=ToolSpec(
            name="get_profit_report_msku",
            arguments={"reportDateMonth": "2026-06"},
            dynamic_arguments=DynamicArgumentsSpec(
                shop_argument=None,
                shop_batch_mode="none",
                source_field="sid",
            ),
        ),
        database=DatabaseSpec(table="chatbi.sale_report_msku_settlement", sql="select 1"),
        compare=CompareSpec(dimensions=["sid", "msku", "reportDateMonth"], metrics=["totalSalesAmount"]),
    )

    output, _shops = await _call_tool_for_all_users(case, {}, tmp_path)

    assert client.calls == [
        ("get_profit_report_msku", {"reportDateMonth": "2026-06"}),
        ("erp_listing", {"sid": "101", "offset": 0, "length": 1000}),
        ("erp_listing", {"sid": "102", "offset": 0, "length": 1000}),
    ]
    assert output == [
        {"sid": "101", "msku": "M1", "totalSalesAmount": 1},
        {"sid": "102", "msku": "M2", "totalSalesAmount": 2},
    ]


@pytest.mark.anyio
async def test_call_tool_for_all_users_skips_timed_out_argument_batch(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    import lingxing_chatbi_check.runners.case_runner as case_runner

    class TimeoutClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def call_tool(self, tool_name, arguments):
            if arguments["profile_ids"] == ["p1"]:
                await asyncio.sleep(1)
            return [
                {
                    "profile_id": arguments["profile_ids"][0],
                    "sid": arguments["profile_ids"][0],
                    "spends": 1,
                }
            ]

        async def reset_session(self):
            return None

    async def fake_discover_authorized_shops(*_args, **_kwargs):
        return [
            AuthorizedShop(source_user_key="user_a", sid="101", profile_id="p1"),
            AuthorizedShop(source_user_key="user_a", sid="102", profile_id="p2"),
        ]

    monkeypatch.setattr(
        case_runner,
        "discover_authorized_shops",
        fake_discover_authorized_shops,
    )
    monkeypatch.setattr(case_runner, "_client_for_user", lambda *_args: TimeoutClient())

    case = CaseSpec(
        name="ad keyword",
        enabled=True,
        auth=AuthSpec(mode="all_users"),
        scope=ScopeSpec(shop_discovery="ad_auth_shops"),
        tool=ToolSpec(
            name="ad_campaign_keyword_report",
            arguments={"report_date": "2026-07-01 - 2026-07-31"},
            dynamic_arguments=DynamicArgumentsSpec(
                shop_argument="profile_ids",
                shop_batch_mode="list",
                source_field="profile_id",
                database_source_field="sid",
                batch_size=1,
            ),
            pagination=PaginationSpec(
                enabled=True,
                page_argument="page",
                page_start=1,
                page_size_argument="length",
                page_size=1000,
                max_pages=10,
                batch_timeout_seconds=0.01,
            ),
        ),
        database=DatabaseSpec(table="chatbi.sp_keyword_report", sql="select 1"),
        compare=CompareSpec(dimensions=["sid"], metrics=["spends"]),
    )

    output, _shops = await _call_tool_for_all_users(case, {}, tmp_path)

    assert output == [{"profile_id": "p2", "sid": "p2", "spends": 1}]
    logs = capsys.readouterr().out.splitlines()
    assert len(logs) == 2
    assert logs[0] == (
        "tool_batch_timeout tool=ad_campaign_keyword_report "
        "args=report_date='2026-07-01 - 2026-07-31', profile_ids=['p1'] "
        "timeout_seconds=0.01 action=skip"
    )
    assert logs[1].startswith(
        "pagination_summary tool=ad_campaign_keyword_report "
        "args=report_date='2026-07-01 - 2026-07-31', profile_ids=['p2'] "
        "pages=1 records=1 total=None seconds="
    )
    assert logs[1].endswith(" max_pages_reached=False")


@pytest.mark.anyio
async def test_load_listing_scope_keys_fetches_all_erp_listing_pages(tmp_path) -> None:
    client = RecordingClient(
        [
            {
                "data": {
                    "data": {
                        "total": 3,
                        "list": [
                            {"store_id": 101, "asin": "B001"},
                            {"store_id": 101, "asin": "B002"},
                        ],
                    }
                }
            },
            {
                "data": {
                    "data": {
                        "total": 3,
                        "list": [
                            {"store_id": 101, "asin": "B003"},
                        ],
                    }
                }
            },
        ]
    )

    keys = await _load_listing_scope_keys(
        client=client,
        listing_tool="erp_listing",
        sid="101",
        cache_dir=tmp_path,
        page_size=2,
    )

    assert client.calls == [
        ("erp_listing", {"sid": "101", "offset": 0, "length": 2}),
        ("erp_listing", {"sid": "101", "offset": 2, "length": 2}),
    ]
    assert keys == {
        ("101", "B001"),
        ("101", "B002"),
        ("101", "B003"),
    }


@pytest.mark.anyio
async def test_load_listing_scope_keys_refetches_incomplete_cache(tmp_path) -> None:
    cache_path = tmp_path / "erp_listing_101.json"
    cache_path.write_text(
        json.dumps(
            {
                "data": {
                    "data": {
                        "total": 3,
                        "list": [
                            {"store_id": 101, "asin": "B001"},
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    client = RecordingClient(
        [
            {
                "data": {
                    "data": {
                        "total": 3,
                        "list": [
                            {"store_id": 101, "asin": "B001"},
                            {"store_id": 101, "asin": "B002"},
                        ],
                    }
                }
            },
            {
                "data": {
                    "data": {
                        "total": 3,
                        "list": [
                            {"store_id": 101, "asin": "B003"},
                        ],
                    }
                }
            },
        ]
    )

    keys = await _load_listing_scope_keys(
        client=client,
        listing_tool="erp_listing",
        sid="101",
        cache_dir=tmp_path,
        page_size=2,
    )

    assert client.calls == [
        ("erp_listing", {"sid": "101", "offset": 0, "length": 2}),
        ("erp_listing", {"sid": "101", "offset": 2, "length": 2}),
    ]
    assert keys == {
        ("101", "B001"),
        ("101", "B002"),
        ("101", "B003"),
    }


@pytest.mark.anyio
async def test_call_tool_with_optional_pagination_fetches_until_short_page(
    capsys,
) -> None:
    client = RecordingClient(
        [
            {"data": {"list": [{"row": 1}, {"row": 2}]}},
            {"data": {"list": [{"row": 3}]}},
        ]
    )

    output = await _call_tool_with_optional_pagination(
        client=client,
        tool_name="ad_campaign_search_term_report",
        arguments={"profile_ids": ["p1"], "report_date": "2026-06-01 - 2026-06-30"},
        pagination=PaginationSpec(
            enabled=True,
            page_argument="page",
            page_start=1,
            page_size_argument="length",
            page_size=2,
            max_pages=10,
        ),
    )

    assert client.calls == [
        (
            "ad_campaign_search_term_report",
            {
                "profile_ids": ["p1"],
                "report_date": "2026-06-01 - 2026-06-30",
                "page": 1,
                "length": 2,
            },
        ),
        (
            "ad_campaign_search_term_report",
            {
                "profile_ids": ["p1"],
                "report_date": "2026-06-01 - 2026-06-30",
                "page": 2,
                "length": 2,
            },
        ),
    ]
    assert _flatten_tool_outputs(output) == [{"row": 1}, {"row": 2}, {"row": 3}]
    logs = capsys.readouterr().out.splitlines()
    assert len(logs) == 1
    assert logs[0].startswith(
        "pagination_summary tool=ad_campaign_search_term_report "
        "args=profile_ids=['p1'], report_date='2026-06-01 - 2026-06-30' "
        "pages=2 records=3 total=None seconds="
    )
    assert logs[0].endswith(" max_pages_reached=False")


@pytest.mark.anyio
async def test_call_tool_with_optional_pagination_stops_when_total_is_reached() -> None:
    client = RecordingClient(
        [
            {
                "data": {
                    "data": {
                        "total": 4,
                        "list": [{"row": 1}, {"row": 2}],
                    }
                }
            },
            {
                "data": {
                    "data": {
                        "total": 4,
                        "list": [{"row": 3}, {"row": 4}],
                    }
                }
            },
            AssertionError("should not request a third full page"),
        ]
    )

    output = await _call_tool_with_optional_pagination(
        client=client,
        tool_name="ad_campaign_keyword_report",
        arguments={"profile_ids": ["p1", "p2"], "report_date": "2026-06-01 - 2026-06-30"},
        pagination=PaginationSpec(
            enabled=True,
            page_argument="page",
            page_start=1,
            page_size_argument="length",
            page_size=2,
            max_pages=10,
        ),
    )

    assert client.calls == [
        (
            "ad_campaign_keyword_report",
            {
                "profile_ids": ["p1", "p2"],
                "report_date": "2026-06-01 - 2026-06-30",
                "page": 1,
                "length": 2,
            },
        ),
        (
            "ad_campaign_keyword_report",
            {
                "profile_ids": ["p1", "p2"],
                "report_date": "2026-06-01 - 2026-06-30",
                "page": 2,
                "length": 2,
            },
        ),
    ]
    assert _flatten_tool_outputs(output) == [
        {"row": 1},
        {"row": 2},
        {"row": 3},
        {"row": 4},
    ]


@pytest.mark.anyio
async def test_call_tool_with_optional_pagination_uses_nested_records_filtered() -> None:
    client = RecordingClient(
        [
            {
                "data": {
                    "recordsFiltered": 3,
                    "data": [{"row": 1}, {"row": 2}],
                },
                "total": 0,
            },
            {
                "data": {
                    "recordsFiltered": 3,
                    "data": [{"row": 3}],
                },
                "total": 0,
            },
        ]
    )

    output = await _call_tool_with_optional_pagination(
        client=client,
        tool_name="ad_campaign_keyword_report",
        arguments={"profile_ids": ["p1", "p2"], "report_date": "2026-07-01 - 2026-07-31"},
        pagination=PaginationSpec(
            enabled=True,
            page_argument="page",
            page_start=1,
            page_size_argument="length",
            page_size=2,
            max_pages=10,
        ),
    )

    assert client.calls == [
        (
            "ad_campaign_keyword_report",
            {
                "profile_ids": ["p1", "p2"],
                "report_date": "2026-07-01 - 2026-07-31",
                "page": 1,
                "length": 2,
            },
        ),
        (
            "ad_campaign_keyword_report",
            {
                "profile_ids": ["p1", "p2"],
                "report_date": "2026-07-01 - 2026-07-31",
                "page": 2,
                "length": 2,
            },
        ),
    ]
    assert _flatten_tool_outputs(output) == [{"row": 1}, {"row": 2}, {"row": 3}]


@pytest.mark.anyio
async def test_call_tool_with_optional_pagination_logs_batch_summary(capsys) -> None:
    client = RecordingClient(
        [
            {
                "data": {
                    "recordsFiltered": 3,
                    "data": [{"row": 1}, {"row": 2}],
                },
                "total": 0,
            },
            {
                "data": {
                    "recordsFiltered": 3,
                    "data": [{"row": 3}],
                },
                "total": 0,
            },
        ]
    )

    await _call_tool_with_optional_pagination(
        client=client,
        tool_name="ad_campaign_keyword_report",
        arguments={"profile_ids": ["p1", "p2"], "report_date": "2026-07-01 - 2026-07-31"},
        pagination=PaginationSpec(
            enabled=True,
            page_argument="page",
            page_start=1,
            page_size_argument="length",
            page_size=2,
            max_pages=10,
        ),
    )

    logs = capsys.readouterr().out.splitlines()
    assert len(logs) == 1
    assert logs[0].startswith(
        "pagination_summary tool=ad_campaign_keyword_report "
        "args=profile_ids=['p1', 'p2'], report_date='2026-07-01 - 2026-07-31' "
        "pages=2 records=3 total=3 seconds="
    )
    assert logs[0].endswith(" max_pages_reached=False")


@pytest.mark.anyio
async def test_call_tool_with_optional_pagination_supports_offset_values() -> None:
    client = RecordingClient(
        [
            {"data": {"list": [{"row": 1}, {"row": 2}]}},
            {"data": {"list": []}},
        ]
    )

    output = await _call_tool_with_optional_pagination(
        client=client,
        tool_name="query_product_performance_asin_lists",
        arguments={"sids": "101,102"},
        pagination=PaginationSpec(
            enabled=True,
            page_argument="offset",
            page_start=0,
            page_size_argument="length",
            page_size=2,
            max_pages=10,
            page_value_mode="offset",
        ),
    )

    assert client.calls == [
        (
                "query_product_performance_asin_lists",
                {
                    "sids": "101,102",
                    "offset": 0,
                    "length": 2,
                },
        ),
        (
                "query_product_performance_asin_lists",
                {
                    "sids": "101,102",
                    "offset": 2,
                    "length": 2,
                },
        ),
    ]
    assert output == [{"row": 1}, {"row": 2}]


@pytest.mark.anyio
async def test_call_tool_with_optional_pagination_logs_max_pages_reached(
    capsys,
) -> None:
    client = RecordingClient(
        [
            {"data": {"list": [{"row": 1}, {"row": 2}]}},
            {"data": {"list": [{"row": 3}, {"row": 4}]}},
        ]
    )

    output = await _call_tool_with_optional_pagination(
        client=client,
        tool_name="ad_campaign_search_term_report",
        arguments={"profile_ids": ["p1"], "report_date": "2026-06-01 - 2026-06-30"},
        pagination=PaginationSpec(
            enabled=True,
            page_argument="page",
            page_start=1,
            page_size_argument="length",
            page_size=2,
            max_pages=2,
        ),
    )

    assert _flatten_tool_outputs(output) == [
        {"row": 1},
        {"row": 2},
        {"row": 3},
        {"row": 4},
    ]
    logs = capsys.readouterr().out.splitlines()
    assert len(logs) == 2
    assert logs[0] == (
        "pagination_warning tool=ad_campaign_search_term_report "
        "args=profile_ids=['p1'], report_date='2026-06-01 - 2026-06-30' "
        "reason=max_pages_reached max_pages=2 page_size=2 last_page=2 "
        "last_returned=2 total=4"
    )
    assert logs[1].startswith(
        "pagination_summary tool=ad_campaign_search_term_report "
        "args=profile_ids=['p1'], report_date='2026-06-01 - 2026-06-30' "
        "pages=2 records=4 total=None seconds="
    )
    assert logs[1].endswith(" max_pages_reached=True")


@pytest.mark.anyio
async def test_call_tool_with_optional_pagination_retries_transient_disconnect() -> None:
    client = RecordingClient(
        [
            RemoteProtocolError("Server disconnected without sending a response."),
            {"data": {"list": [{"row": 1}]}},
        ]
    )

    output = await _call_tool_with_optional_pagination(
        client=client,
        tool_name="ad_campaign_search_term_report",
        arguments={"profile_ids": ["p1"], "report_date": "2026-06-01 - 2026-06-30"},
        pagination=PaginationSpec(
            enabled=True,
            page_argument="page",
            page_start=1,
            page_size_argument="length",
            page_size=2,
            max_pages=10,
        ),
    )

    assert len(client.calls) == 2
    assert client.calls[0] == client.calls[1]
    assert output == [{"row": 1}]
