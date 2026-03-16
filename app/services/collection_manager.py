import json
from typing import Any

import aiosqlite

from app.database import execute_query, execute_write
from app.errors import NotFoundError


async def list_collections(db: aiosqlite.Connection) -> list[dict[str, Any]]:
    """List all collections with their metadata."""
    rows = await execute_query(
        db,
        "SELECT name, row_count, columns_json, created_at, updated_at "
        "FROM _collections_meta ORDER BY name",
    )
    for row in rows:
        row["columns"] = json.loads(str(row["columns_json"]))
        del row["columns_json"]
    return rows


async def get_collection(db: aiosqlite.Connection, name: str) -> dict[str, Any] | None:
    """Get metadata for a single collection."""
    rows = await execute_query(
        db,
        "SELECT name, row_count, columns_json, created_at, updated_at "
        "FROM _collections_meta WHERE name = ?",
        (name,),
    )
    if not rows:
        return None
    row = rows[0]
    row["columns"] = json.loads(str(row["columns_json"]))
    del row["columns_json"]
    return row


async def get_collection_or_404(db: aiosqlite.Connection, name: str) -> dict[str, Any]:
    """Get collection metadata or raise NotFoundError."""
    collection = await get_collection(db, name)
    if collection is None:
        raise NotFoundError(f"Collection '{name}' not found")
    return collection


async def delete_collection(db: aiosqlite.Connection, name: str) -> None:
    """Delete a collection table and its metadata."""
    await get_collection_or_404(db, name)
    await db.execute(f"DROP TABLE IF EXISTS [{name}]")
    await execute_write(
        db,
        "DELETE FROM _collections_meta WHERE name = ?",
        (name,),
    )


async def update_row_count(db: aiosqlite.Connection, name: str) -> None:
    """Update the row_count in metadata from the actual table."""
    rows = await execute_query(db, f"SELECT COUNT(*) as cnt FROM [{name}]")
    count = rows[0]["cnt"]
    await execute_write(
        db,
        "UPDATE _collections_meta SET row_count = ?, updated_at = datetime('now') "
        "WHERE name = ?",
        (count, name),
    )
