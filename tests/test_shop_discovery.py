import pytest

from lingxing_chatbi_check.scopes.shop_discovery import (
    AuthorizedShop,
    dedupe_authorized_shops,
    load_authorized_shop_cache,
    normalize_shop_records,
    save_authorized_shop_cache,
)


def test_normalize_get_my_sids_records() -> None:
    shops = normalize_shop_records(
        tool_name="get_my_sids",
        source_user_key="user_a",
        records=[
            {"sid": 101, "name": "店铺A", "country": "US"},
            {"id": 102, "shop_name": "店铺B", "country": "JP"},
        ],
    )

    assert shops == [
        AuthorizedShop(source_user_key="user_a", sid="101", name="店铺A", country="US"),
        AuthorizedShop(source_user_key="user_a", sid="102", name="店铺B", country="JP"),
    ]


def test_normalize_ad_auth_shops_records() -> None:
    shops = normalize_shop_records(
        tool_name="ad_auth_shops",
        source_user_key="user_b",
        records=[
            {"sid": "201", "profile_id": "p201", "alias": "广告店铺", "country": "US"}
        ],
    )

    assert shops == [
        AuthorizedShop(
            source_user_key="user_b",
            sid="201",
            profile_id="p201",
            name="广告店铺",
            country="US",
        )
    ]


def test_dedupe_authorized_shops_prefers_first_key_for_same_sid() -> None:
    shops = dedupe_authorized_shops(
        [
            AuthorizedShop(source_user_key="user_a", sid="101", profile_id="p1"),
            AuthorizedShop(source_user_key="user_b", sid="101", profile_id="p1b"),
            AuthorizedShop(source_user_key="user_b", sid="102"),
        ]
    )

    assert shops == [
        AuthorizedShop(source_user_key="user_a", sid="101", profile_id="p1"),
        AuthorizedShop(source_user_key="user_b", sid="102"),
    ]


def test_normalize_shop_records_requires_sid_or_profile_id() -> None:
    with pytest.raises(ValueError, match="shop identifier"):
        normalize_shop_records(
            tool_name="get_my_sids",
            source_user_key="user_a",
            records=[{"name": "缺少ID"}],
        )


def test_authorized_shop_cache_round_trips(tmp_path) -> None:
    cache_path = tmp_path / "shops.json"
    shops = [
        AuthorizedShop(
            source_user_key="user_a",
            sid="101",
            profile_id="p101",
            name="店铺A",
            country="US",
        )
    ]

    save_authorized_shop_cache(cache_path, shops)

    assert load_authorized_shop_cache(cache_path) == shops
