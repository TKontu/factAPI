# Phase 6: MCP Server ✅ COMPLETE

## Goal
Expose factAPI collections as MCP tools so AI assistants (Claude Code, Claude Desktop, etc.) can query reference data directly.

---

## Concept

The MCP server runs as a separate process (stdio transport) but **reuses the same service layer** as the REST API. This is key for DRY — same `query_builder`, `collection_manager`, and `execute_query` functions.

```
Claude Desktop / Claude Code
    ↓ MCP (stdio)
app/mcp_server.py
    ↓ reuses
app/services/query_builder.py
app/services/collection_manager.py
app/database.py
    ↓
SQLite DB (read-only connection)
```

---

## Tasks

### 6.1 Dependencies
- [x] Add `mcp>=1.0.0` to `requirements.txt`

### 6.2 MCP Server (`app/mcp_server.py`)

**Tools to expose:**

| Tool | Params | Description |
|------|--------|-------------|
| `list_collections` | none | List all available collections with row counts |
| `query_collection` | `collection` (req), `filters` (dict), `sort`, `limit`, `offset`, `fields` (list) | Query with filters — translates to same `build_query` call |
| `search_collection` | `collection` (req), `search_term` (req), `limit` | Universal search — calls `build_query` with `_search` param |
| `get_record` | `collection` (req), `record_id` (req) | Get single record by ID |
| `get_schema` | `collection` (req) | Get column names and types |

**Resources to expose:**

| URI | Description |
|-----|-------------|
| `factapi://collections` | Dynamic list of all collections |
| `factapi://collections/{name}/schema` | Schema for a specific collection |

- [x] Implement MCP server using `mcp` Python SDK (`FastMCP` high-level API) with stdio transport
- [x] Open aiosqlite connection in read-only mode (`?mode=ro` URI)
- [x] Load settings from same `app/config.py`
- [x] Each tool function:
  1. Validates inputs
  2. Calls existing service functions
  3. Returns structured dict result
- [x] `query_collection` translates its filter dict into the format `build_query` expects (complete reuse)
- [x] `search_collection` is sugar: calls `build_query` with `_search` in params
- [x] Error handling: `NotFoundError` → `ToolError`, query builder errors → `ToolError`

### 6.3 Entry Point
- [x] Make runnable as `python -m app.mcp_server`
- [x] Add `__main__` block that starts the MCP server with stdio transport

### 6.4 Configuration Examples
- [x] Claude Desktop and Claude Code MCP config examples in README (completed in Phase 7)

### 6.5 Tests
- [x] `tests/test_mcp_server.py` — 17 tests across 5 test classes
  - `TestMcpListCollections`: returns both collections, includes metadata
  - `TestMcpGetSchema`: returns columns for people, JSON types for products, unknown → error
  - `TestMcpQueryCollection`: no filters, with filter, sort/limit/offset, fields, dot-notation JSON, invalid column → error, unknown collection → error
  - `TestMcpSearchCollection`: finds matching rows, no matches → empty
  - `TestMcpGetRecord`: returns correct record, missing ID → error, unknown collection → error

---

## Implementation Notes

- **Architecture:** Tool logic is in standalone async helper functions (`_list_collections`, `_get_schema`, `_query_collection`, `_search_collection`, `_get_record`) that accept `db` as first param. MCP `@mcp.tool()` handlers are thin wrappers that extract `db` from lifespan context and delegate. Tests call the helpers directly.
- **Lifespan:** Uses `AppContext` dataclass yielded from async context manager. DB available via `ctx.request_context.lifespan_context.db` in tools, and via `mcp._db` for the concrete `factapi://collections` resource (which doesn't receive context injection).
- **Resources:** `factapi://collections` is a concrete resource (no URI params, no context injection). `factapi://collections/{name}/schema` is a resource template (URI params + context injection).
- **17 new tests** (159 total, up from 142 in Phase 5)

---

## Verify
```bash
# Test standalone
python -m app.mcp_server  # Should start and accept stdio

# Configure in Claude Code, then ask:
# "What cities in Japan have population over 1 million?"
# → Claude uses query_collection tool
# "Find me Tokyo"
# → Claude uses search_collection tool

pytest tests/test_mcp_server.py -v
```
