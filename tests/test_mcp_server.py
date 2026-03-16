"""Tests for MCP server tool functions."""

import tempfile

import aiosqlite
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from app.database import init_metadata_table
from app.mcp_server import (
    _get_record,
    _get_schema,
    _list_collections,
    _query_collection,
    _search_collection,
)
from app.services.importer import import_csv


@pytest.fixture
async def mcp_db():
    """Create a temp DB with two test collections: people and products."""
    tmp = tempfile.mktemp(suffix=".db")
    db = await aiosqlite.connect(tmp)
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    await init_metadata_table(db)

    sample_csv = b"name,age,score\nAlice,30,95.5\nBob,25,87.0\nCharlie,35,92.3\nDiana,28,88.1\nEve,32,91.7"
    await import_csv(db, "people", sample_csv)

    json_csv = (
        b"name,metadata,tags\n"
        b'Widget A,"{""color"":""red"",""size"":10,""coords"":{""lat"":40.7,""lon"":-74.0}}","[""sale"",""new""]"\n'
        b'Widget B,"{""color"":""blue"",""size"":25,""coords"":{""lat"":34.0,""lon"":-118.2}}","[""featured""]"\n'
        b'Widget C,"{""color"":""red"",""size"":5,""coords"":{""lat"":51.5,""lon"":-0.1}}","[""sale""]"'
    )
    await import_csv(db, "products", json_csv)

    yield db
    await db.close()


class TestMcpListCollections:
    async def test_returns_both_collections(self, mcp_db: aiosqlite.Connection) -> None:
        result = await _list_collections(mcp_db)
        names = [c["name"] for c in result]
        assert "people" in names
        assert "products" in names
        assert len(result) == 2

    async def test_includes_metadata(self, mcp_db: aiosqlite.Connection) -> None:
        result = await _list_collections(mcp_db)
        people = next(c for c in result if c["name"] == "people")
        assert people["row_count"] == 5
        assert "columns" in people
        assert "name" in people["columns"]


class TestMcpGetSchema:
    async def test_returns_columns_for_people(
        self, mcp_db: aiosqlite.Connection
    ) -> None:
        result = await _get_schema(mcp_db, "people")
        assert result["name"] == "people"
        assert "name" in result["columns"]
        assert "age" in result["columns"]
        assert "score" in result["columns"]

    async def test_returns_json_types_for_products(
        self, mcp_db: aiosqlite.Connection
    ) -> None:
        result = await _get_schema(mcp_db, "products")
        assert result["columns"]["metadata"] == "JSON"
        assert result["columns"]["tags"] == "JSON"

    async def test_unknown_collection_raises_error(
        self, mcp_db: aiosqlite.Connection
    ) -> None:
        with pytest.raises(ToolError, match="not found"):
            await _get_schema(mcp_db, "nonexistent")


class TestMcpQueryCollection:
    async def test_no_filters_returns_all(self, mcp_db: aiosqlite.Connection) -> None:
        result = await _query_collection(mcp_db, "people")
        assert result["total"] == 5
        assert result["count"] == 5
        assert len(result["data"]) == 5

    async def test_with_filter(self, mcp_db: aiosqlite.Connection) -> None:
        result = await _query_collection(mcp_db, "people", filters={"name": "Alice"})
        assert result["total"] == 1
        assert result["data"][0]["name"] == "Alice"

    async def test_with_sort_limit_offset(self, mcp_db: aiosqlite.Connection) -> None:
        result = await _query_collection(
            mcp_db, "people", sort="age", limit=2, offset=1
        )
        assert result["count"] == 2
        # sorted by age ascending: Bob(25), Diana(28), Alice(30), Eve(32), Charlie(35)
        # offset 1 → Diana, Alice
        assert result["data"][0]["name"] == "Diana"
        assert result["data"][1]["name"] == "Alice"

    async def test_with_fields(self, mcp_db: aiosqlite.Connection) -> None:
        result = await _query_collection(mcp_db, "people", fields="name,age")
        row = result["data"][0]
        assert "name" in row
        assert "age" in row
        assert "score" not in row

    async def test_json_dot_notation_filter(self, mcp_db: aiosqlite.Connection) -> None:
        result = await _query_collection(
            mcp_db, "products", filters={"metadata.color": "red"}
        )
        assert result["total"] == 2
        names = [r["name"] for r in result["data"]]
        assert "Widget A" in names
        assert "Widget C" in names

    async def test_invalid_column_raises_error(
        self, mcp_db: aiosqlite.Connection
    ) -> None:
        with pytest.raises(ToolError, match="Unknown"):
            await _query_collection(mcp_db, "people", filters={"nonexistent": "val"})

    async def test_unknown_collection_raises_error(
        self, mcp_db: aiosqlite.Connection
    ) -> None:
        with pytest.raises(ToolError, match="not found"):
            await _query_collection(mcp_db, "nonexistent")


class TestMcpSearchCollection:
    async def test_finds_matching_rows(self, mcp_db: aiosqlite.Connection) -> None:
        result = await _search_collection(mcp_db, "people", "Alice")
        assert result["total"] >= 1
        assert any(r["name"] == "Alice" for r in result["data"])

    async def test_no_matches_returns_empty(self, mcp_db: aiosqlite.Connection) -> None:
        result = await _search_collection(mcp_db, "people", "zzzznotfound")
        assert result["total"] == 0
        assert result["data"] == []


class TestMcpGetRecord:
    async def test_returns_correct_record(self, mcp_db: aiosqlite.Connection) -> None:
        result = await _get_record(mcp_db, "people", 1)
        assert result["_id"] == 1
        assert result["name"] == "Alice"

    async def test_missing_id_raises_error(self, mcp_db: aiosqlite.Connection) -> None:
        with pytest.raises(ToolError, match="not found"):
            await _get_record(mcp_db, "people", 9999)

    async def test_unknown_collection_raises_error(
        self, mcp_db: aiosqlite.Connection
    ) -> None:
        with pytest.raises(ToolError, match="not found"):
            await _get_record(mcp_db, "nonexistent", 1)
