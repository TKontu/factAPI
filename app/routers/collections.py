import time

import structlog
from fastapi import APIRouter, Depends, Request

from app.auth import require_api_key
from app.config import Settings, get_settings
from app.database import execute_query
from app.errors import NotFoundError, ValidationError
from app.models.schemas import (
    CollectionListResponse,
    CollectionResponse,
    CollectionSchema,
)
from app.services.collection_manager import get_collection_or_404, list_collections
from app.services.query_builder import build_query

logger = structlog.stdlib.get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["collections"])


@router.get("/collections", response_model=CollectionListResponse)
async def list_all_collections(
    request: Request,
    _key: str = Depends(require_api_key),
) -> CollectionListResponse:
    """List all available collections."""
    db = request.app.state.db
    collections = await list_collections(db)
    return CollectionListResponse(collections=collections)


@router.get("/collections/{name}/schema", response_model=CollectionSchema)
async def get_collection_schema(
    name: str,
    request: Request,
    _key: str = Depends(require_api_key),
) -> CollectionSchema:
    """Get the schema of a collection."""
    db = request.app.state.db
    meta = await get_collection_or_404(db, name)
    return CollectionSchema(name=meta["name"], columns=meta["columns"])


@router.get("/collections/{name}", response_model=CollectionResponse)
async def query_collection(
    name: str,
    request: Request,
    _key: str = Depends(require_api_key),
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> CollectionResponse:
    """Query a collection with filters, sorting, and pagination."""
    db = request.app.state.db
    meta = await get_collection_or_404(db, name)

    query_params = dict(request.query_params)
    result = build_query(
        name, meta["columns"], query_params, settings.default_limit, settings.max_limit
    )

    if result.errors:
        raise ValidationError("; ".join(result.errors))

    query_start = time.perf_counter()

    count_rows = await execute_query(
        db, result.count_sql, tuple(result.count_parameters)
    )
    total = count_rows[0]["total"]

    rows = await execute_query(db, result.select_sql, tuple(result.parameters))

    duration_ms = round((time.perf_counter() - query_start) * 1000, 2)
    logger.debug(
        "query_executed",
        collection=name,
        total=total,
        count=len(rows),
        duration_ms=duration_ms,
    )

    # Parse limit/offset from the last two parameters
    offset = result.parameters[-1]
    limit = result.parameters[-2]

    return CollectionResponse(
        collection=name,
        total=total,
        count=len(rows),
        limit=limit,
        offset=offset,
        data=rows,
    )


@router.get("/collections/{name}/{record_id}", response_model=dict[str, object])
async def get_record(
    name: str,
    record_id: int,
    request: Request,
    _key: str = Depends(require_api_key),
) -> dict[str, object]:
    """Get a single record by ID."""
    db = request.app.state.db
    await get_collection_or_404(db, name)
    rows = await execute_query(
        db, f"SELECT * FROM [{name}] WHERE _id = ?", (record_id,)
    )
    if not rows:
        raise NotFoundError(f"Record {record_id} not found in '{name}'")
    return rows[0]
