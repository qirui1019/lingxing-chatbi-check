from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_env_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Environment config not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Environment config must be a YAML mapping: {path}")

    return data


def get_mcp_user_config(config: dict[str, Any], user_key: str) -> dict[str, str]:
    users = config.get("lingxing_mcp", {}).get("users", {})
    if user_key not in users:
        raise KeyError(f"MCP user alias not found: {user_key}")

    user_config = users[user_key]
    if not isinstance(user_config, dict) or not user_config.get("x_mcp_key"):
        raise ValueError(f"MCP user alias must define x_mcp_key: {user_key}")

    return {"x_mcp_key": str(user_config["x_mcp_key"])}
