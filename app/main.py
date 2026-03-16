from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import close_db, init_db, init_metadata_table
from app.errors import FactAPIError
from app.logging import setup_logging
from app.middleware import RequestMiddleware
from app.models.schemas import HealthResponse
from app.routers.admin import router as admin_router
from app.routers.collections import router as collections_router

logger = structlog.stdlib.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    setup_logging(settings)
    logger.info("startup", env=settings.env, db_path=settings.db_path)
    db = await init_db(settings.db_path)
    await init_metadata_table(db)
    app.state.db = db
    yield
    logger.info("shutdown")
    await close_db(db)


API_DESCRIPTION = """\
Turn any CSV into a queryable REST API. Upload a CSV file, get a full-featured
API with filtering, sorting, pagination, full-text search, and JSON field support.

## Authentication

- **Read endpoints** require the `X-API-Key` header (skip if `FACTAPI_API_KEY` is unset).
- **Admin endpoints** require the `X-Admin-Key` header (skip if `FACTAPI_ADMIN_KEY` is unset).

## Query Parameters

| Parameter | Example | Description |
|-----------|---------|-------------|
| `column=value` | `country=Japan` | Exact match |
| `column__gt` | `price__gt=100` | Greater than |
| `column__gte` / `__lt` / `__lte` | `age__gte=18` | Comparison operators |
| `column__like` | `name__like=%smith%` | Pattern match |
| `column__in` | `status__in=a,b` | Match any in list |
| `json_col.path` | `metadata.color=red` | JSON dot-notation |
| `_sort` | `_sort=-population` | Sort (prefix `-` = DESC) |
| `_limit` / `_offset` | `_limit=25&_offset=50` | Pagination |
| `_fields` | `_fields=name,price` | Select columns |
| `_search` | `_search=tokyo` | Full-text search |
"""

app = FastAPI(
    title="factAPI",
    version="0.1.0",
    description=API_DESCRIPTION,
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(RequestMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)
app.include_router(collections_router)


@app.exception_handler(FactAPIError)
async def factapi_error_handler(request: Request, exc: FactAPIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    """Check if the API is running."""
    return HealthResponse(status="healthy", version="0.1.0")
