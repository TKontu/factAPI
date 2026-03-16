import csv
import io
import json
import re
from typing import Any

import aiosqlite
import structlog

from app.errors import ConflictError, ValidationError

logger = structlog.stdlib.get_logger(__name__)

COLLECTION_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
COLUMN_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
RESERVED_NAMES = {"_collections_meta"}


def sanitize_column_name(raw: str) -> str:
    """Sanitize a raw CSV header into a valid column name.

    Args:
        raw: Raw column header string.

    Returns:
        Sanitized lowercase column name.

    Raises:
        ValidationError: If the result is empty or invalid.
    """
    name = raw.strip().lower()
    name = re.sub(r"[^a-z0-9]", "_", name)
    name = re.sub(r"_+", "_", name)
    name = name.strip("_")
    name = re.sub(r"^[0-9]+", "", name)
    name = name.strip("_")
    if not name or not COLUMN_NAME_RE.match(name):
        raise ValidationError(f"Cannot sanitize column name: '{raw}'")
    return name


def infer_column_type(values: list[str]) -> str:
    """Infer SQL column type from sample values.

    Args:
        values: List of string values from the CSV column.

    Returns:
        One of "INTEGER", "REAL", or "TEXT".
    """
    sample = [v for v in values if v.strip()][:100]
    if not sample:
        return "TEXT"

    all_int = True
    all_numeric = True
    for v in sample:
        try:
            int(v)
        except ValueError:
            all_int = False
            try:
                float(v)
            except ValueError:
                all_numeric = False
                break

    if all_int:
        return "INTEGER"
    if all_numeric:
        return "REAL"
    return "TEXT"


def detect_json_column(values: list[str]) -> bool:
    """Detect if a column contains JSON objects or arrays.

    Args:
        values: List of string values from the CSV column.

    Returns:
        True if more than 50% of non-empty values are valid JSON objects/arrays.
    """
    sample = [v for v in values if v.strip()][:100]
    if not sample:
        return False

    json_count = 0
    for v in sample:
        stripped = v.strip()
        if stripped.startswith(("{", "[")):
            try:
                json.loads(stripped)
                json_count += 1
            except (json.JSONDecodeError, ValueError):
                pass

    return json_count > len(sample) * 0.5


def validate_collection_name(name: str) -> None:
    """Validate a collection name against naming rules.

    Args:
        name: Collection name to validate.

    Raises:
        ValidationError: If the name is invalid or reserved.
    """
    if not COLLECTION_NAME_RE.match(name):
        raise ValidationError(
            f"Invalid collection name: '{name}'. "
            "Must match ^[a-z][a-z0-9_]{{0,63}}$"
        )
    if name in RESERVED_NAMES:
        raise ValidationError(f"Collection name '{name}' is reserved")


async def import_csv(
    db: aiosqlite.Connection,
    name: str,
    file_content: bytes,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Import a CSV file into a new SQLite table.

    Args:
        db: Database connection.
        name: Collection/table name.
        file_content: Raw CSV bytes (UTF-8).
        overwrite: If True, replace existing table.

    Returns:
        Metadata dict with name, columns, row_count, timestamps.

    Raises:
        ValidationError: If CSV is malformed or names are invalid.
        ConflictError: If table exists and overwrite is False.
    """
    validate_collection_name(name)

    text = file_content.decode("utf-8")
    reader = csv.reader(io.StringIO(text))

    try:
        raw_headers = next(reader)
    except StopIteration as err:
        raise ValidationError("CSV file is empty") from err

    columns = []
    seen: set[str] = set()
    for h in raw_headers:
        col = sanitize_column_name(h)
        if col in seen:
            raise ValidationError(f"Duplicate column name after sanitization: '{col}'")
        seen.add(col)
        columns.append(col)

    rows = list(reader)

    # Infer types per column
    col_types: dict[str, str] = {}
    for i, col in enumerate(columns):
        values = [row[i] for row in rows if i < len(row)]
        col_types[col] = (
            "JSON" if detect_json_column(values) else infer_column_type(values)
        )

    # Check if table exists
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    exists = await cursor.fetchone()

    if exists and not overwrite:
        raise ConflictError(f"Collection '{name}' already exists")

    if exists:
        await db.execute(f"DROP TABLE [{name}]")

    # Create table
    col_defs = ", ".join(f"[{col}] {col_types[col]}" for col in columns)
    create_sql = (
        f"CREATE TABLE [{name}] (_id INTEGER PRIMARY KEY AUTOINCREMENT, {col_defs})"
    )
    await db.execute(create_sql)

    # Batch insert rows
    if rows:
        placeholders = ", ".join("?" for _ in columns)
        insert_sql = f"INSERT INTO [{name}] ({', '.join(f'[{c}]' for c in columns)}) VALUES ({placeholders})"
        batch_size = 1000
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            # Pad or trim rows to match column count
            normalized = []
            for row in batch:
                if len(row) < len(columns):
                    row = row + [""] * (len(columns) - len(row))
                elif len(row) > len(columns):
                    row = row[: len(columns)]
                normalized.append(row)
            await db.executemany(insert_sql, normalized)

    # Upsert metadata
    columns_json = json.dumps(col_types)
    await db.execute(
        """
        INSERT INTO _collections_meta (name, row_count, columns_json, created_at, updated_at)
        VALUES (?, ?, ?, datetime('now'), datetime('now'))
        ON CONFLICT(name) DO UPDATE SET
            row_count = excluded.row_count,
            columns_json = excluded.columns_json,
            updated_at = datetime('now')
        """,
        (name, len(rows), columns_json),
    )
    await db.commit()

    # Fetch back the metadata
    cursor = await db.execute(
        "SELECT created_at, updated_at FROM _collections_meta WHERE name = ?",
        (name,),
    )
    meta_row = await cursor.fetchone()

    logger.info("csv_imported", collection=name, row_count=len(rows))

    return {
        "name": name,
        "columns": col_types,
        "row_count": len(rows),
        "created_at": meta_row[0],
        "updated_at": meta_row[1],
    }


async def append_csv(
    db: aiosqlite.Connection,
    name: str,
    file_content: bytes,
) -> dict[str, Any]:
    """Append rows from a CSV file to an existing collection.

    Args:
        db: Database connection.
        name: Collection/table name.
        file_content: Raw CSV bytes (UTF-8).

    Returns:
        Updated metadata dict.

    Raises:
        NotFoundError: If collection does not exist.
        ValidationError: If CSV headers don't match existing columns.
    """
    from app.services.collection_manager import get_collection_or_404, update_row_count

    meta = await get_collection_or_404(db, name)
    existing_columns = meta["columns"]

    text = file_content.decode("utf-8")
    reader = csv.reader(io.StringIO(text))

    try:
        raw_headers = next(reader)
    except StopIteration as err:
        raise ValidationError("CSV file is empty") from err

    headers = [sanitize_column_name(h) for h in raw_headers]
    expected = list(existing_columns.keys())
    if headers != expected:
        raise ValidationError(
            f"CSV headers {headers} do not match existing columns {expected}"
        )

    rows = list(reader)

    if rows:
        columns = headers
        placeholders = ", ".join("?" for _ in columns)
        insert_sql = f"INSERT INTO [{name}] ({', '.join(f'[{c}]' for c in columns)}) VALUES ({placeholders})"
        batch_size = 1000
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            normalized = []
            for row in batch:
                if len(row) < len(columns):
                    row = row + [""] * (len(columns) - len(row))
                elif len(row) > len(columns):
                    row = row[: len(columns)]
                normalized.append(row)
            await db.executemany(insert_sql, normalized)

    await db.commit()
    await update_row_count(db, name)

    # Fetch updated metadata
    cursor = await db.execute(
        "SELECT row_count, created_at, updated_at FROM _collections_meta WHERE name = ?",
        (name,),
    )
    meta_row = await cursor.fetchone()

    logger.info("csv_appended", collection=name, rows_added=len(rows))

    return {
        "name": name,
        "columns": existing_columns,
        "row_count": meta_row[0],
        "created_at": meta_row[1],
        "updated_at": meta_row[2],
    }
