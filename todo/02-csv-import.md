# Phase 2: CSV Import & Collection Management ✅ COMPLETE

## Goal
Upload a CSV file → creates a queryable SQLite table with metadata. Auth and list collections work.

---

## Tasks

### 2.1 Importer Service (`app/services/importer.py`)
- [x] Create `app/services/__init__.py`
- [x] `sanitize_column_name(raw: str) -> str`
  - Lowercase, replace non-alnum with `_`, strip leading digits
  - Validate against `^[a-z][a-z0-9_]{0,63}$`
  - Reject empty strings
- [x] `infer_column_type(values: list[str]) -> str`
  - Sample up to 100 non-empty values
  - Try `int()` then `float()`, fallback `TEXT`
  - Return `"INTEGER"`, `"REAL"`, or `"TEXT"`
- [x] `import_csv(db, name, file_content, overwrite=False) -> CollectionMeta`
  - Parse CSV (csv.reader, UTF-8 assumed)
  - Sanitize headers → column names
  - Infer types from row values
  - Validate collection name: `^[a-z][a-z0-9_]{0,63}$`, reject `_collections_meta`
  - If not overwrite and table exists → raise `ConflictError`
  - If overwrite and table exists → DROP TABLE
  - CREATE TABLE with `_id INTEGER PRIMARY KEY AUTOINCREMENT` + inferred columns
  - Batch INSERT rows (batches of 1000)
  - Insert/update `_collections_meta` record
  - Return `CollectionMeta`

### 2.2 Collection Manager (`app/services/collection_manager.py`)
- [x] `list_collections(db) -> list[CollectionMeta]`
- [x] `get_collection(db, name) -> CollectionMeta | None`
- [x] `get_collection_or_404(db, name) -> CollectionMeta` — raises `NotFoundError` if None
- [x] `delete_collection(db, name) -> None` — DROP TABLE + DELETE metadata
- [x] `update_row_count(db, name) -> None` — COUNT(*) and update metadata

### 2.3 Auth (`app/auth.py`)
- [x] `require_api_key(request) -> str` — checks `X-API-Key` header via `secrets.compare_digest`
- [x] `require_admin_key(request) -> str` — checks `X-Admin-Key` header
- [x] Skip auth if respective key setting is empty (local dev convenience)

### 2.4 Schemas additions (`app/models/schemas.py`)
- [x] `CollectionMeta(BaseModel)`: name, columns (dict[str, str]), row_count, created_at, updated_at
- [x] `CollectionListResponse(BaseModel)`: collections (list[CollectionMeta])

### 2.5 Admin Router (`app/routers/admin.py`)
- [x] `POST /api/v1/admin/collections` — Form(name) + File(upload), calls `import_csv`, returns 201
- [x] Depends on `require_admin_key`

### 2.6 Collections Router (`app/routers/collections.py`)
- [x] `GET /api/v1/collections` — list all collections
- [x] Depends on `require_api_key`

### 2.7 Wire routers into `app/main.py`

### 2.8 Tests
- [x] `tests/conftest.py` additions: `sample_csv`, `loaded_db`, `authed_client`, `admin_client` fixtures
- [x] `tests/test_importer.py`
  - sanitize_column_name edge cases (spaces, special chars, leading digits, unicode)
  - infer_column_type (int, float, text, mixed, empty)
  - Full import with small CSV (5 rows, 3 columns)
  - Duplicate name → ConflictError
  - overwrite=True replaces data
- [x] `tests/test_auth.py` — valid key passes, invalid 401, missing 401
- [x] `tests/test_admin.py` — POST 201, POST without key 401, POST duplicate 409

---

## Verify
```bash
curl -X POST http://localhost:8000/api/v1/admin/collections \
  -H "X-Admin-Key: test" -F "name=cities" -F "file=@data/worldcities.csv"
curl http://localhost:8000/api/v1/collections -H "X-API-Key: test"
pytest tests/ -v
```
