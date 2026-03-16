# Phase 3: Query Builder & GET Endpoint ✅ COMPLETE

## Goal
The core value — filter, sort, paginate, select fields on any collection. The query builder is the most important module.

---

## Tasks

### 3.1 Query Builder (`app/services/query_builder.py`) — Pure function module, no DB/FastAPI deps

- [x] Define `QueryResult` dataclass: `select_sql`, `count_sql`, `parameters` (list), `errors` (list[str])
- [x] Implement `build_query(table, columns, params, default_limit, max_limit) -> QueryResult`

**Parsing flow:**
- [x] Separate meta-params (`_sort`, `_limit`, `_offset`, `_fields`, `_q`) from filter params
- [x] `_fields` → validate each against `columns` dict, build SELECT clause (default: all + `_id`)
- [x] Filter params → parse `column__operator` pattern:
  - No operator suffix → exact match `=`
  - Known operator → map to SQL: `gt: >`, `lt: <`, `gte: >=`, `lte: <=`, `like: LIKE`, `in: IN`
- [x] Validate every filter column exists in `columns` dict (whitelist = SQL injection defense)
- [x] Build WHERE clause with `?` placeholders (never string interpolation for values)
- [x] `__in` operator: split value on commas, generate `IN (?, ?, ?)` with correct placeholder count
- [x] `_q` → `WHERE (col1 LIKE ? OR col2 LIKE ? ...)` for TEXT columns only, `%term%` binding
- [x] `_sort` → validate column exists, `ORDER BY col ASC` or `DESC` (prefix `-` = DESC)
- [x] Clamp `_limit` to `[1, max_limit]`, `_offset` to `>= 0`
- [x] Generate count query: same WHERE clause, no LIMIT/OFFSET/ORDER BY
- [x] Return `QueryResult` with both queries + parameters + any validation errors

### 3.2 Schemas additions (`app/models/schemas.py`)
- [x] `CollectionResponse(BaseModel)`: collection, total, count, limit, offset, data (list[dict[str, Any]])

### 3.3 Collections Router addition (`app/routers/collections.py`)
- [x] `GET /api/v1/collections/{name}` — main query endpoint
  1. Resolve collection via `get_collection_or_404`
  2. Extract all query params from `request.query_params`
  3. Call `build_query(name, meta.columns, params, settings)`
  4. If `query_result.errors` → return 422 with details
  5. Execute `count_sql` and `select_sql`
  6. Return `CollectionResponse`

### 3.4 Tests — Most important test file

- [x] `tests/test_query_builder.py`
  - No filters → `SELECT * ... LIMIT 100 OFFSET 0`
  - Exact match filter
  - Each operator: `__gt`, `__lt`, `__gte`, `__lte`, `__like`, `__in`
  - `_sort` ascending and descending
  - `_limit` clamping (0→1, 9999→max_limit)
  - `_offset` negative → 0
  - `_fields` with valid and invalid column names
  - `_q` generates OR clause for TEXT columns only
  - Unknown column in filter → error
  - SQL injection attempt in column name → rejected
  - `__in` with multiple values → correct placeholder count
  - Combined multiple filters
- [x] `tests/test_collections_api.py`
  - GET with filters returns correct data
  - GET nonexistent collection → 404
  - Pagination (limit/offset) returns correct subset
  - Sort order correct

---

## Verify
```bash
curl "http://localhost:8000/api/v1/collections/cities?country=Japan&_sort=-population&_limit=5" \
  -H "X-API-Key: test"
curl "http://localhost:8000/api/v1/collections/cities?population__gt=1000000&_fields=city,country,population" \
  -H "X-API-Key: test"
curl "http://localhost:8000/api/v1/collections/cities?_q=tokyo" -H "X-API-Key: test"
pytest tests/test_query_builder.py tests/test_collections_api.py -v
```
