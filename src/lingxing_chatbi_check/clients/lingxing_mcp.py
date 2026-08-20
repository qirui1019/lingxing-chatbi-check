from __future__ import annotations

import json
from typing import Any


class LingxingMcpClient:
    def __init__(
        self,
        url: str,
        x_mcp_key: str,
        timeout_seconds: float = 120,
    ) -> None:
        self.url = url
        self.x_mcp_key = x_mcp_key
        self.timeout_seconds = timeout_seconds
        self._http_client_context: Any | None = None
        self._http_client: Any | None = None
        self._transport_context: Any | None = None
        self._session_context: Any | None = None
        self._session: Any | None = None

    async def __aenter__(self) -> "LingxingMcpClient":
        await self._open_session()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        await self._close_session(exc_type, exc, traceback)
        return False

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if self._session is not None:
            try:
                result = await self._session.call_tool(tool_name, arguments=arguments)
                return _parse_tool_result(result)
            except BaseException:
                await self.reset_session()
                raise

        async with self:
            return await self.call_tool(tool_name, arguments)

    async def list_tools(self) -> list[str]:
        if self._session is not None:
            response = await self._session.list_tools()
            return [tool.name for tool in response.tools]

        async with self:
            return await self.list_tools()

    async def _open_session(self) -> None:
        if self._session is not None:
            return
        try:
            import httpx2
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client
        except ImportError as exc:
            raise RuntimeError(
                "MCP client dependencies are not installed. Run `python -m pip install -e .`."
            ) from exc

        headers = {"X-Mcp-Key": self.x_mcp_key}
        self._http_client_context = httpx2.AsyncClient(
            headers=headers,
            follow_redirects=True,
            timeout=self.timeout_seconds,
        )
        self._http_client = await self._http_client_context.__aenter__()
        self._transport_context = streamable_http_client(
            self.url,
            http_client=self._http_client,
        )
        streams = await self._transport_context.__aenter__()
        read_stream, write_stream, *_ = streams
        self._session_context = ClientSession(read_stream, write_stream)
        self._session = await self._session_context.__aenter__()
        await self._session.initialize()

    async def _close_session(
        self,
        exc_type: Any = None,
        exc: Any = None,
        traceback: Any = None,
    ) -> None:
        session_context = self._session_context
        transport_context = self._transport_context
        http_client_context = self._http_client_context
        self._session = None
        self._session_context = None
        self._transport_context = None
        self._http_client = None
        self._http_client_context = None

        close_error: BaseException | None = None
        for context in (session_context, transport_context, http_client_context):
            if context is None:
                continue
            try:
                await context.__aexit__(exc_type, exc, traceback)
            except BaseException as error:
                if exc_type is not None:
                    continue
                if close_error is None:
                    close_error = error
        if close_error is not None:
            raise close_error

    async def reset_session(self) -> None:
        try:
            await self._close_session()
        except BaseException:
            pass


def _parse_tool_result(result: Any) -> Any:
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
