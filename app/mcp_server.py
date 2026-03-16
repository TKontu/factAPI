"""MCP server exposing factAPI collections as tools for AI assistants."""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import aiosqlite
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from app.config import get_settings
from app.database import execute_query
from app.errors import NotFoundError
from app.services.collection_manager import get_collection_or_404, list_collections
from app.services.query_builder import build_query


@dataclass
class AppContext:
    db: aiosqlite.Connection


@asynccontextmanager
async def lifespan(server: FastMCP):  # noqa: ANN201
    settings = get_settings()
    db = await aiosqlite.connect(f"file:{settings.db_path}?mode=ro", uri=True)
    await db.execute("PRAGMA journal_mode=WAL")
    server._db = db  # type: ignore[attr-defined]
    try:
        yield AppContext(db=db)
    finally:
        await db.close()


mcp = FastMCP(
    name="factapi",
    instructions=(
        "Query factAPI collections. Use list_collections to discover available "
        "data, get_schema to understand columns, and query_collection or "
        "search_collection to retrieve data."
    ),
    lifespan=lifespan,
)


def _get_db(ctx: Context) -> aiosqlite.Connection:
    return ctx.request_context.lifespan_context.db


# --- Standalone async helpers (testable without MCP context) ---


async def _list_collections(db: aiosqlite.Connection) -> list[dict[str, Any]]:
    return await list_collections(db)


async def _get_schema(db: aiosqlite.Connection, collection: str) -> dict[str, Any]:
    try:
        meta = await get_collection_or_404(db, collection)
    except NotFoundError as e:
        raise ToolError(str(e)) from e
    return {"name": meta["name"], "columns": meta["columns"]}


async def _query_collection(
    db: aiosqlite.Connection,
    collection: str,
    filters: dict[str, str] | None = None,
    sort: str | None = None,
    limit: int = 100,
    offset: int = 0,
    fields: str | None = None,
) -> dict[str, Any]:
    try:
        meta = await get_collection_or_404(db, collection)
    except NotFoundError as e:
        raise ToolError(str(e)) from e

    params: dict[str, str] = {}
    if filters:
        params.update(filters)
    if sort is not None:
        params["_sort"] = sort
    params["_limit"] = str(limit)
    params["_offset"] = str(offset)
    if fields is not None:
        params["_fields"] = fields

    qr = build_query(meta["name"], meta["columns"], params)
    if qr.errors:
        raise ToolError("; ".join(qr.errors))

    count_rows = await execute_query(db, qr.count_sql, tuple(qr.count_parameters))
    total = count_rows[0]["total"] if count_rows else 0
    data = await execute_query(db, qr.select_sql, tuple(qr.parameters))
    return {"total": total, "count": len(data), "data": data}


async def _search_collection(
    db: aiosqlite.Connection,
    collection: str,
    search_term: str,
    limit: int = 100,
) -> dict[str, Any]:
    try:
        meta = await get_collection_or_404(db, collection)
    except NotFoundError as e:
        raise ToolError(str(e)) from e

    params = {"_search": search_term, "_limit": str(limit)}
    qr = build_query(meta["name"], meta["columns"], params)
    if qr.errors:
        raise ToolError("; ".join(qr.errors))

    count_rows = await execute_query(db, qr.count_sql, tuple(qr.count_parameters))
    total = count_rows[0]["total"] if count_rows else 0
    data = await execute_query(db, qr.select_sql, tuple(qr.parameters))
    return {"total": total, "count": len(data), "data": data}


async def _get_record(
    db: aiosqlite.Connection,
    collection: str,
    record_id: int,
) -> dict[str, Any]:
    try:
        meta = await get_collection_or_404(db, collection)
    except NotFoundError as e:
        raise ToolError(str(e)) from e

    rows = await execute_query(
        db,
        f"SELECT * FROM [{meta['name']}] WHERE _id = ?",
        (record_id,),
    )
    if not rows:
        raise ToolError(f"Record {record_id} not found in '{collection}'")
    return rows[0]


# --- MCP tool registrations (thin wrappers) ---


@mcp.tool()
async def list_collections_tool(ctx: Context) -> list[dict[str, Any]]:
    """List all available collections with their metadata."""
    return await _list_collections(_get_db(ctx))


@mcp.tool()
async def get_schema(ctx: Context, collection: str) -> dict[str, Any]:
    """Get the schema (column names and types) for a collection."""
    return await _get_schema(_get_db(ctx), collection)


@mcp.tool()
async def query_collection(
    ctx: Context,
    collection: str,
    filters: dict[str, str] | None = None,
    sort: str | None = None,
    limit: int = 100,
    offset: int = 0,
    fields: str | None = None,
) -> dict[str, Any]:
    """Query a collection with optional filters, sorting, pagination, and field selection.

    Args:
        collection: Name of the collection to query.
        filters: Column filters as key-value pairs. Use column__op for operators
            (gt, lt, gte, lte, like, in). Use dot notation for JSON fields.
        sort: Sort field. Prefix with - for descending.
        limit: Max rows to return (default 100).
        offset: Number of rows to skip.
        fields: Comma-separated list of fields to return.
    """
    return await _query_collection(
        _get_db(ctx), collection, filters, sort, limit, offset, fields
    )


@mcp.tool()
async def search_collection(
    ctx: Context,
    collection: str,
    search_term: str,
    limit: int = 100,
) -> dict[str, Any]:
    """Search across all columns of a collection for a term.

    Args:
        collection: Name of the collection to search.
        search_term: Text to search for across all columns.
        limit: Max rows to return (default 100).
    """
    return await _search_collection(_get_db(ctx), collection, search_term, limit)


@mcp.tool()
async def get_record(
    ctx: Context,
    collection: str,
    record_id: int,
) -> dict[str, Any]:
    """Get a single record by its ID.

    Args:
        collection: Name of the collection.
        record_id: The _id of the record to retrieve.
    """
    return await _get_record(_get_db(ctx), collection, record_id)


# --- MCP resources ---


@mcp.resource("factapi://collections")
async def collections_resource() -> list[dict[str, Any]]:
    """List of all available collections."""
    return await _list_collections(mcp._db)  # type: ignore[attr-defined]


@mcp.resource("factapi://collections/{name}/schema")
async def collection_schema_resource(name: str, ctx: Context) -> dict[str, Any]:
    """Schema for a specific collection."""
    return await _get_schema(_get_db(ctx), name)


if __name__ == "__main__":
    mcp.run(transport="stdio")
