#!/usr/bin/env python3
"""Self-contained safety checks for the Crates MCP server."""

import asyncio
import importlib
import os

import server


def _load_server(*, allow_writes: bool):
    if allow_writes:
        os.environ["CRATES_MCP_ALLOW_WRITES"] = "true"
    else:
        os.environ.pop("CRATES_MCP_ALLOW_WRITES", None)
    return importlib.reload(server)


async def _call(module, name: str, arguments: dict):
    return await module.call_tool(name, arguments)


async def main():
    module = _load_server(allow_writes=False)

    tool_names = {tool.name for tool in module._list_dedicated_tools()}
    assert "crates_add_tune_to_crate" not in tool_names
    assert "crates_remove_tune_from_crate" not in tool_names

    calls = []

    def fake_api(method, path, *, params=None, body=None):
        calls.append((method, path, params, body))
        return {"status": 200, "body": "ok"}

    module._api = fake_api

    result = await _call(module, "crates_api_request", {"method": "POST", "path": "/crates/test"})
    assert "Writes are disabled" in result[0].text
    assert calls == []

    result = await _call(
        module,
        "crates_add_tune_to_crate",
        {"crateId": "crate-1", "tuneId": "tune-1"},
    )
    assert "Writes are disabled" in result[0].text
    assert calls == []

    result = await _call(module, "crates_api_request", {"method": "GET", "path": "https://example.test/crates"})
    assert "must start with '/'" in result[0].text
    assert calls == []

    result = await _call(module, "crates_api_request", {"method": "GET", "path": "//example.test/crates"})
    assert "absolute URLs" in result[0].text
    assert calls == []

    # Path traversal via '..' segments must be rejected before any request.
    result = await _call(module, "crates_api_request", {"method": "GET", "path": "/../../admin"})
    assert "'.' and '..'" in result[0].text
    assert calls == []

    result = await _call(module, "crates_api_request", {"method": "GET", "path": "/resources/../../admin"})
    assert "'.' and '..'" in result[0].text
    assert calls == []

    result = await _call(module, "crates_api_request", {"method": "GET", "path": "/crates"})
    assert result[0].text == '{\n  "status": 200,\n  "body": "ok"\n}'
    assert calls == [("GET", "/crates", None, None)]

    module = _load_server(allow_writes=True)
    calls = []
    module._api = fake_api

    tool_names = {tool.name for tool in module._list_dedicated_tools()}
    assert "crates_add_tune_to_crate" in tool_names
    assert "crates_remove_tune_from_crate" in tool_names

    result = await _call(module, "crates_api_request", {"method": "POST", "path": "/crates/test"})
    assert result[0].text == '{\n  "status": 200,\n  "body": "ok"\n}'
    assert calls == [("POST", "/crates/test", None, None)]

    # End-to-end: exercise the *real* _api URL construction (no fake) to prove a
    # traversal path cannot escape the /resources base prefix after normalization.
    module = _load_server(allow_writes=False)
    base = module.BASE_URL
    assert base.endswith("/resources")

    # A traversal that normalizes outside the base is refused by _api itself,
    # without ever issuing an HTTP request (requests is never reached).
    refused = module._api("GET", "/../../admin")
    assert refused["status"] is None
    assert "escapes API base path" in refused["error"]

    # Sanity: the base-relative resolution helper agrees with the guard.
    assert module._resolved_url_within_base("/crates/123")
    assert not module._resolved_url_within_base("/../../admin")
    assert not module._resolved_url_within_base("/resources/../../admin")

    os.environ.pop("CRATES_MCP_ALLOW_WRITES", None)
    print("MCP safety checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
