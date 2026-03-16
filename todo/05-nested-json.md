# Phase 5: Nested JSON Support ✅ COMPLETE

## Goal
Support complex/nested data in columns using SQLite's JSON functions. Enables datasets with structured fields.

---

## Concept

Some CSV columns may contain JSON objects/arrays, e.g.:

```csv
name,metadata,tags
Widget A,"{""color"":""red"",""size"":10}","[""sale"",""new""]"
Widget B,"{""color"":""blue"",""size"":25}","[""featured""]"
```

Users should be able to:
- Filter by nested fields: `?metadata.color=red`
- Select nested fields: `?_fields=name,metadata.color,metadata.size`
- Search includes JSON content: `_search=red` matches inside JSON

---

## Tasks

### 5.1 JSON Detection in Importer (`app/services/importer.py`)
- [x] `detect_json_column(values: list[str]) -> bool`
  - Check if >50% of non-empty values parse as JSON objects/arrays (start with `{`/`[`)
  - Must be valid `json.loads()` parseable
- [x] During type inference: if `detect_json_column` is true, mark column as `"JSON"` in metadata
- [x] Storage: JSON data stored as TEXT in SQLite (SQLite JSON functions work on TEXT natively)
- [x] `columns_json` metadata example: `{"name": "TEXT", "metadata": "JSON", "tags": "JSON"}`

### 5.2 Dot-Notation in Query Builder (`app/services/query_builder.py`)

**Filtering:**
- [x] When a filter column contains `.`: split on first `.` to get `base_column` and `json_path`
- [x] Validate `base_column` exists in schema AND is type `JSON`
- [x] Build: `json_extract(base_column, '$.json_path') = ?`
- [x] Supports nested paths: `metadata.coords.lat` → `json_extract(metadata, '$.coords.lat')`
- [x] Operators work on extracted values: `?metadata.size__gt=10` → `json_extract(metadata, '$.size') > CAST(? AS NUMERIC)`
- [x] JSON path sanitized via regex `^[a-zA-Z0-9_.]+$` to prevent injection

**Field selection:**
- [x] `_fields=name,metadata.color` → `SELECT name, json_extract(metadata, '$.color') AS "metadata.color"`

**Search:**
- [x] `_search` on JSON columns: use `col LIKE ?` on the raw TEXT (searches within serialized JSON)
- [x] `_q` on JSON columns: same LIKE on raw TEXT

**Sort:**
- [x] `_sort=metadata.size` → `ORDER BY json_extract(metadata, '$.size') ASC`

### 5.3 Schema Endpoint Update
- [x] Schema shows JSON columns with type `"JSON"` (no code changes needed — existing endpoint reads from metadata)

### 5.4 Tests
- [x] `tests/test_json_queries.py`
  - Create collection with JSON column fixture (small CSV with JSON fields)
  - Filter by nested field: `?metadata.color=red`
  - Nested numeric comparison: `?metadata.size__gt=10`
  - `_fields` with dot notation returns extracted values
  - `_search` matches content inside JSON strings
  - Deep nesting: `?metadata.coords.lat__gt=35`
  - Invalid base column → error
  - Dot notation on non-JSON column → error
  - Schema endpoint shows JSON type
  - Sort by nested field
  - `__in` with dot notation

### 5.5 Test Fixture
- [x] Added `json_csv` fixture in conftest.py with 3 rows, deep nesting (coords.lat/lon)

---

## Implementation Notes

- `_resolve_column()` helper centralizes dot-notation resolution for filters, sort, and field selection
- Numeric operators (`gt`, `lt`, `gte`, `lte`) on JSON-extracted values use `CAST(? AS NUMERIC)` to ensure correct SQLite type comparison (json_extract returns native types, but query params are strings)
- 29 new tests (8 unit for detect_json_column, 13 unit for query builder, 1 schema API, 7 integration)
- Total test count: 142 (up from 113 in Phase 4)

---

## Verify
```bash
# Upload CSV with JSON columns, then:
curl "http://localhost:8000/api/v1/collections/products?metadata.color=red" -H "X-API-Key: test"
curl "http://localhost:8000/api/v1/collections/products?metadata.size__gt=10&_fields=name,metadata.color" -H "X-API-Key: test"
curl "http://localhost:8000/api/v1/collections/products?_search=red" -H "X-API-Key: test"
pytest tests/test_json_queries.py -v
```
