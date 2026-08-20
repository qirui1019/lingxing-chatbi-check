from lingxing_chatbi_check.cases.models import DynamicArgumentsSpec
from lingxing_chatbi_check.scopes.argument_builder import build_tool_argument_batches
from lingxing_chatbi_check.scopes.argument_builder import values_for_database_scope
from lingxing_chatbi_check.scopes.shop_discovery import AuthorizedShop


def test_build_tool_argument_batches_supports_single_shop_calls() -> None:
    shops = [
        AuthorizedShop(source_user_key="user_a", sid="101"),
        AuthorizedShop(source_user_key="user_a", sid="102"),
    ]

    batches = build_tool_argument_batches(
        base_arguments={"start_date": "2026-08-01", "length": 100},
        dynamic_arguments=DynamicArgumentsSpec(
            shop_argument="sid",
            shop_batch_mode="single",
            source_field="sid",
        ),
        shops=shops,
    )

    assert batches == [
        {"start_date": "2026-08-01", "length": 100, "sid": "101"},
        {"start_date": "2026-08-01", "length": 100, "sid": "102"},
    ]


def test_build_tool_argument_batches_supports_list_shop_calls() -> None:
    shops = [
        AuthorizedShop(source_user_key="user_a", sid="101", profile_id="p1"),
        AuthorizedShop(source_user_key="user_a", sid="102", profile_id="p2"),
        AuthorizedShop(source_user_key="user_a", sid="103", profile_id="p3"),
    ]

    batches = build_tool_argument_batches(
        base_arguments={"report_date": "2026-06-01 - 2026-06-30"},
        dynamic_arguments=DynamicArgumentsSpec(
            shop_argument="profile_ids",
            shop_batch_mode="list",
            source_field="profile_id",
            batch_size=2,
        ),
        shops=shops,
    )

    assert batches == [
        {
            "report_date": "2026-06-01 - 2026-06-30",
            "profile_ids": ["p1", "p2"],
        },
        {
            "report_date": "2026-06-01 - 2026-06-30",
            "profile_ids": ["p3"],
        },
    ]


def test_build_tool_argument_batches_uses_comma_separated_values_for_sids_argument() -> None:
    shops = [
        AuthorizedShop(source_user_key="user_a", sid="508344"),
        AuthorizedShop(source_user_key="user_a", sid="508279"),
    ]

    batches = build_tool_argument_batches(
        base_arguments={"start_date": "2026-06-01", "end_date": "2026-06-30"},
        dynamic_arguments=DynamicArgumentsSpec(
            shop_argument="sids",
            shop_batch_mode="list",
            source_field="sid",
            batch_size=2,
        ),
        shops=shops,
    )

    assert batches == [
        {
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
            "sids": "508344,508279",
        }
    ]


def test_values_for_database_scope_can_use_different_shop_field() -> None:
    shops = [
        AuthorizedShop(source_user_key="user_a", sid="101", profile_id="p1"),
        AuthorizedShop(source_user_key="user_a", sid="102", profile_id="p2"),
    ]

    values = values_for_database_scope(
        shops,
        DynamicArgumentsSpec(
            shop_argument="profile_ids",
            shop_batch_mode="list",
            source_field="profile_id",
            database_source_field="sid",
            database_param="sid_values",
        ),
    )

    assert values == ["101", "102"]
