# crates-api

Public artifacts for the Crates DJ music library API. Reverse-engineered from the macOS app.

## What's Inside

- `specs/` - OpenAPI 3.0.3 specs per Crates.app version. `specs/latest` is a symlink to the newest version.
- `crates-api-kotlin/` - Kotlin client library generated from the OpenAPI spec (Ktor + coroutines + kotlinx.serialization).
- `crates-api-mcp/` - MCP server exposing the Crates API to LLMs.
- `crates-api-skill.md` - Skill file / system prompt for LLMs that need to use the API.

## Latest Version

`1.15.1` - see `specs/latest/openapi.yaml`.

## Requirements & Notes

- Everything here is **only tested on macOS**.
- The Crates server must be running locally (Crates.app must be open).
- The API is at `http://localhost:54735/resources`.
- Most endpoints require a `Client-ID` header.

## Specs

```bash
ls specs/latest/openapi.yaml
```

If a new Crates release has no spec changes, the tooling symlinks its version folder to the previous version's folder.

## Kotlin Client

### Build

```bash
cd crates-api-kotlin
./gradlew build
```

### Use

```kotlin
import io.crates.api.apis.CratesApi
import kotlinx.coroutines.runBlocking

runBlocking {
    val client = CratesApi()
    // Sets the Client-ID header for requests.
    client.setApiKey("my-client-id")
    val response = client.cratesGetAllCrates(clientID = null, callbacks = null)
    println(response.body())
}
```

Pass `clientID` to individual calls only when you need to override the globally configured `Client-ID` header.

The artifact is published as `io.crates:crates-api:1.0.0` from the generated `publishing` block. You can import it locally or publish to Maven Local with `./gradlew publishToMavenLocal`.

## MCP Server

### Install

```bash
cd crates-api-mcp
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure (for Claude / other MCP clients)

```json
{
  "mcpServers": {
    "crates": {
      "command": "/path/to/crates-api/crates-api-mcp/.venv/bin/python",
      "args": ["/path/to/crates-api/crates-api-mcp/server.py"]
    }
  }
}
```

### Environment Variables

- `CRATES_BASE_URL` - default `http://localhost:54735/resources`
- `CRATES_CLIENT_ID` - default `mcp-client`
- `CRATES_MCP_ALLOW_WRITES` - default unset/false. Set to `true` to expose mutating MCP tools and allow raw `POST`, `PUT`, `PATCH`, and `DELETE` requests.

The MCP server is read-only by default. Dedicated write tools such as adding or removing tunes from crates are hidden unless `CRATES_MCP_ALLOW_WRITES=true`, and raw non-`GET` requests return a blocked-write response.

## Skill File

For LLMs that support skill files, point them at `crates-api-skill.md`. It covers base URL, auth, common endpoints, and safety notes.
