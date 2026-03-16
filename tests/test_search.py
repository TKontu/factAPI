import io

import pytest
from httpx import AsyncClient

from app.services.query_builder import build_query

COLUMNS = {
    "name": "TEXT",
    "age": "INTEGER",
    "score": "REAL",
    "country": "TEXT",
}


class TestSearchQueryBuilder:
    def test_single_term_ors_all_columns(self) -> None:
        result = build_query("people", COLUMNS, {"_search": "alice"})
        assert "[name] LIKE ?" in result.select_sql
        assert "[country] LIKE ?" in result.select_sql
        assert "CAST([age] AS TEXT) LIKE ?" in result.select_sql
        assert "CAST([score] AS TEXT) LIKE ?" in result.select_sql
        assert "OR" in result.select_sql
        assert "%alice%" in result.count_parameters

    def test_multi_term_ands_groups(self) -> None:
        result = build_query("people", COLUMNS, {"_search": "alice 30"})
        # Two groups ANDed together
        sql = result.select_sql
        assert "AND" in sql
        assert "%alice%" in result.count_parameters
        assert "%30%" in result.count_parameters

    def test_combined_with_filter(self) -> None:
        result = build_query("people", COLUMNS, {"_search": "alice", "country": "USA"})
        assert "[country] = ?" in result.select_sql
        assert "OR" in result.select_sql
        assert result.errors == []

    def test_combined_with_q(self) -> None:
        result = build_query("people", COLUMNS, {"_search": "30", "_q": "alice"})
        assert result.errors == []
        # Both _q and _search should produce clauses
        assert "%alice%" in result.count_parameters
        assert "%30%" in result.count_parameters

    def test_no_errors(self) -> None:
        result = build_query("people", COLUMNS, {"_search": "test"})
        assert result.errors == []

    def test_search_not_treated_as_filter(self) -> None:
        result = build_query("people", COLUMNS, {"_search": "test"})
        assert "Unknown filter" not in " ".join(result.errors)


@pytest.fixture
async def people_collection(admin_client: AsyncClient, sample_csv: bytes) -> str:
    response = await admin_client.post(
        "/api/v1/admin/collections",
        data={"name": "people"},
        files={"file": ("people.csv", io.BytesIO(sample_csv), "text/csv")},
    )
    assert response.status_code == 201
    return "people"


class TestSearchAPI:
    async def test_search_by_name(
        self, authed_client: AsyncClient, people_collection: str
    ) -> None:
        response = await authed_client.get("/api/v1/collections/people?_search=Alice")
        data = response.json()
        assert data["total"] >= 1
        names = [r["name"] for r in data["data"]]
        assert any("Alice" in n for n in names)

    async def test_search_by_numeric_column(
        self, authed_client: AsyncClient, people_collection: str
    ) -> None:
        response = await authed_client.get("/api/v1/collections/people?_search=30")
        data = response.json()
        assert data["total"] >= 1

    async def test_search_multi_term(
        self, authed_client: AsyncClient, people_collection: str
    ) -> None:
        response = await authed_client.get(
            "/api/v1/collections/people?_search=Alice 30"
        )
        data = response.json()
        # Alice is age 30, so should match
        assert data["total"] >= 1
        assert data["data"][0]["name"] == "Alice"

    async def test_search_no_match(
        self, authed_client: AsyncClient, people_collection: str
    ) -> None:
        response = await authed_client.get(
            "/api/v1/collections/people?_search=zzzznonexistent"
        )
        data = response.json()
        assert data["total"] == 0

    async def test_search_combined_with_filter(
        self, authed_client: AsyncClient, people_collection: str
    ) -> None:
        response = await authed_client.get(
            "/api/v1/collections/people?_search=95&age__gte=25"
        )
        data = response.json()
        assert data["total"] >= 1
        for row in data["data"]:
            assert row["age"] >= 25
