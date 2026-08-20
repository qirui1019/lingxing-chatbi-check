import pytest

from lingxing_chatbi_check.scopes.shop_discovery import (
    AuthorizedShop,
    _extract_records,
    discover_authorized_shops,
    is_tool_error_response,
    is_transient_tool_error_response,
    dedupe_authorized_shops,
    load_authorized_shop_cache,
    normalize_shop_records,
    save_authorized_shop_cache,
)


class RecordingMcpClient:
    outputs = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def call_tool(self, tool_name, arguments):
        return self.outputs.pop(0)


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


def test_extract_records_handles_nested_ad_auth_shops_response() -> None:
    record = {
        "store_id": 3468613898,
        "profile_id": "1106247134740478",
        "alias": "Amazon-03-CA",
        "country": "CA",
        "sid": 508278,
    }
    response = {
        "code": 0,
        "message": "success",
        "data": {
            "msg": "success",
            "code": 1,
            "data": [record],
            "success": True,
        },
        "total": 0,
    }

    assert _extract_records(response) == [record]


def test_extract_records_handles_get_my_sids_text_response() -> None:
    response = """店铺列表（id即为其他接口的sid参数）:
- sid: 508278, 店铺名: Amazon-03-CA, 国家: 加拿大(CA)
- sid: 508279, 店铺名: Amazon-03-MX, 国家: 墨西哥(MX)
"""

    assert _extract_records(response, tool_name="get_my_sids") == [
        {"sid": "508278", "name": "Amazon-03-CA", "country": "CA"},
        {"sid": "508279", "name": "Amazon-03-MX", "country": "MX"},
    ]


def test_extract_records_does_not_treat_tool_error_payload_as_shop_record() -> None:
    response = {
        "msg": "服务器繁忙 :0ad3ca97_a0f7_491f_b16c_ad2dc91cbdfe",
        "traceId": "0ad3ca97_a0f7_491f_b16c_ad2dc91cbdfe",
        "code": 0,
        "data": None,
        "success": False,
    }

    assert _extract_records(response) == []
    assert is_transient_tool_error_response(response) is True


def test_extract_records_does_not_treat_invalid_mcp_key_payload_as_shop_record() -> None:
    response = {
        "code": 102,
        "message": "参数不合法",
        "error_details": [
            "MCP Key无效或已失效，请检查x-mcp-key配置；如无法确认，请在MCP服务管理页重新生成Key后更新客户端配置"
        ],
        "data": None,
        "total": 0,
    }

    assert _extract_records(response) == []
    assert is_tool_error_response(response) is True
    assert is_transient_tool_error_response(response) is False


def test_tool_error_response_helpers_ignore_non_mapping_response() -> None:
    response = "upstream temporarily unavailable"

    assert _extract_records(response) == []
    assert is_tool_error_response(response) is False
    assert is_transient_tool_error_response(response) is False


@pytest.mark.anyio
async def test_discover_authorized_shops_reports_invalid_mcp_key_error(monkeypatch) -> None:
    import lingxing_chatbi_check.scopes.shop_discovery as shop_discovery

    RecordingMcpClient.outputs = [
        {
            "code": 102,
            "message": "参数不合法",
            "error_details": [
                "MCP Key无效或已失效，请检查x-mcp-key配置；如无法确认，请在MCP服务管理页重新生成Key后更新客户端配置"
            ],
            "data": None,
            "total": 0,
        }
    ]

    monkeypatch.setattr(shop_discovery, "LingxingMcpClient", RecordingMcpClient)

    with pytest.raises(ValueError) as exc_info:
        await discover_authorized_shops(
            {
                "lingxing_mcp": {
                    "url": "https://example.test/mcp",
                    "users": {"default": {"x_mcp_key": "expired"}},
                }
            },
            discovery_tool="ad_auth_shops",
        )

    message = str(exc_info.value)
    assert "ad_auth_shops returned an error response" in message
    assert "code=102" in message
    assert "MCP Key无效或已失效" in message
    assert "shop identifier" not in message


@pytest.mark.anyio
async def test_discover_authorized_shops_retries_transient_tool_error(monkeypatch) -> None:
    import lingxing_chatbi_check.scopes.shop_discovery as shop_discovery

    RecordingMcpClient.outputs = [
        {
            "msg": "服务器繁忙 :0ad3ca97_a0f7_491f_b16c_ad2dc91cbdfe",
            "traceId": "0ad3ca97_a0f7_491f_b16c_ad2dc91cbdfe",
            "code": 0,
            "data": None,
            "success": False,
        },
        {
            "data": {
                "data": [
                    {
                        "sid": 508278,
                        "profile_id": "1106247134740478",
                        "alias": "Amazon-03-CA",
                        "country": "CA",
                    }
                ]
            }
        },
    ]

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(shop_discovery, "LingxingMcpClient", RecordingMcpClient)
    monkeypatch.setattr(shop_discovery.asyncio, "sleep", no_sleep)

    shops = await discover_authorized_shops(
        {
            "lingxing_mcp": {
                "url": "https://example.test/mcp",
                "users": {"default": {"x_mcp_key": "secret"}},
            }
        },
        discovery_tool="ad_auth_shops",
    )

    assert shops == [
        AuthorizedShop(
            source_user_key="default",
            sid="508278",
            profile_id="1106247134740478",
            name="Amazon-03-CA",
            country="CA",
        )
    ]


@pytest.mark.anyio
async def test_discover_authorized_shops_raises_and_does_not_cache_empty_result(
    monkeypatch,
    tmp_path,
) -> None:
    import lingxing_chatbi_check.scopes.shop_discovery as shop_discovery

    RecordingMcpClient.outputs = [{"data": {"data": []}}]

    monkeypatch.setattr(shop_discovery, "LingxingMcpClient", RecordingMcpClient)
    cache_path = tmp_path / "ad_auth_shops.json"

    with pytest.raises(ValueError, match="did not return any authorized shops"):
        await discover_authorized_shops(
            {
                "lingxing_mcp": {
                    "url": "https://example.test/mcp",
                    "users": {"default": {"x_mcp_key": "secret"}},
                }
            },
            discovery_tool="ad_auth_shops",
            cache_path=cache_path,
        )

    assert not cache_path.exists()


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
