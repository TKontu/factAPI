# Architecture & Cross-Cutting Concerns — STATUS: ALL PHASES COMPLETE

## Project Structure

```
app/
├── __init__.py
├── main.py                  # FastAPI app, lifespan, CORS, middleware registration
├── config.py                # pydantic-settings (FACTAPI_* env vars)
├── database.py              # aiosqlite connection, query helpers
├── errors.py                # Exception hierarchy
├── auth.py                  # API key dependencies (read + admin)
├── logging.py               # structlog configuration (JSON/console rendering)
├── middleware.py             # Request ID, request logging, exception safety net
├── mcp_server.py            # MCP server (reuses services)
├── routers/
│   ├── __init__.py
│   ├── collections.py       # GET /api/v1/collections/...
│   └── admin.py             # POST/PUT/DELETE admin endpoints
├── services/
│   ├── __init__.py
│   ├── importer.py          # CSV parsing, type inference, JSON column detection
│   ├── query_builder.py     # Pure-function SQL builder, dot-notation JSON queries
│   └── collection_manager.py  # Collection metadata CRUD
└── models/
    ├── __init__.py
    └── schemas.py           # Pydantic request/response models
```

## DRY Abstractions

| Pattern | Module | Reused by |
|---------|--------|-----------|
| Collection exists? Get schema | `collection_manager.get_collection_or_404` | Every collection endpoint + MCP |
| Response envelope | `schemas.CollectionResponse` | Query, single record, search, MCP |
| Auth dependencies | `auth.require_api_key / require_admin_key` | All routers |
| Error types | `errors.py` | All modules |
| Column validation | `query_builder` (whitelist check) | Query, search, import validation |
| SQL execution helpers | `database.execute_query / execute_write` | All services |
| Name sanitization | `importer.sanitize_column_name` | Import, table creation |

## Security Checklist

- [x] Parameterized queries (`?` placeholders) — never string interpolation for values
- [x] Column names validated against schema whitelist before SQL placement
- [x] Table names validated via regex `^[a-z][a-z0-9_]{0,63}$`
- [x] `_collections_meta` reserved — rejected on create
- [x] API keys compared with `secrets.compare_digest` (timing-safe)
- [x] JSON paths: base column validated against schema, path regex-sanitized
- [x] MCP server opens DB in read-only mode (`?mode=ro` URI)
- [x] Unhandled exceptions → generic 500 (no internals leaked)
- [x] No secrets in committed files — `stack.env` gitignored, only `.example` templates committed

## Build Order

```
Phase 1: config → errors → database → schemas → main (health)              ✅ COMPLETE
Phase 2: importer → collection_manager → auth → admin router → collections ✅ COMPLETE
Phase 3: query_builder → collections (query endpoint)                       ✅ COMPLETE
Phase 4: search in query_builder → schema/single-record → admin CRUD       ✅ COMPLETE
Phase 5: JSON detection in importer → dot-notation in query_builder         ✅ COMPLETE
Phase 6: mcp_server (reuses services layer)                                 ✅ COMPLETE
Phase 7: logging → middleware → Dockerfile → docker-compose → README        ✅ COMPLETE
```

## Testing Strategy

### Fixture Hierarchy

```python
# conftest.py — built up across phases
settings_override   # temp DB, dummy API keys
app                 # FastAPI app with test settings
client              # httpx.AsyncClient
db                  # raw aiosqlite connection
sample_csv          # small CSV bytes (Phase 2)
json_csv            # CSV with JSON columns (Phase 5)
loaded_db           # db with sample collection (Phase 2)
authed_client       # client with X-API-Key (Phase 2)
admin_client        # client with X-Admin-Key (Phase 2)

# test_mcp_server.py — standalone fixture
mcp_db              # temp DB with people + products collections (Phase 6)
```

### Test Levels

- **Unit** (no DB/HTTP): query_builder, sanitize_column_name, infer_column_type, detect_json_column, config
- **Integration** (real SQLite): importer, collection_manager
- **API** (full stack via httpx): all endpoints, auth, errors, middleware

### Test Files (162 tests passing as of Phase 7)

```
tests/
├── conftest.py              # Fixtures: settings_override, app, client, authed_client, admin_client, db, sample_csv, json_csv
├── test_health.py           # Phase 1 ✅
├── test_config.py           # Phase 1 ✅
├── test_importer.py         # Phase 2 ✅
├── test_auth.py             # Phase 2 ✅
├── test_admin.py            # Phase 2 + 4 ✅ (create, delete, replace, append)
├── test_query_builder.py    # Phase 3 ✅ (most important)
├── test_collections_api.py  # Phase 3 + 4 ✅ (query, schema, single record)
├── test_search.py           # Phase 4 ✅ (unit + integration)
├── test_json_queries.py     # Phase 5 ✅ (detect_json_column, dot-notation, JSON filters, integration)
├── test_mcp_server.py       # Phase 6 ✅ (5 tools: list, schema, query, search, get_record)
└── test_middleware.py        # Phase 7 ✅ (request ID, 404, exception safety net)
```
