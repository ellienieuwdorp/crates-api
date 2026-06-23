#!/usr/bin/env python3
"""
Crates API MCP Server.

Exposes the Crates.app REST API as MCP tools so LLMs can interact with it.
The server reads the OpenAPI spec from the local specs folder and turns the most
common read/write endpoints into a focused set of tools. LLMs can also fall back
on `crates_api_request` for endpoints not covered by a dedicated tool.

Requirements:
    pip install -r requirements.txt

Usage:
    python server.py

The server connects to the Crates server at http://localhost:54735/resources.
Set CRATES_BASE_URL and CRATES_CLIENT_ID to override defaults. The server is
read-only by default; set CRATES_MCP_ALLOW_WRITES=true to enable mutating API
tools and raw non-GET requests.
"""

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import yaml
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("CRATES_BASE_URL", "http://localhost:54735/resources")
CLIENT_ID = os.environ.get("CRATES_CLIENT_ID", "mcp-client")
SPEC_DIR = Path(__file__).resolve().parent.parent / "specs"
ALLOW_WRITES = os.environ.get("CRATES_MCP_ALLOW_WRITES", "").lower() in {"1", "true", "yes", "on"}
READ_METHODS = {"GET"}
WRITE_METHODS = {"POST", "PUT", "DELETE", "PATCH"}
SUPPORTED_METHODS = READ_METHODS | WRITE_METHODS
MUTATING_TOOL_NAMES = frozenset(
    {
        "crates_add_tune_to_crate",
        "crates_remove_tune_from_crate",
    }
)


def _load_spec() -> dict:
    """Load the latest OpenAPI spec from specs/latest/openapi.yaml."""
    latest = (SPEC_DIR / "latest" / "openapi.yaml").resolve()
    if not latest.exists():
        latest = SPEC_DIR / "latest" / "openapi.yaml"
    if not latest.exists():
        raise RuntimeError(f"Could not find spec at {latest}")
    return yaml.safe_load(latest.read_text())


SPEC = _load_spec()


def _write_disabled_text(action: str) -> TextContent:
    return TextContent(
        type="text",
        text=(
            f"Writes are disabled for this Crates MCP server; blocked {action}. "
            "Restart the server with CRATES_MCP_ALLOW_WRITES=true to enable mutating tools "
            "and raw POST/PUT/PATCH/DELETE requests."
        ),
    )


def _error_text(message: str) -> TextContent:
    return TextContent(type="text", text=message)


def _validate_raw_request_path(path: Any) -> str | None:
    if not isinstance(path, str) or not path:
        return "Invalid path: path must be a non-empty string starting with '/'."
    if path != path.strip():
        return "Invalid path: path must not contain leading or trailing whitespace."
    if not path.startswith("/"):
        return "Invalid path: raw request paths must start with '/'."
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or path.startswith("//"):
        return "Invalid path: absolute URLs and network-location paths are not allowed."
    if re.search(r"[A-Za-z][A-Za-z0-9+.-]*://", path):
        return "Invalid path: paths must not contain absolute URLs."
    if any(segment in (".", "..") for segment in parsed.path.split("/")):
        return "Invalid path: '.' and '..' path segments are not allowed."
    if not _resolved_url_within_base(path):
        return "Invalid path: resolved URL escapes the API base path."
    return None


def _resolved_url_within_base(path: str) -> bool:
    """Resolve path against BASE_URL and verify it stays under BASE_URL."""
    base = BASE_URL if BASE_URL.endswith("/") else BASE_URL + "/"
    resolved = urljoin(base, path.lstrip("/"))
    return resolved == BASE_URL or resolved.startswith(base)


def _api(method: str, path: str, *, params: dict | None = None, body: Any = None):
    """Make a request to the Crates API."""
    url = f"{BASE_URL}{path}"
    # Normalize the final URL and ensure it cannot escape BASE_URL (e.g. via
    # '../' segments that requests would otherwise collapse before sending).
    if not _resolved_url_within_base(path):
        return {"status": None, "error": f"Refusing request: URL escapes API base path: {url}"}
    headers = {"Client-ID": CLIENT_ID}
    if body is not None and not isinstance(body, str):
        body = json.dumps(body)
        headers["Content-Type"] = "application/json"
    try:
        resp = requests.request(method.upper(), url, headers=headers, params=params or {}, data=body, timeout=30)
        resp.raise_for_status()
        return {"status": resp.status_code, "body": resp.text[:4000]}
    except requests.exceptions.RequestException as e:
        return {"status": getattr(e.response, "status_code", None), "error": str(e)}


def _path_for(operation_id: str) -> tuple[str, str, str] | None:
    """Find (method, path, summary) for a given operationId."""
    for path, ops in SPEC["paths"].items():
        for method, op in ops.items():
            if op.get("operationId") == operation_id:
                return method, path, op.get("summary", "")
    return None


def _list_dedicated_tools() -> list[Tool]:
    """Return a curated list of MCP tools mapped from the spec."""
    raw_request_description = "Make a raw GET request to any Crates API endpoint. Use when no dedicated tool exists."
    if ALLOW_WRITES:
        raw_request_description = "Make a raw request to any Crates API endpoint. Use when no dedicated tool exists."

    tools = [
        Tool(
            name="crates_health_check",
            description="Check if the Crates server is reachable.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="crates_list_crates",
            description="List all top-level crates (returns CratePresentationBean objects).",
            inputSchema={"type": "object", "properties": {"clientID": {"type": "string"}}},
        ),
        Tool(
            name="crates_get_crate",
            description="Get a single crate by ID.",
            inputSchema={"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
        ),
        Tool(
            name="crates_get_crate_contents",
            description="Get contents of a crate by ID.",
            inputSchema={"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
        ),
        Tool(
            name="crates_search",
            description="Search the Crates library (Lucene-backed).",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Lucene search query"},
                    "offset": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="crates_list_tunes",
            description="List tunes in a crate.",
            inputSchema={
                "type": "object",
                "properties": {
                    "crateId": {"type": "string"},
                    "offset": {"type": "integer"},
                    "limit": {"type": "integer"},
                },
                "required": ["crateId"],
            },
        ),
        Tool(
            name="crates_get_tune",
            description="Get a tune by ID.",
            inputSchema={"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]},
        ),
        Tool(
            name="crates_add_tune_to_crate",
            description="Add a tune to a crate. Requires CRATES_MCP_ALLOW_WRITES=true.",
            inputSchema={
                "type": "object",
                "properties": {
                    "crateId": {"type": "string"},
                    "tuneId": {"type": "string"},
                },
                "required": ["crateId", "tuneId"],
            },
        ),
        Tool(
            name="crates_remove_tune_from_crate",
            description="Remove a tune from a crate. Requires CRATES_MCP_ALLOW_WRITES=true.",
            inputSchema={
                "type": "object",
                "properties": {
                    "crateId": {"type": "string"},
                    "tuneId": {"type": "string"},
                },
                "required": ["crateId", "tuneId"],
            },
        ),
        Tool(
            name="crates_api_request",
            description=raw_request_description,
            inputSchema={
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"]},
                    "path": {"type": "string", "description": "API path relative to /resources, e.g. /tunes/123"},
                    "query": {"type": "object", "description": "Optional query parameters"},
                    "body": {"type": "string", "description": "Optional raw JSON body"},
                },
                "required": ["method", "path"],
            },
        ),
        Tool(
            name="crates_list_endpoints",
            description="List all available API endpoints with their method and summary.",
            inputSchema={
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "description": "Optional filter by tag, e.g. 'crates' or 'tunes'"}
                }
            },
        ),
    ]
    if not ALLOW_WRITES:
        tools = [tool for tool in tools if tool.name not in MUTATING_TOOL_NAMES]
    return tools


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

app = Server("crates-api-mcp")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return _list_dedicated_tools()


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name in MUTATING_TOOL_NAMES and not ALLOW_WRITES:
        return [_write_disabled_text(name)]

    if name == "crates_health_check":
        result = _api("GET", "/actions/test")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "crates_list_crates":
        result = _api("GET", "/crates")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "crates_get_crate":
        result = _api("GET", f"/crates/{arguments['id']}")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "crates_get_crate_contents":
        result = _api("GET", f"/crates/{arguments['id']}/contents")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "crates_search":
        params = {"query": arguments["query"]}
        if "offset" in arguments:
            params["offset"] = arguments["offset"]
        if "limit" in arguments:
            params["limit"] = arguments["limit"]
        result = _api("GET", "/search", params=params)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "crates_list_tunes":
        params = {}
        if "offset" in arguments:
            params["offset"] = arguments["offset"]
        if "limit" in arguments:
            params["limit"] = arguments["limit"]
        result = _api("GET", f"/crates/tunes/{arguments['crateId']}", params=params)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "crates_get_tune":
        result = _api("GET", f"/tunes/{arguments['id']}")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "crates_add_tune_to_crate":
        body = arguments.get("tuneId")
        result = _api("POST", f"/crates/{arguments['crateId']}/tunes", body=body)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "crates_remove_tune_from_crate":
        result = _api("DELETE", f"/crates/{arguments['crateId']}/tunes/{arguments['tuneId']}")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "crates_api_request":
        method = str(arguments["method"]).upper()
        if method not in SUPPORTED_METHODS:
            supported = ", ".join(sorted(SUPPORTED_METHODS))
            return [_error_text(f"Unsupported method: {method}. Supported methods: {supported}.")]
        if method in WRITE_METHODS and not ALLOW_WRITES:
            return [_write_disabled_text(f"raw {method} request")]
        path_error = _validate_raw_request_path(arguments["path"])
        if path_error:
            return [_error_text(path_error)]
        result = _api(
            method,
            arguments["path"],
            params=arguments.get("query"),
            body=arguments.get("body"),
        )
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "crates_list_endpoints":
        tag_filter = arguments.get("tag")
        rows = []
        for path, ops in SPEC["paths"].items():
            for method, op in ops.items():
                if method not in ("get", "post", "put", "delete", "patch"):
                    continue
                tags = op.get("tags", [])
                if tag_filter and tag_filter not in tags:
                    continue
                rows.append(f"{method.upper()} {path} - {op.get('summary', '')}")
        text = "\n".join(sorted(rows))[:8000]
        return [TextContent(type="text", text=text)]

    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as streams:
        await app.run(streams[0], streams[1], app.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
