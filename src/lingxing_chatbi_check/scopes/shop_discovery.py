from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import re
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
            timeout_seconds=float(mcp_config.get("timeout_seconds", 120)),
        )
        response = await _call_discovery_tool_with_retries(client, discovery_tool)
        records = _extract_records(response, tool_name=discovery_tool)
        if not records and is_tool_error_response(response):
            raise ValueError(
                f"{discovery_tool} returned an error response: "
                f"{_format_tool_error_response(response)}"
            )
        shops.extend(
            normalize_shop_records(
                tool_name=discovery_tool,
                source_user_key=str(user_key),
                records=records,
            )
        )
    unique = dedupe_authorized_shops(shops)
    if not unique:
        raise ValueError(f"{discovery_tool} did not return any authorized shops")
    if cache_path is not None:
        save_authorized_shop_cache(cache_path, unique)
    return unique


async def _call_discovery_tool_with_retries(
    client: LingxingMcpClient,
    discovery_tool: str,
    *,
    max_attempts: int = 3,
    retry_delay_seconds: float = 0.5,
) -> Any:
    last_response: Any = None
    for attempt in range(max_attempts):
        response = await client.call_tool(discovery_tool, {})
        if not is_transient_tool_error_response(response):
            return response
        last_response = response
        if attempt < max_attempts - 1:
            await asyncio.sleep(retry_delay_seconds * (attempt + 1))
    return last_response


def save_authorized_shop_cache(path: Path, shops: list[AuthorizedShop]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([shop.to_dict() for shop in shops], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_authorized_shop_cache(path: Path) -> list[AuthorizedShop]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [AuthorizedShop.from_dict(item) for item in data]


def _extract_records(response: Any, tool_name: str | None = None) -> list[dict[str, Any]]:
    if isinstance(response, list):
        return [item for item in response if isinstance(item, dict)]
    if isinstance(response, dict):
        if is_tool_error_response(response):
            return []
        for key in ("data", "rows", "list", "items", "records"):
            value = response.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = _extract_records(value, tool_name=tool_name)
                if nested or _contains_record_list_key(value):
                    return nested
        return [response]
    if isinstance(response, str) and tool_name == "get_my_sids":
        return _extract_get_my_sids_text_records(response)
    return []


def _extract_get_my_sids_text_records(response: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in response.splitlines():
        sid_match = re.search(r"\bsid\s*[:：]\s*(\d+)", line, flags=re.IGNORECASE)
        if sid_match is None:
            continue

        record: dict[str, Any] = {"sid": sid_match.group(1)}
        parts = [part.strip(" -\t") for part in re.split(r"[,，]", line) if part.strip()]
        name = _extract_shop_name_from_text_parts(parts)
        country = _extract_country_code(line, parts)
        if name:
            record["name"] = name
        if country:
            record["country"] = country
        records.append(record)
    return records


def _extract_shop_name_from_text_parts(parts: list[str]) -> str | None:
    for part in parts:
        lowered = part.lower()
        if "店铺名" in part or "shop_name" in lowered or lowered.startswith("name"):
            return _text_value_after_label(part)

    if len(parts) >= 2:
        return _text_value_after_label(parts[1])
    return None


def _text_value_after_label(text: str) -> str:
    for separator in (":", "：", "?"):
        if separator in text:
            return text.rsplit(separator, 1)[-1].strip()
    return text.strip()


def _extract_country_code(line: str, parts: list[str]) -> str | None:
    for part in parts:
        if "国家" in part or "country" in part.lower():
            matches = re.findall(r"\b[A-Z]{2}\b", part)
            if matches:
                return matches[-1]

    matches = re.findall(r"\b[A-Z]{2}\b", line)
    return matches[-1] if matches else None


def _contains_record_list_key(response: dict[str, Any]) -> bool:
    return any(isinstance(response.get(key), list) for key in ("data", "rows", "list", "items", "records"))


def is_tool_error_response(response: Any) -> bool:
    if not isinstance(response, dict):
        return False
    success = response.get("success")
    code = response.get("code")
    data = response.get("data")
    if success is False:
        return True
    if data is None and response.get("error_details"):
        return True
    if data is None and code not in (None, 1, "1"):
        return True
    return False


def is_transient_tool_error_response(response: Any) -> bool:
    if not isinstance(response, dict) or not is_tool_error_response(response):
        return False
    message = str(response.get("msg") or response.get("message") or "")
    return "服务器繁忙" in message or "server busy" in message.lower()


def _format_tool_error_response(response: Any) -> str:
    if not isinstance(response, dict):
        return str(response)

    parts: list[str] = []
    for key in ("code", "message", "msg", "traceId", "request_id"):
        value = response.get(key)
        if value not in (None, ""):
            parts.append(f"{key}={value}")

    error_details = response.get("error_details")
    if isinstance(error_details, list):
        details_text = "; ".join(str(item) for item in error_details)
    elif error_details:
        details_text = str(error_details)
    else:
        details_text = ""
    if details_text:
        parts.append(f"error_details={details_text}")

    return ", ".join(parts) if parts else str(response)


def _first_present(record: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None
