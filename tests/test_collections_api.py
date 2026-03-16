import io

import pytest
from httpx import AsyncClient


@pytest.fixture
async def people_collection(admin_client: AsyncClient, sample_csv: bytes) -> str:
    """Import sample_csv as 'people' collection."""
    response = await admin_client.post(
        "/api/v1/admin/collections",
        data={"name": "people"},
        files={"file": ("people.csv", io.BytesIO(sample_csv), "text/csv")},
    )
    assert response.status_code == 201
    return "people"


class TestQueryCollectionAuth:
    async def test_requires_auth(
        self, client: AsyncClient, people_collection: str
    ) -> None:
        response = await client.get("/api/v1/collections/people")
        assert response.status_code == 401


class TestQueryCollectionNotFound:
    async def test_nonexistent_collection_returns_404(
        self, authed_client: AsyncClient
    ) -> None:
        response = await authed_client.get("/api/v1/collections/nonexistent")
        assert response.status_code == 404


class TestQueryCollectionBasic:
    async def test_get_all_rows(
        self, authed_client: AsyncClient, people_collection: str
    ) -> None:
        response = await authed_client.get("/api/v1/collections/people")
        assert response.status_code == 200
        data = response.json()
        assert data["collection"] == "people"
        assert data["total"] == 5
        assert data["count"] == 5
        assert len(data["data"]) == 5

    async def test_response_shape(
        self, authed_client: AsyncClient, people_collection: str
    ) -> None:
        response = await authed_client.get("/api/v1/collections/people")
        data = response.json()
        assert "collection" in data
        assert "total" in data
        assert "count" in data
        assert "limit" in data
        assert "offset" in data
        assert "data" in data
        # Each row should have _id and the columns
        row = data["data"][0]
        assert "_id" in row
        assert "name" in row
        assert "age" in row
        assert "score" in row


class TestQueryCollectionFilters:
    async def test_exact_filter(
        self, authed_client: AsyncClient, people_collection: str
    ) -> None:
        response = await authed_client.get("/api/v1/collections/people?name=Alice")
        data = response.json()
        assert data["total"] == 1
        assert data["count"] == 1
        assert data["data"][0]["name"] == "Alice"

    async def test_operator_filter_gt(
        self, authed_client: AsyncClient, people_collection: str
    ) -> None:
        response = await authed_client.get("/api/v1/collections/people?age__gt=30")
        data = response.json()
        assert data["total"] > 0
        for row in data["data"]:
            assert row["age"] > 30

    async def test_invalid_filter_column(
        self, authed_client: AsyncClient, people_collection: str
    ) -> None:
        response = await authed_client.get("/api/v1/collections/people?bogus=value")
        assert response.status_code == 422


class TestQueryCollectionPagination:
    async def test_limit(
        self, authed_client: AsyncClient, people_collection: str
    ) -> None:
        response = await authed_client.get("/api/v1/collections/people?_limit=2")
        data = response.json()
        assert data["count"] == 2
        assert data["limit"] == 2
        assert data["total"] == 5

    async def test_offset(
        self, authed_client: AsyncClient, people_collection: str
    ) -> None:
        response = await authed_client.get(
            "/api/v1/collections/people?_limit=2&_offset=3"
        )
        data = response.json()
        assert data["count"] == 2
        assert data["offset"] == 3


class TestQueryCollectionSorting:
    async def test_sort_ascending(
        self, authed_client: AsyncClient, people_collection: str
    ) -> None:
        response = await authed_client.get("/api/v1/collections/people?_sort=name")
        data = response.json()
        names = [r["name"] for r in data["data"]]
        assert names == sorted(names)

    async def test_sort_descending(
        self, authed_client: AsyncClient, people_collection: str
    ) -> None:
        response = await authed_client.get("/api/v1/collections/people?_sort=-name")
        data = response.json()
        names = [r["name"] for r in data["data"]]
        assert names == sorted(names, reverse=True)


class TestQueryCollectionFields:
    async def test_fields_selection(
        self, authed_client: AsyncClient, people_collection: str
    ) -> None:
        response = await authed_client.get(
            "/api/v1/collections/people?_fields=name,age"
        )
        data = response.json()
        row = data["data"][0]
        assert "name" in row
        assert "age" in row
        assert "score" not in row
        assert "_id" not in row


class TestQueryCollectionFullTextSearch:
    async def test_q_finds_matching_rows(
        self, authed_client: AsyncClient, people_collection: str
    ) -> None:
        response = await authed_client.get("/api/v1/collections/people?_q=ali")
        data = response.json()
        assert data["total"] >= 1
        names = [r["name"] for r in data["data"]]
        assert any("Ali" in n for n in names)


class TestCollectionSchema:
    async def test_returns_schema(
        self, authed_client: AsyncClient, people_collection: str
    ) -> None:
        response = await authed_client.get("/api/v1/collections/people/schema")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "people"
        assert "name" in data["columns"]
        assert "age" in data["columns"]
        assert "score" in data["columns"]
        assert data["columns"]["name"] == "TEXT"
        assert data["columns"]["age"] == "INTEGER"
        assert data["columns"]["score"] == "REAL"

    async def test_404_for_nonexistent(self, authed_client: AsyncClient) -> None:
        response = await authed_client.get("/api/v1/collections/nonexistent/schema")
        assert response.status_code == 404

    async def test_401_without_auth(
        self, client: AsyncClient, people_collection: str
    ) -> None:
        response = await client.get("/api/v1/collections/people/schema")
        assert response.status_code == 401


class TestSingleRecord:
    async def test_get_record_by_id(
        self, authed_client: AsyncClient, people_collection: str
    ) -> None:
        response = await authed_client.get("/api/v1/collections/people/1")
        assert response.status_code == 200
        data = response.json()
        assert data["_id"] == 1
        assert "name" in data

    async def test_404_for_missing_id(
        self, authed_client: AsyncClient, people_collection: str
    ) -> None:
        response = await authed_client.get("/api/v1/collections/people/9999")
        assert response.status_code == 404

    async def test_404_for_missing_collection(self, authed_client: AsyncClient) -> None:
        response = await authed_client.get("/api/v1/collections/nonexistent/1")
        assert response.status_code == 404

    async def test_401_without_auth(
        self, client: AsyncClient, people_collection: str
    ) -> None:
        response = await client.get("/api/v1/collections/people/1")
        assert response.status_code == 401
