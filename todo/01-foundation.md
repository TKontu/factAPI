# Phase 1: Foundation — Config, Database, Health ✅ COMPLETE

## Goal
Running FastAPI app with configuration, database connectivity, error handling, and health endpoint.

---

## Tasks

### 1.1 Dependencies
- [x] Create `requirements.txt`: fastapi, uvicorn[standard], aiosqlite, pydantic-settings, structlog, python-multipart
- [x] Create `requirements-dev.txt`: pytest, pytest-asyncio, httpx, coverage, ruff, mypy
- [x] `pip install -r requirements.txt -r requirements-dev.txt`

### 1.2 Config (`app/config.py`)
- [x] Create `app/__init__.py`
- [x] Create `Settings(BaseSettings)` with prefix `FACTAPI_`
  - `db_path: str = "data/factapi.db"`
  - `api_key: str = ""`
  - `admin_key: str = ""`
  - `default_limit: int = 100`
  - `max_limit: int = 1000`
  - `cors_origins: str = "*"`
  - `log_level: str = "info"`
- [x] `get_settings()` with `@lru_cache` for testability
- [x] `cors_origins_list` property that splits on commas

### 1.3 Errors (`app/errors.py`)
- [x] `FactAPIError(Exception)` base with `message`, `code`, `status_code`
- [x] `NotFoundError` — 404, `NOT_FOUND`
- [x] `ValidationError` — 422, `VALIDATION_ERROR`
- [x] `AuthenticationError` — 401, `UNAUTHORIZED`
- [x] `ConflictError` — 409, `CONFLICT`

### 1.4 Database (`app/database.py`)
- [x] aiosqlite connection opened/closed via lifespan
- [x] Enable WAL mode + foreign keys on connect
- [x] `execute_query(db, sql, params) -> list[dict]` — SELECT helper, returns rows as dicts
- [x] `execute_write(db, sql, params) -> int` — INSERT/UPDATE/DELETE, returns rowcount

### 1.5 Schemas (`app/models/schemas.py`)
- [x] Create `app/models/__init__.py`
- [x] `HealthResponse(BaseModel)`: status, version
- [x] `ErrorDetail(BaseModel)`: code, message
- [x] `ErrorResponse(BaseModel)`: error (ErrorDetail)

### 1.6 Main App (`app/main.py`)
- [x] Lifespan: open DB, create `_collections_meta` table, yield, close DB
- [x] `_collections_meta` schema:
  ```sql
  name TEXT PRIMARY KEY,
  columns_json TEXT NOT NULL,
  row_count INTEGER DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
  ```
- [x] CORS middleware from `settings.cors_origins_list`
- [x] Exception handler for `FactAPIError` → JSON `ErrorResponse`
- [x] `GET /health` → `{"status": "healthy", "version": "0.1.0"}`
- [x] Create `app/routers/__init__.py`

### 1.7 Update .env.example
- [x] Replace Postgres/Redis placeholders with FACTAPI_* vars

### 1.8 Tests
- [x] Create `tests/__init__.py`
- [x] Create `tests/conftest.py` with fixtures: `settings_override`, `app`, `client`, `db`
- [x] Create `tests/test_health.py` — 200, correct response shape
- [x] Create `tests/test_config.py` — settings load correctly, defaults work

---

## Verify
```bash
uvicorn app.main:app --reload
curl http://localhost:8000/health
pytest tests/test_health.py tests/test_config.py -v
```
