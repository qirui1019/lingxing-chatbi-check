from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from lingxing_chatbi_check.clients.lingxing_mcp import LingxingMcpClient
from lingxing_chatbi_check.config import get_mcp_user_config


@dataclass(frozen=True)
class AuthorizedShop:
    source_user_key: str
    sid: str | None = None
    profile_id: str | None = None
    name: str | None = None
    country: str | None = None

    def value_for(self, field_name: str) -> str | None:
        return getattr(self, field_name, None)

    def to_dict(self) -> dict[str, str | None]:
        return {
            "source_user_key": self.source_user_key,
            "sid": self.sid,
            "profile_id": self.profile_id,
            "name": self.name,
            "country": self.country,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuthorizedShop":
        return cls(
            source_user_key=str(data["source_user_key"]),
            sid=str(data["sid"]) if data.get("sid") is not None else None,
            profile_id=str(data["profile_id"]) if data.get("profile_id") is not None else None,
            name=str(data["name"]) if data.get("name") is not None else None,
            country=str(data["country"]) if data.get("country") is not None else None,
        )


def normalize_shop_records(
    tool_name: str,
    source_user_key: str,
    records: list[dict[str, Any]],
) -> list[AuthorizedShop]:
    shops: list[AuthorizedShop] = []
    for record in records:
        sid = _first_present(record, ["sid", "s_id", "id", "store_id"])
        profile_id = _first_present(record, ["profile_id", "profileId"])
        name = _first_present(record, ["name", "shop_name", "alias", "store_name"])
        country = _first_present(record, ["country", "country_code", "region"])

        if sid is None and profile_id is None:
            raise ValueError(
                f"{tool_name} returned a row without shop identifier: {record}"
            )

        shops.append(
            AuthorizedShop(
                source_user_key=source_user_key,
                sid=str(sid) if sid is not None else None,
                profile_id=str(profile_id) if profile_id is not None else None,
                name=str(name) if name is not None else None,
                country=str(country) if country is not None else None,
            )
        )
    return shops


def dedupe_authorized_shops(shops: list[AuthorizedShop]) -> list[AuthorizedShop]:
    seen: set[str] = set()
    unique: list[AuthorizedShop] = []
    for shop in shops:
        key = shop.sid or shop.profile_id
        if key is None or key in seen:
            continue
        seen.add(key)
        unique.append(shop)
    return unique


async def discover_authorized_shops(
    env_config: dict[str, Any],
    discovery_tool: str,
    cache_path: Path | None = None,
) -> list[AuthorizedShop]:
    if cache_path is not None and cache_path.exists():
        return load_authorized_shop_cache(cache_path)

    mcp_config = env_config["lingxing_mcp"]
    users = mcp_config.get("users", {})
    shops: list[AuthorizedShop] = []
    for user_key in users:
        user_config = get_mcp_user_config(env_config, user_key)
        client = LingxingMcpClient(
            url=str(mcp_config["url"]),
            x_mcp_key=user_config["x_mcp_key"],
        )
        response = await client.call_tool(discovery_tool, {})
        records = _extract_records(response)
        shops.extend(
            normalize_shop_records(
                tool_name=discovery_tool,
                source_user_key=str(user_key),
                records=records,
            )
        )
    unique = dedupe_authorized_shops(shops)
    if cache_path is not None:
        save_authorized_shop_cache(cache_path, unique)
    return unique


def save_authorized_shop_cache(path: Path, shops: list[AuthorizedShop]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([shop.to_dict() for shop in shops], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_authorized_shop_cache(path: Path) -> list[AuthorizedShop]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [AuthorizedShop.from_dict(item) for item in data]


def _extract_records(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, list):
        return [item for item in response if isinstance(item, dict)]
    if isinstance(response, dict):
        for key in ("data", "rows", "list", "items", "records"):
            value = response.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [response]
    return []


def _first_present(record: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None
