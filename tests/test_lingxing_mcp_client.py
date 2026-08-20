import sys
import types

import pytest

from lingxing_chatbi_check.clients.lingxing_mcp import LingxingMcpClient


def test_lingxing_mcp_client_stores_timeout_seconds() -> None:
    client = LingxingMcpClient(
        url="https://example.test/mcp",
        x_mcp_key="secret",
        timeout_seconds=180,
    )

    assert client.timeout_seconds == 180


@pytest.mark.anyio
async def test_lingxing_mcp_client_reuses_initialized_session_inside_context(
    monkeypatch,
) -> None:
    state = {
        "http_client_entries": 0,
        "transport_entries": 0,
        "session_entries": 0,
        "initialize_calls": 0,
        "tool_calls": [],
    }

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            state["http_client_entries"] += 1
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class FakeTransport:
        async def __aenter__(self):
            state["transport_entries"] += 1
            return ("read", "write")

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class FakeSession:
        def __init__(self, read_stream, write_stream):
            self.read_stream = read_stream
            self.write_stream = write_stream

        async def __aenter__(self):
            state["session_entries"] += 1
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

        async def initialize(self):
            state["initialize_calls"] += 1

        async def call_tool(self, tool_name, arguments):
            state["tool_calls"].append((tool_name, arguments))
            return types.SimpleNamespace(
                structuredContent={"call_number": len(state["tool_calls"])}
            )

    httpx2 = types.ModuleType("httpx2")
    httpx2.AsyncClient = FakeAsyncClient
    mcp = types.ModuleType("mcp")
    mcp.ClientSession = FakeSession
    streamable_http = types.ModuleType("mcp.client.streamable_http")
    streamable_http.streamable_http_client = (
        lambda _url, http_client: FakeTransport()
    )

    monkeypatch.setitem(sys.modules, "httpx2", httpx2)
    monkeypatch.setitem(sys.modules, "mcp", mcp)
    monkeypatch.setitem(sys.modules, "mcp.client", types.ModuleType("mcp.client"))
    monkeypatch.setitem(
        sys.modules,
        "mcp.client.streamable_http",
        streamable_http,
    )

    client = LingxingMcpClient(
        url="https://example.test/mcp",
        x_mcp_key="secret",
    )

    async with client:
        first = await client.call_tool("tool_a", {"page": 1})
        second = await client.call_tool("tool_b", {"page": 2})

    assert first == {"call_number": 1}
    assert second == {"call_number": 2}
    assert state["http_client_entries"] == 1
    assert state["transport_entries"] == 1
    assert state["session_entries"] == 1
    assert state["initialize_calls"] == 1
    assert state["tool_calls"] == [
        ("tool_a", {"page": 1}),
        ("tool_b", {"page": 2}),
    ]


@pytest.mark.anyio
async def test_lingxing_mcp_client_does_not_mask_body_error_with_close_error() -> None:
    client = LingxingMcpClient(
        url="https://example.test/mcp",
        x_mcp_key="secret",
    )

    class BrokenCloseContext:
        async def __aexit__(self, exc_type, exc, traceback):
            raise RuntimeError(
                "Attempted to exit cancel scope in a different task than it was entered in"
            )

    body_error = TimeoutError("tool timed out")
    client._session_context = BrokenCloseContext()

    await client.__aexit__(type(body_error), body_error, body_error.__traceback__)


@pytest.mark.anyio
async def test_lingxing_mcp_client_resets_session_after_call_failure(
    monkeypatch,
) -> None:
    state = {
        "http_client_entries": 0,
        "transport_entries": 0,
        "session_entries": 0,
        "session_exits": 0,
        "tool_calls": 0,
    }

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            state["http_client_entries"] += 1
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class FakeTransport:
        async def __aenter__(self):
            state["transport_entries"] += 1
            return ("read", "write")

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class FakeSession:
        def __init__(self, read_stream, write_stream):
            self.session_number = state["session_entries"] + 1

        async def __aenter__(self):
            state["session_entries"] += 1
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            state["session_exits"] += 1
            return False

        async def initialize(self):
            pass

        async def call_tool(self, tool_name, arguments):
            state["tool_calls"] += 1
            if self.session_number == 1:
                raise TimeoutError("tool timed out")
            return types.SimpleNamespace(structuredContent={"ok": True})

    httpx2 = types.ModuleType("httpx2")
    httpx2.AsyncClient = FakeAsyncClient
    mcp = types.ModuleType("mcp")
    mcp.ClientSession = FakeSession
    streamable_http = types.ModuleType("mcp.client.streamable_http")
    streamable_http.streamable_http_client = (
        lambda _url, http_client: FakeTransport()
    )

    monkeypatch.setitem(sys.modules, "httpx2", httpx2)
    monkeypatch.setitem(sys.modules, "mcp", mcp)
    monkeypatch.setitem(sys.modules, "mcp.client", types.ModuleType("mcp.client"))
    monkeypatch.setitem(
        sys.modules,
        "mcp.client.streamable_http",
        streamable_http,
    )

    client = LingxingMcpClient(
        url="https://example.test/mcp",
        x_mcp_key="secret",
    )

    async with client:
        with pytest.raises(TimeoutError):
            await client.call_tool("tool_a", {"page": 1})
        result = await client.call_tool("tool_a", {"page": 1})

    assert result == {"ok": True}
    assert state["session_entries"] == 2
    assert state["session_exits"] == 2
