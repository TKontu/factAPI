# factAPI

Turn any CSV file into a queryable REST API in seconds. Upload a CSV, get a full-featured API with filtering, sorting, pagination, full-text search, and JSON field support — backed by SQLite.

## Features

- **CSV to API** — Upload any CSV and immediately query it via REST
- **Type inference** — Automatically detects INTEGER, REAL, TEXT, and JSON columns
- **Rich querying** — Filter, sort, paginate, search, and select fields
- **JSON support** — Query nested JSON fields with dot notation
- **MCP server** — Expose collections as tools for AI assistants
- **Structured logging** — JSON logs in production, colored console in development
- **Docker ready** — Single-command deployment with persistent storage

## Docker Quickstart

```bash
cp .env.example .env
# Edit .env with your API keys

docker compose up -d --build
curl http://localhost:8484/health
```

Upload a CSV:

```bash
curl -X POST http://localhost:8484/api/v1/admin/collections \
  -H "X-Admin-Key: your-admin-api-key" \
  -F "name=cities" -F "file=@data/worldcities.csv"
```

Query it:

```bash
curl "http://localhost:8484/api/v1/collections/cities?country=Japan&_limit=5" \
  -H "X-API-Key: your-read-api-key"
```

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

cp .env.example .env
uvicorn app.main:app --reload
```

Run tests:

```bash
pytest tests/ -v
```

## API Reference

### Health Check

```bash
curl http://localhost:8000/health
```

### Admin Endpoints

All admin endpoints require the `X-Admin-Key` header.

**Create collection:**

```bash
curl -X POST http://localhost:8000/api/v1/admin/collections \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -F "name=products" -F "file=@products.csv"
```

**Replace collection:**

```bash
curl -X PUT http://localhost:8000/api/v1/admin/collections/products \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -F "file=@products_v2.csv"
```

**Append to collection:**

```bash
curl -X POST http://localhost:8000/api/v1/admin/collections/products/append \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -F "file=@more_products.csv"
```

**Delete collection:**

```bash
curl -X DELETE http://localhost:8000/api/v1/admin/collections/products \
  -H "X-Admin-Key: $ADMIN_KEY"
```

### Query Endpoints

All query endpoints require the `X-API-Key` header (if configured).

**List collections:**

```bash
curl http://localhost:8000/api/v1/collections \
  -H "X-API-Key: $API_KEY"
```

**Get collection schema:**

```bash
curl http://localhost:8000/api/v1/collections/products/schema \
  -H "X-API-Key: $API_KEY"
```

**Query collection:**

```bash
curl "http://localhost:8000/api/v1/collections/products?category=electronics&_sort=-price&_limit=10" \
  -H "X-API-Key: $API_KEY"
```

**Get single record:**

```bash
curl http://localhost:8000/api/v1/collections/products/42 \
  -H "X-API-Key: $API_KEY"
```

## Query Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `column=value` | Exact match filter | `country=Japan` |
| `column__gt` | Greater than | `price__gt=100` |
| `column__gte` | Greater than or equal | `age__gte=18` |
| `column__lt` | Less than | `score__lt=50` |
| `column__lte` | Less than or equal | `rating__lte=3` |
| `column__like` | Pattern match (% wildcard) | `name__like=%smith%` |
| `column__in` | Match any in comma-separated list | `status__in=active,pending` |
| `json_col.path` | JSON field access (dot notation) | `metadata.color=red` |
| `_sort` | Sort by field (prefix `-` for desc) | `_sort=-created_at` |
| `_limit` | Max rows to return | `_limit=25` |
| `_offset` | Skip N rows | `_offset=50` |
| `_fields` | Comma-separated fields to return | `_fields=name,price` |
| `_search` | Full-text search across all columns | `_search=tokyo` |

## MCP Server

factAPI includes an MCP (Model Context Protocol) server for AI assistant integration.

```json
{
  "mcpServers": {
    "factapi": {
      "command": "python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "/path/to/factAPI"
    }
  }
}
```

Available tools: `list_collections`, `get_schema`, `query_collection`, `search_collection`, `get_record`.

## Configuration

All settings use the `FACTAPI_` prefix and can be set via environment variables or `.env` file.

| Variable | Description | Default |
|----------|-------------|---------|
| `FACTAPI_ENV` | Environment (`development` / `production`) | `development` |
| `FACTAPI_DB_PATH` | Path to SQLite database file | `data/factapi.db` |
| `FACTAPI_API_KEY` | API key for read endpoints (empty = no auth) | `` |
| `FACTAPI_ADMIN_KEY` | API key for admin endpoints (empty = no auth) | `` |
| `FACTAPI_DEFAULT_LIMIT` | Default query result limit | `100` |
| `FACTAPI_MAX_LIMIT` | Maximum allowed query limit | `1000` |
| `FACTAPI_CORS_ORIGINS` | Comma-separated CORS origins | `*` |
| `FACTAPI_LOG_LEVEL` | Log level (debug/info/warning/error) | `info` |

## Example Datasets

Any CSV works. Some ideas:

- World cities with coordinates and population
- Product catalogs with prices and categories
- Historical events with dates and descriptions
- Sports statistics with player/team data

Place CSV files in the `data/` directory and upload via the admin API.
