# Phase 4: Search/Lookup, Single Record, Schema, Admin CRUD ✅ COMPLETE

## Goal
Universal search across any column (dataset-agnostic), single record by ID, schema endpoint, full admin CRUD.

---

## Tasks

### 4.1 Universal Search (`_search`) — in `app/services/query_builder.py`

**Concept:** Find records by *any* value without knowing column names. Dataset-agnostic.
- "tokyo" → matches city column, returns all Tokyo entries
- "tokyo japan" → narrows to Tokyo in Japan (fewer results)
- "springfield" → returns ALL Springfields (multiple matches)

- [x] Add `_search` parameter handling to `build_query`:
  - Split search term on spaces → multiple terms
  - For each term, build OR across ALL columns:
    - TEXT columns: `col LIKE ?` with `%term%`
    - INTEGER/REAL columns: `CAST(col AS TEXT) LIKE ?` with `%term%`
  - AND terms together: each term must match at least one column
  - Example: `_search=tokyo japan` →
    ```sql
    WHERE (city LIKE '%tokyo%' OR country LIKE '%tokyo%' OR CAST(population AS TEXT) LIKE '%tokyo%' OR ...)
      AND (city LIKE '%japan%' OR country LIKE '%japan%' OR CAST(population AS TEXT) LIKE '%japan%' OR ...)
    ```
- [x] `_search` can be combined with other filters (AND with explicit filters)
- [x] `_q` remains as TEXT-only search (backward compat), `_search` is universal

### 4.2 Schema Endpoint (`app/routers/collections.py`)
- [x] `GET /api/v1/collections/{name}/schema`
  - Returns `{"name": name, "columns": {"city": "TEXT", "population": "INTEGER", ...}}`
  - Uses `get_collection_or_404`

### 4.3 Single Record Endpoint (`app/routers/collections.py`)
- [x] `GET /api/v1/collections/{name}/{record_id:int}`
  - `SELECT * FROM {name} WHERE _id = ?`
  - Returns single dict or 404

### 4.4 Admin DELETE (`app/routers/admin.py`)
- [x] `DELETE /api/v1/admin/collections/{name}`
  - Calls `delete_collection` (DROP TABLE + DELETE metadata)
  - Returns 204 No Content

### 4.5 Admin PUT — Replace (`app/routers/admin.py`)
- [x] `PUT /api/v1/admin/collections/{name}`
  - Accepts UploadFile
  - Calls `import_csv(overwrite=True)`
  - Returns 200 with updated `CollectionMeta`

### 4.6 Admin POST — Append (`app/routers/admin.py`)
- [x] `POST /api/v1/admin/collections/{name}/append`
  - Accepts UploadFile
  - New function: `append_csv(db, name, file_content) -> CollectionMeta` in importer
  - Validates CSV headers match existing schema exactly
  - Inserts rows, updates row count
  - Returns 200 with updated metadata
  - Mismatched columns → 422

### 4.7 Tests
- [x] `tests/test_search.py`
  - Single term matches correct rows
  - Multi-term narrows results
  - Numeric column search works (e.g., search for "30")
  - No matches → empty data array
  - Works on any schema (dataset-agnostic)
- [x] `tests/test_collections_api.py` additions
  - Schema endpoint returns correct columns/types
  - Single record by ID
  - Single record 404 for missing ID
  - 401 without auth for schema and record endpoints
- [x] `tests/test_admin.py` additions
  - DELETE returns 204, collection gone
  - DELETE nonexistent → 404
  - PUT replaces data
  - PUT nonexistent → 404
  - Append adds rows, count increases
  - Append with mismatched columns → 422
  - Append nonexistent → 404
  - 401 without admin key for all new endpoints

---

## Verify
```bash
# Universal search
curl "http://localhost:8000/api/v1/collections/cities?_search=tokyo" -H "X-API-Key: test"
curl "http://localhost:8000/api/v1/collections/cities?_search=tokyo+japan" -H "X-API-Key: test"
# Schema
curl "http://localhost:8000/api/v1/collections/cities/schema" -H "X-API-Key: test"
# Single record
curl "http://localhost:8000/api/v1/collections/cities/42" -H "X-API-Key: test"
# Admin CRUD
curl -X DELETE "http://localhost:8000/api/v1/admin/collections/cities" -H "X-Admin-Key: test"
pytest tests/ -v
```
