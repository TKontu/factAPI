# factAPI — Project Plan & Architecture

> A generic, schema-agnostic REST API for serving structured reference data.
> Upload a CSV → get a queryable API endpoint. No code changes per dataset.

---

## 1. Vision

Multiple projects need access to common reference data (cities, countries, currencies, timezones, etc.). Instead of embedding CSVs or duplicating databases, **factAPI** provides a single service that:

- Accepts any tabular dataset as a "collection"
- Auto-creates storage and endpoints from the data schema
- Exposes rich querying (filter, sort, search, paginate) on every collection
- Serves all your projects from one place on your home NAS

---

## 2. Tech Stack

| Layer         | Choice                  | Rationale                                       |
|---------------|-------------------------|-------------------------------------------------|
| Language      | Python 3.12+            | Ecosystem, familiarity                          |
| Framework     | FastAPI                 | Async, auto OpenAPI docs, type-safe             |
| Database      | SQLite (via aiosqlite)  | Zero config, file-based, perfect for NAS        |
| ORM / Query   | Raw SQL with aiosqlite  | Full control over dynamic schemas               |
| Auth          | API key (header-based)  | Simple, sufficient for internal services        |
| Logging       | structlog               | Structured JSON logs in production              |
| MCP           | mcp (FastMCP)           | AI assistant integration via stdio transport    |
| Container     | Docker                  | Single-container deploy                         |
| Deployment    | Portainer (from Git)    | GitOps workflow, no manual builds on NAS        |
| Docs          | Auto-generated OpenAPI  | Free from FastAPI, always up to date            |

**Why SQLite over Postgres?** For reference data (read-heavy, rarely updated, single-digit concurrent writers), SQLite is simpler, faster, and needs no separate container. If you outgrow it later, swap to Postgres — the query layer abstracts this.

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────┐
│                     factAPI                         │
│                                                     │
│  ┌──────────┐   ┌──────────────┐   ┌────────────┐  │
│  │  FastAPI  │──▶│ Query Engine │──▶│  SQLite DB │  │
│  │  Router   │   │  (dynamic)   │   │  (file)    │  │
│  └──────────┘   └──────────────┘   └────────────┘  │
│       │                                    ▲        │
│       ▼                                    │        │
│  ┌──────────┐   ┌──────────────┐           │        │
│  │  Admin   │──▶│ CSV Importer │───────────┘        │
│  │  Routes  │   │ (infer types)│                    │
│  └──────────┘   └──────────────┘                    │
│       │                                             │
│  ┌──────────┐   ┌──────────────┐                    │
│  │Middleware │   │  MCP Server  │──── stdio ────▶ AI│
│  │ (logging,│   │ (read-only)  │                    │
│  │  req ID) │   └──────────────┘                    │
│  └──────────┘                                       │
└─────────────────────────────────────────────────────┘
         ▲                          │
         │ HTTP                     │ Volume mount
    ┌────┴────┐              ┌──────┴──────┐
    │ Clients │              │ /data/factapi│
    │ (your   │              │  (NAS disk)  │
    │ projects)              └─────────────┘
    └─────────┘
```

### Request Flow

```
GET /api/v1/collections/cities?country=Japan&_sort=-population&_limit=10

  1. Middleware     → assigns request ID, starts timer
  2. Router         → resolves "cities" collection, validates it exists
  3. Query Builder  → constructs: SELECT * FROM cities
                                  WHERE country = 'Japan'
                                  ORDER BY population DESC
                                  LIMIT 10 OFFSET 0
  4. DB Executor    → runs query via aiosqlite
  5. Serializer     → returns JSON with metadata (total count, pagination)
  6. Middleware     → logs request_completed with duration, attaches X-Request-ID
```

---

## 4. Project Structure

```
factapi/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, lifespan, CORS, middleware registration
│   ├── config.py             # Settings via pydantic-settings (env vars)
│   ├── database.py           # SQLite connection management
│   ├── errors.py             # Exception hierarchy
│   ├── auth.py               # API key dependencies (with auth failure logging)
│   ├── logging.py            # structlog configuration (JSON/console rendering)
│   ├── middleware.py          # Request ID, request logging, exception safety net
│   ├── mcp_server.py         # MCP server (FastMCP, stdio transport, reuses services)
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── collections.py    # GET /api/v1/collections/{name} — query data
│   │   └── admin.py          # POST/PUT/DELETE admin endpoints (with operation logging)
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── importer.py       # CSV parsing, type inference (incl. JSON detection), table creation
│   │   ├── query_builder.py  # Dynamic WHERE, ORDER BY, LIMIT/OFFSET, dot-notation JSON queries
│   │   └── collection_manager.py  # CRUD for collection metadata
│   │
│   └── models/
│       ├── __init__.py
│       └── schemas.py        # Pydantic models for request/response
│
├── data/                     # SQLite DB lives here (volume-mounted)
├── seeds/                    # Example CSVs for initial data (cities, etc.)
│
├── tests/
│   ├── conftest.py
│   ├── test_health.py
│   ├── test_config.py
│   ├── test_importer.py
│   ├── test_auth.py
│   ├── test_admin.py
│   ├── test_query_builder.py
│   ├── test_collections_api.py
│   ├── test_search.py
│   ├── test_json_queries.py
│   ├── test_mcp_server.py
│   └── test_middleware.py
│
├── todo/                     # Phase-by-phase implementation plans
├── Dockerfile
├── docker-compose.yml        # Local development compose
├── docker-compose.prod.yml   # Remote deployment compose (GitHub → Portainer)
├── .env.example              # Local dev env template
├── stack.env.example         # Production env template (cp to stack.env, gitignored)
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── README.md
└── .gitignore
```

---

## 5. Core Concepts

### 5.1 Collections

A **collection** is a named dataset (e.g., `cities`, `currencies`). Each collection maps to:

- A SQLite table holding the actual data
- A metadata record tracking: name, column definitions, row count, created/updated timestamps

### 5.2 Type Inference

When a CSV is uploaded, the importer:

1. Reads headers → column names (sanitized to valid SQL identifiers)
2. Samples rows to infer types: `INTEGER`, `REAL`, `TEXT`, or `JSON`
3. JSON detection: if >50% of non-empty values in a column parse as JSON objects/arrays, the column is typed as `JSON`
4. Creates the table with inferred types (JSON stored as TEXT affinity in SQLite)
5. Bulk-inserts all rows

### 5.3 Query Parameters (Convention)

Every collection endpoint supports these query params:

| Param         | Example                          | Behavior                              |
|---------------|----------------------------------|---------------------------------------|
| `{column}`    | `?country=Japan`                 | Exact match filter                    |
| `{col}__gt`   | `?population__gt=1000000`        | Greater than                          |
| `{col}__lt`   | `?population__lt=500000`         | Less than                             |
| `{col}__gte`  | `?lat__gte=30`                   | Greater than or equal                 |
| `{col}__lte`  | `?lng__lte=100`                  | Less than or equal                    |
| `{col}__like` | `?city__like=New%`               | SQL LIKE pattern                      |
| `{col}__in`   | `?country__in=Japan,India`       | IN list                               |
| `_sort`       | `?_sort=-population`             | Sort (prefix `-` for DESC)            |
| `_limit`      | `?_limit=25`                     | Page size (default 100, max 1000)     |
| `_offset`     | `?_offset=50`                    | Skip rows                             |
| `_fields`     | `?_fields=city,country,population`| Select specific columns              |
| `_q`          | `?_q=tokyo`                      | Full-text search across TEXT/JSON columns |
| `_search`     | `?_search=tokyo japan`           | Universal search across ALL columns   |
| `{json}.path` | `?metadata.color=red`            | Dot-notation filter on JSON columns   |

### 5.4 Response Format

```json
{
  "collection": "cities",
  "total": 47868,
  "count": 2,
  "limit": 100,
  "offset": 0,
  "data": [
    {
      "city": "Tokyo",
      "country": "Japan",
      "population": 37785000,
      "lat": 35.687,
      "lng": 139.7495
    },
    {
      "city": "Osaka",
      "country": "Japan",
      "population": 15126000,
      "lat": 34.6939,
      "lng": 135.5022
    }
  ]
}
```

---

## 6. API Endpoints

### Public (require API key)

| Method | Path                                   | Description                    |
|--------|----------------------------------------|--------------------------------|
| GET    | `/api/v1/collections`                  | List all collections           |
| GET    | `/api/v1/collections/{name}`           | Query collection data          |
| GET    | `/api/v1/collections/{name}/schema`    | Get column names and types     |
| GET    | `/api/v1/collections/{name}/{id}`      | Get single record by ID        |

### Admin (require admin API key)

| Method | Path                                   | Description                     |
|--------|----------------------------------------|---------------------------------|
| POST   | `/api/v1/admin/collections`            | Create collection from CSV      |
| PUT    | `/api/v1/admin/collections/{name}`     | Replace collection data         |
| DELETE | `/api/v1/admin/collections/{name}`     | Drop collection                 |
| POST   | `/api/v1/admin/collections/{name}/append` | Add rows to existing collection |

### System

| Method | Path              | Description                |
|--------|-------------------|----------------------------|
| GET    | `/health`         | Health check               |
| GET    | `/docs`           | OpenAPI Swagger UI (auto)  |
| GET    | `/redoc`          | ReDoc (auto)               |

---

## 7. Configuration (Environment Variables)

```env
# .env.example
FACTAPI_ENV=development
FACTAPI_DB_PATH=data/factapi.db
FACTAPI_API_KEY=your-read-api-key
FACTAPI_ADMIN_KEY=your-admin-api-key
FACTAPI_DEFAULT_LIMIT=100
FACTAPI_MAX_LIMIT=1000
FACTAPI_CORS_ORIGINS=*
FACTAPI_LOG_LEVEL=info
```

---

## 8. Docker & Deployment

### Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/
RUN mkdir -p /data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml (local development)

```yaml
services:
  factapi:
    build: .
    ports:
      - "8484:8000"
    volumes:
      - ./data:/data
    env_file: .env
    environment:
      FACTAPI_DB_PATH: /data/factapi.db
      FACTAPI_ENV: production
    restart: unless-stopped
```

### docker-compose.prod.yml (remote deployment)

```yaml
services:
  factapi:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8484:8000"
    volumes:
      - factapi-data:/data
    env_file: stack.env
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s

volumes:
  factapi-data:
```

### Portainer Deployment

1. Push code to Git (GitHub/Gitea/etc.)
2. In Portainer → Stacks → Add Stack → "Repository"
3. Point to your repo URL, branch `main`, compose file `docker-compose.prod.yml`
4. Set environment variables in Portainer's UI (or upload `stack.env` from `stack.env.example`)
5. Deploy — Portainer builds and runs from Git
6. To update: push to `main` → redeploy stack in Portainer
7. Data persists in named Docker volume `factapi-data`

---

## 9. Observability

### Structured Logging

- **Production** (`FACTAPI_ENV=production`): JSON-formatted logs via structlog
- **Development**: Colored console output
- **Request-scoped context**: Every log line includes `request_id` via `structlog.contextvars`
- **Processors**: ISO timestamp, log level, logger name, callsite (module + function)

### Log Points

| Event | Level | Module |
|-------|-------|--------|
| `startup` / `shutdown` | INFO | `app.main` |
| `request_completed` (method, path, status, duration) | INFO | `app.middleware` |
| `unhandled_exception` | ERROR | `app.middleware` |
| `auth_failed` | WARNING | `app.auth` |
| `collection_created/deleted/replaced/appended` | INFO | `app.routers.admin` |
| `csv_imported` / `csv_appended` | INFO | `app.services.importer` |
| `query_executed` (collection, total, count, duration) | DEBUG | `app.routers.collections` |

### Request Middleware

- Generates `X-Request-ID` (UUID hex) on every request
- Logs `request_completed` with method, path, status_code, duration_ms
- Exception safety net: unhandled errors → generic 500 JSON, no internals leaked

---

## 10. High-Level TODO

### Phase 1 — Foundation ✅ COMPLETE
- [x] Project structure, pyproject.toml, requirements.txt
- [x] FastAPI app with health endpoint and CORS
- [x] Config via pydantic-settings
- [x] SQLite connection management (aiosqlite)
- [x] Error hierarchy (FactAPIError, NotFoundError, ValidationError, etc.)
- [x] Pydantic response schemas

### Phase 2 — CSV Import & Collections ✅ COMPLETE
- [x] CSV importer with type inference (INTEGER, REAL, TEXT)
- [x] Column name sanitization, collection name validation
- [x] `_collections_meta` table for tracking collections
- [x] Admin POST endpoint (upload CSV → create collection)
- [x] API key authentication (two-tier: read + admin)
- [x] List collections endpoint

### Phase 3 — Query Builder ✅ COMPLETE
- [x] Generic GET query endpoint with filtering
- [x] Comparison operators (__gt, __lt, __gte, __lte, __like, __in)
- [x] _fields for column selection
- [x] _q full-text search across TEXT columns
- [x] _sort (ASC/DESC), _limit, _offset pagination
- [x] Total count in response metadata

### Phase 4 — Search, CRUD & Schema ✅ COMPLETE
- [x] Universal _search across ALL columns (incl. CAST for numeric)
- [x] Schema endpoint per collection
- [x] Single-record GET by ID
- [x] Admin DELETE, PUT (replace), POST append endpoints

### Phase 5 — Nested JSON Support ✅ COMPLETE
- [x] JSON column detection during CSV import (>50% valid JSON → type "JSON")
- [x] Dot-notation filtering: `?metadata.color=red` → `json_extract()`
- [x] Dot-notation in _fields, _sort
- [x] Numeric comparison CAST for JSON-extracted values
- [x] _q and _search include JSON columns
- [x] JSON path sanitization (regex validation)

### Phase 6 — MCP Server ✅ COMPLETE
- [x] MCP server exposing collections as tools for AI assistants (`app/mcp_server.py`)
- [x] 5 tools: list_collections, get_schema, query_collection, search_collection, get_record
- [x] 2 resources: `factapi://collections`, `factapi://collections/{name}/schema`
- [x] Read-only DB connection (`?mode=ro` URI)
- [x] stdio transport via `FastMCP` high-level API
- [x] Testable architecture: standalone async helpers + thin MCP wrappers
- [x] Error handling: `NotFoundError`/`ValidationError` → `ToolError`

### Phase 7 — Production ✅ COMPLETE
- [x] Structured logging (structlog) — JSON in production, console in development
- [x] Request middleware (request ID, request logging, exception safety net)
- [x] Inline logging: auth failures, admin operations, query timing, CSV import
- [x] Dockerfile, docker-compose.yml (local), docker-compose.prod.yml (remote/Portainer)
- [x] `stack.env.example` for production env template (real `stack.env` gitignored)
- [x] Health check in production compose
- [x] README with usage examples, API reference, configuration
- [x] Security audit: no secrets committed, proper gitignore coverage
- [x] 162 tests passing, all lint checks clean

### Future / Nice to Have
- [ ] Web UI for browsing collections (simple React/HTML page)
- [ ] CSV export endpoint (GET /collections/{name}?_format=csv)
- [ ] Webhook on collection update
- [ ] Schema override on upload (explicit types via JSON)
- [ ] Caching layer (ETags or in-memory for hot collections)
- [ ] Optional Postgres backend (swap via config)
- [ ] Bulk import via JSON in addition to CSV

---

## 11. Security Notes

- **Two-tier keys**: read-only API key for clients, admin key for mutations
- **SQL injection prevention**: all dynamic queries use parameterized bindings, never string interpolation
- **Input validation**: column names validated against collection schema before query construction
- **JSON path safety**: dot-notation paths validated via regex `^[a-zA-Z0-9_.]+$`, base column must be JSON type
- **Exception safety**: unhandled exceptions return generic 500 with no internal details leaked
- **CORS**: configurable, default to restrictive in production
- **No public internet exposure needed**: runs on NAS, accessible within home network or via VPN/tunnel

---

## 12. Example Usage

```bash
# Upload a dataset
curl -X POST http://nas:8484/api/v1/admin/collections \
  -H "X-Admin-Key: your-admin-key" \
  -F "name=cities" \
  -F "file=@worldcities.csv"

# Query it
curl "http://nas:8484/api/v1/collections/cities?country=Japan&_sort=-population&_limit=5" \
  -H "X-API-Key: your-api-key"

# From any project (Python example)
import httpx
resp = httpx.get(
    "http://nas:8484/api/v1/collections/cities",
    params={"country": "Finland", "_sort": "city"},
    headers={"X-API-Key": "your-api-key"}
)
cities = resp.json()["data"]
```
