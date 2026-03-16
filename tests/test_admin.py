import io

from httpx import AsyncClient


class TestCreateCollection:
    async def test_create_with_valid_csv(
        self, admin_client: AsyncClient, sample_csv: bytes
    ) -> None:
        response = await admin_client.post(
            "/api/v1/admin/collections",
            data={"name": "testcol"},
            files={"file": ("test.csv", sample_csv, "text/csv")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "testcol"
        assert data["row_count"] == 5
        assert "name" in data["columns"]
        assert "age" in data["columns"]
        assert "score" in data["columns"]
        assert "created_at" in data
        assert "updated_at" in data

    async def test_create_without_admin_key(
        self, client: AsyncClient, sample_csv: bytes
    ) -> None:
        response = await client.post(
            "/api/v1/admin/collections",
            data={"name": "testcol"},
            files={"file": ("test.csv", sample_csv, "text/csv")},
        )
        assert response.status_code == 401

    async def test_duplicate_name_returns_409(
        self, admin_client: AsyncClient, sample_csv: bytes
    ) -> None:
        await admin_client.post(
            "/api/v1/admin/collections",
            data={"name": "duptest"},
            files={"file": ("test.csv", sample_csv, "text/csv")},
        )
        response = await admin_client.post(
            "/api/v1/admin/collections",
            data={"name": "duptest"},
            files={"file": ("test.csv", sample_csv, "text/csv")},
        )
        assert response.status_code == 409

    async def test_invalid_collection_name(
        self, admin_client: AsyncClient, sample_csv: bytes
    ) -> None:
        response = await admin_client.post(
            "/api/v1/admin/collections",
            data={"name": "123invalid"},
            files={"file": ("test.csv", sample_csv, "text/csv")},
        )
        assert response.status_code == 422


class TestDeleteCollection:
    async def test_delete_returns_204(
        self, admin_client: AsyncClient, sample_csv: bytes
    ) -> None:
        await admin_client.post(
            "/api/v1/admin/collections",
            data={"name": "todelete"},
            files={"file": ("test.csv", sample_csv, "text/csv")},
        )
        response = await admin_client.delete("/api/v1/admin/collections/todelete")
        assert response.status_code == 204

    async def test_delete_collection_is_gone(
        self, admin_client: AsyncClient, authed_client: AsyncClient, sample_csv: bytes
    ) -> None:
        await admin_client.post(
            "/api/v1/admin/collections",
            data={"name": "gonecol"},
            files={"file": ("test.csv", sample_csv, "text/csv")},
        )
        await admin_client.delete("/api/v1/admin/collections/gonecol")
        response = await authed_client.get("/api/v1/collections/gonecol")
        assert response.status_code == 404

    async def test_delete_nonexistent_returns_404(
        self, admin_client: AsyncClient
    ) -> None:
        response = await admin_client.delete("/api/v1/admin/collections/nonexistent")
        assert response.status_code == 404

    async def test_delete_without_admin_key(
        self, client: AsyncClient, sample_csv: bytes
    ) -> None:
        response = await client.delete("/api/v1/admin/collections/anything")
        assert response.status_code == 401


class TestReplaceCollection:
    async def test_put_replaces_data(
        self, admin_client: AsyncClient, sample_csv: bytes
    ) -> None:
        await admin_client.post(
            "/api/v1/admin/collections",
            data={"name": "replaceme"},
            files={"file": ("test.csv", sample_csv, "text/csv")},
        )
        new_csv = b"name,age,score\nZara,40,99.0"
        response = await admin_client.put(
            "/api/v1/admin/collections/replaceme",
            files={"file": ("new.csv", io.BytesIO(new_csv), "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["row_count"] == 1

    async def test_put_nonexistent_returns_404(self, admin_client: AsyncClient) -> None:
        new_csv = b"name,age\nTest,1"
        response = await admin_client.put(
            "/api/v1/admin/collections/nonexistent",
            files={"file": ("new.csv", io.BytesIO(new_csv), "text/csv")},
        )
        assert response.status_code == 404

    async def test_put_without_admin_key(self, client: AsyncClient) -> None:
        response = await client.put(
            "/api/v1/admin/collections/anything",
            files={"file": ("new.csv", io.BytesIO(b"a,b\n1,2"), "text/csv")},
        )
        assert response.status_code == 401


class TestAppendCollection:
    async def test_append_increases_row_count(
        self, admin_client: AsyncClient, sample_csv: bytes
    ) -> None:
        await admin_client.post(
            "/api/v1/admin/collections",
            data={"name": "appendme"},
            files={"file": ("test.csv", sample_csv, "text/csv")},
        )
        append_csv = b"name,age,score\nFrank,45,80.0\nGrace,22,76.5"
        response = await admin_client.post(
            "/api/v1/admin/collections/appendme/append",
            files={"file": ("append.csv", io.BytesIO(append_csv), "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["row_count"] == 7  # 5 original + 2 appended

    async def test_append_mismatched_columns_returns_422(
        self, admin_client: AsyncClient, sample_csv: bytes
    ) -> None:
        await admin_client.post(
            "/api/v1/admin/collections",
            data={"name": "mismatch"},
            files={"file": ("test.csv", sample_csv, "text/csv")},
        )
        bad_csv = b"name,age,wrong_column\nFrank,45,80.0"
        response = await admin_client.post(
            "/api/v1/admin/collections/mismatch/append",
            files={"file": ("bad.csv", io.BytesIO(bad_csv), "text/csv")},
        )
        assert response.status_code == 422

    async def test_append_nonexistent_returns_404(
        self, admin_client: AsyncClient
    ) -> None:
        csv_data = b"name,age\nTest,1"
        response = await admin_client.post(
            "/api/v1/admin/collections/nonexistent/append",
            files={"file": ("test.csv", io.BytesIO(csv_data), "text/csv")},
        )
        assert response.status_code == 404

    async def test_append_without_admin_key(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/admin/collections/anything/append",
            files={"file": ("test.csv", io.BytesIO(b"a,b\n1,2"), "text/csv")},
        )
        assert response.status_code == 401
