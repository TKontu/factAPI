from pathlib import Path

import aiosqlite


async def init_db(db_path: str) -> aiosqlite.Connection:
    """Open a database connection with WAL mode and foreign keys enabled."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(db_path)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def close_db(db: aiosqlite.Connection) -> None:
    """Close the database connection."""
    await db.close()


async def execute_query(
    db: aiosqlite.Connection,
    sql: str,
    params: tuple[object, ...] = (),
) -> list[dict[str, object]]:
    """Execute a SELECT query and return results as a list of dicts."""
    cursor = await db.execute(sql, params)
    columns = [desc[0] for desc in cursor.description or []]
    rows = await cursor.fetchall()
    return [dict(zip(columns, row, strict=True)) for row in rows]


async def execute_write(
    db: aiosqlite.Connection,
    sql: str,
    params: tuple[object, ...] = (),
) -> int:
    """Execute an INSERT/UPDATE/DELETE, commit, and return rowcount."""
    cursor = await db.execute(sql, params)
    await db.commit()
    return cursor.rowcount


async def init_metadata_table(db: aiosqlite.Connection) -> None:
    """Create the _collections_meta table if it doesn't exist."""
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS _collections_meta (
            name TEXT PRIMARY KEY,
            row_count INTEGER NOT NULL DEFAULT 0,
            columns_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    await db.commit()
