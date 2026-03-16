import io

import pytest

from app.services.importer import detect_json_column
from app.services.query_builder import build_query


class TestDetectJsonColumn:
    def test_all_objects(self) -> None:
        values = ['{"a":1}', '{"b":2}', '{"c":3}']
        assert detect_json_column(values) is True

    def test_all_arrays(self) -> None:
        values = ['["a","b"]', '["c"]', "[1,2,3]"]
        assert detect_json_column(values) is True

    def test_mixed_above_threshold(self) -> None:
        values = ['{"a":1}', '{"b":2}', "plain text"]
        assert detect_json_column(values) is True

    def test_below_threshold(self) -> None:
        values = ['{"a":1}', "plain text", "another text", "more text"]
        assert detect_json_column(values) is False

    def test_empty_values(self) -> None:
        values: list[str] = []
        assert detect_json_column(values) is False

    def test_all_empty_strings(self) -> None:
        values = ["", "  ", ""]
        assert detect_json_column(values) is False

    def test_invalid_json(self) -> None:
        values = ["{bad json", "[not valid", "{{}}"]
        assert detect_json_column(values) is False

    def test_strings_starting_with_brace_but_invalid(self) -> None:
        values = ["{not json}", "{also bad}", "plain"]
        assert detect_json_column(values) is False


class TestJsonQueryBuilder:
    COLUMNS = {"name": "TEXT", "metadata": "JSON", "tags": "JSON"}

    def test_dot_notation_exact_match(self) -> None:
        result = build_query("t", self.COLUMNS, {"metadata.color": "red"})
        assert result.errors == []
        assert "json_extract([metadata], '$.color') = ?" in result.select_sql
        assert "red" in result.parameters

    def test_dot_notation_with_operator(self) -> None:
        result = build_query("t", self.COLUMNS, {"metadata.size__gt": "10"})
        assert result.errors == []
        assert (
            "json_extract([metadata], '$.size') > CAST(? AS NUMERIC)"
            in result.select_sql
        )

    def test_deep_nesting(self) -> None:
        result = build_query("t", self.COLUMNS, {"metadata.coords.lat__gt": "35"})
        assert result.errors == []
        assert (
            "json_extract([metadata], '$.coords.lat') > CAST(? AS NUMERIC)"
            in result.select_sql
        )

    def test_fields_with_dot_notation(self) -> None:
        result = build_query("t", self.COLUMNS, {"_fields": "name,metadata.color"})
        assert result.errors == []
        assert "[name]" in result.select_sql
        assert (
            "json_extract([metadata], '$.color') AS \"metadata.color\""
            in result.select_sql
        )

    def test_dot_on_non_json_column_error(self) -> None:
        result = build_query("t", self.COLUMNS, {"name.foo": "bar"})
        assert len(result.errors) == 1
        assert "not a JSON column" in result.errors[0]

    def test_unknown_base_column_error(self) -> None:
        result = build_query("t", self.COLUMNS, {"unknown.foo": "bar"})
        assert len(result.errors) == 1
        assert "Unknown filter column" in result.errors[0]

    def test_q_includes_json_columns(self) -> None:
        result = build_query("t", self.COLUMNS, {"_q": "red"})
        assert result.errors == []
        # Should search name, metadata, and tags (all TEXT/JSON)
        assert result.select_sql.count("LIKE ?") == 3

    def test_search_includes_json_columns(self) -> None:
        result = build_query("t", self.COLUMNS, {"_search": "red"})
        assert result.errors == []
        assert result.select_sql.count("LIKE ?") == 3

    def test_in_with_dot_notation(self) -> None:
        result = build_query("t", self.COLUMNS, {"metadata.color__in": "red,blue"})
        assert result.errors == []
        assert "json_extract([metadata], '$.color') IN (?, ?)" in result.select_sql

    def test_sort_with_dot_notation(self) -> None:
        result = build_query("t", self.COLUMNS, {"_sort": "metadata.size"})
        assert result.errors == []
        assert "ORDER BY json_extract([metadata], '$.size') ASC" in result.select_sql

    def test_sort_desc_with_dot_notation(self) -> None:
        result = build_query("t", self.COLUMNS, {"_sort": "-metadata.size"})
        assert result.errors == []
        assert "ORDER BY json_extract([metadata], '$.size') DESC" in result.select_sql

    def test_fields_dot_on_non_json_error(self) -> None:
        result = build_query("t", self.COLUMNS, {"_fields": "name.foo"})
        assert len(result.errors) == 1
        assert "not a JSON column" in result.errors[0]

    def test_fields_unknown_base_error(self) -> None:
        result = build_query("t", self.COLUMNS, {"_fields": "unknown.foo"})
        assert len(result.errors) == 1
        assert "Unknown field" in result.errors[0]


class TestJsonSchemaAPI:
    async def test_schema_shows_json_type(
        self,
        admin_client,
        authed_client,
        json_csv,
        db,  # noqa: ANN001
    ) -> None:
        await admin_client.post(
            "/api/v1/admin/collections",
            data={"name": "products"},
            files={"file": ("products.csv", io.BytesIO(json_csv), "text/csv")},
        )
        resp = await authed_client.get("/api/v1/collections/products/schema")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["columns"]["metadata"] == "JSON"
        assert schema["columns"]["tags"] == "JSON"
        assert schema["columns"]["name"] == "TEXT"


class TestJsonFilterAPI:
    @pytest.fixture(autouse=True)
    async def _setup_collection(
        self,
        admin_client,
        authed_client,
        json_csv,
        db,  # noqa: ANN001
    ) -> None:
        await admin_client.post(
            "/api/v1/admin/collections",
            data={"name": "products"},
            files={"file": ("products.csv", io.BytesIO(json_csv), "text/csv")},
        )
        self.client = authed_client

    async def test_filter_by_nested_field(self) -> None:
        resp = await self.client.get(
            "/api/v1/collections/products", params={"metadata.color": "red"}
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2
        names = {row["name"] for row in data}
        assert names == {"Widget A", "Widget C"}

    async def test_nested_numeric_comparison(self) -> None:
        resp = await self.client.get(
            "/api/v1/collections/products", params={"metadata.size__gt": "10"}
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["name"] == "Widget B"

    async def test_deep_nesting(self) -> None:
        resp = await self.client.get(
            "/api/v1/collections/products",
            params={"metadata.coords.lat__gt": "35"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        names = {row["name"] for row in data}
        assert "Widget A" in names  # lat=40.7
        assert "Widget C" in names  # lat=51.5

    async def test_fields_with_dot_notation(self) -> None:
        resp = await self.client.get(
            "/api/v1/collections/products",
            params={"_fields": "name,metadata.color"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 3
        for row in data:
            assert "name" in row
            assert "metadata.color" in row
            assert "_id" not in row

    async def test_search_matches_inside_json(self) -> None:
        resp = await self.client.get(
            "/api/v1/collections/products", params={"_search": "blue"}
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["name"] == "Widget B"

    async def test_dot_on_non_json_column_returns_422(self) -> None:
        resp = await self.client.get(
            "/api/v1/collections/products", params={"name.foo": "bar"}
        )
        assert resp.status_code == 422

    async def test_sort_by_nested_field(self) -> None:
        resp = await self.client.get(
            "/api/v1/collections/products",
            params={"_sort": "-metadata.size"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data[0]["name"] == "Widget B"  # size=25
        assert data[-1]["name"] == "Widget C"  # size=5
