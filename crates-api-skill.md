# Crates API Skill

Use this skill when you need to interact with the local Crates DJ music library server from a macOS machine running Crates.app.

## What is Crates

Crates is a macOS app for DJs. It bundles a local Java server that exposes a REST API on `http://localhost:54735/resources`. The desktop UI talks to this server; the same API is available to code and LLMs using this skill.

## Basic Facts

- Base URL: `http://localhost:54735/resources`
- Authentication: send a `Client-ID` header (any string, default to `mcp-client`)
- Media type: `application/json` for most endpoints
- Spec: OpenAPI 3.0.3, generated directly from decompiled JAX-RS + Swagger annotations
- The current API version is `1.15.1` (check `specs/latest/openapi.yaml` for the latest version)

## When to Use This Skill

- Read or write crates, tunes, playlists, tags, artists, releases, labels, genres
- Search the library using the Lucene-backed `/search` endpoint
- Read or update user/configuration settings
- Trigger actions like `movetocrate`, `copyto`, `waveform.analyzer`, etc.
- Query external service connections (Spotify, SoundCloud, Discogs, YouTube, Google Drive, Last.fm, iTunes, Bandcamp, Genius)
- List or manipulate play-queue state, player targets, and waveforms

## How to Make Requests

If you are an LLM running via the MCP server, prefer the dedicated tools:

- `crates_health_check` - verify the server is up
- `crates_list_crates` - list all crates
- `crates_get_crate` - get one crate by ID
- `crates_get_crate_contents` - get crate contents
- `crates_search` - search the library
- `crates_list_tunes` - list tunes in a crate
- `crates_get_tune` - get a tune by ID
- `crates_add_tune_to_crate` - add a tune to a crate; only exposed when `CRATES_MCP_ALLOW_WRITES=true`
- `crates_remove_tune_from_crate` - remove a tune from a crate; only exposed when `CRATES_MCP_ALLOW_WRITES=true`
- `crates_list_endpoints` - list all available endpoints (optionally filtered by tag)
- `crates_api_request` - fallback for any endpoint not covered above

If you are generating code, use the Kotlin client in `crates-api-kotlin/` or read the OpenAPI spec directly.

## Important Usage Notes

1. **IDs are strings**. Even when the underlying Java type is `Long`, the REST layer accepts them as strings in path and query parameters.
2. **Always send Client-ID header**. Some endpoints return errors without it. Use a stable ID per client/session.
3. **Write endpoints may send JSON as a raw string body**. The OpenAPI spec declares `requestBody.content.schema.type: string` for some POST/PUT endpoints because the server accepts a plain JSON string body, not a typed object wrapper. Wrap your JSON in a string when the spec says so.
4. **Actions use the `/actions` tree**. Many batch operations (move to crate, copy to path, discogs lookup, waveform analysis, etc.) are triggered by creating an action object via `POST /actions/*`. Read the dedicated action endpoints before trying to hand-roll equivalent behavior.
5. **Search uses Lucene syntax**. `/search` accepts a `query` parameter with Lucene query syntax (e.g. `artist:"foo" title:bar`).
6. **Response schemas are inferred from presentation beans**. The generated OpenAPI spec contains 142 schemas under `#/components/schemas/`. Prefer named models over guessing field names.
7. **Check the spec before inventing endpoints**. The source is authoritative; the spec is regenerated from the actual bytecode every time Crates updates.

## Common Patterns

### List all crates and pick one

```python
import requests
base = "http://localhost:54735/resources"
headers = {"Client-ID": "my-script"}
resp = requests.get(f"{base}/crates", headers=headers)
resp.raise_for_status()
print(resp.json())
```

### Add a tune to a crate

```python
import requests
requests.post(
    f"{base}/crates/{crate_id}/tunes",
    headers={"Client-ID": "my-script", "Content-Type": "application/json"},
    data=tune_id  # plain string body
)
```

## Discovering Endpoints

- Read `specs/latest/openapi.yaml` for the full contract.
- Use `crates_list_endpoints` to get a quick tag-filtered list.
- When in doubt, use `crates_api_request` with `method`, `path`, and optional `query`/`body`.

## Safety Notes

- The MCP server is read-only by default. Set `CRATES_MCP_ALLOW_WRITES=true` only when the user has explicitly approved writes; otherwise mutating tools are hidden and raw `POST`, `PUT`, `PATCH`, and `DELETE` requests are blocked.
- This API can move, delete, rename, and write metadata to music files. Confirm destructive actions with the user before executing them.
- The server is local-only; there is no remote Crates API.
- Everything here is reverse-engineered from the app and only tested on macOS.
