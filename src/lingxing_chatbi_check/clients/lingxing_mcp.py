from __future__ import annotations

import json
from typing import Any


class LingxingMcpClient:
    def __init__(self, url: str, x_mcp_key: str) -> None:
        self.url = url
        self.x_mcp_key = x_mcp_key

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        try:
            import httpx2
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client
        except ImportError as exc:
            raise RuntimeError(
                "MCP client dependencies are not installed. Run `python -m pip install -e .`."
            ) from exc

        headers = {"X-Mcp-Key": self.x_mcp_key}
        async with httpx2.AsyncClient(headers=headers, follow_redirects=True) as http_client:
            transport = streamable_http_client(self.url, http_client=http_client)
            async with transport as streams:
                read_stream, write_stream, *_ = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments=arguments)

        structured = getattr(result, "structuredContent", None)
        if structured is not None:
            return structured

        content = getattr(result, "content", None) or []
        if not content:
            return result

        first = content[0]
        text = getattr(first, "text", None)
        if text is None:
            return result

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    async def list_tools(self) -> list[str]:
        try:
            import httpx2
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client
        except ImportError as exc:
            raise RuntimeError(
                "MCP client dependencies are not installed. Run `python -m pip install -e .`."
            ) from exc

        headers = {"X-Mcp-Key": self.x_mcp_key}
        async with httpx2.AsyncClient(headers=headers, follow_redirects=True) as http_client:
            transport = streamable_http_client(self.url, http_client=http_client)
            async with transport as streams:
                read_stream, write_stream, *_ = streams
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    response = await session.list_tools()

        return [tool.name for tool in response.tools]
