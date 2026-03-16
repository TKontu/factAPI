from httpx import AsyncClient


class TestApiKeyAuth:
    async def test_valid_api_key(self, authed_client: AsyncClient) -> None:
        response = await authed_client.get("/api/v1/collections")
        assert response.status_code == 200

    async def test_invalid_api_key(self, client: AsyncClient) -> None:
        response = await client.get(
            "/api/v1/collections", headers={"X-API-Key": "wrong-key"}
        )
        assert response.status_code == 401

    async def test_missing_api_key(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/collections")
        assert response.status_code == 401


class TestAdminKeyAuth:
    async def test_valid_admin_key(
        self, admin_client: AsyncClient, sample_csv: bytes
    ) -> None:
        response = await admin_client.post(
            "/api/v1/admin/collections",
            data={"name": "authtest"},
            files={"file": ("test.csv", sample_csv, "text/csv")},
        )
        assert response.status_code == 201

    async def test_invalid_admin_key(
        self, client: AsyncClient, sample_csv: bytes
    ) -> None:
        response = await client.post(
            "/api/v1/admin/collections",
            data={"name": "authtest"},
            files={"file": ("test.csv", sample_csv, "text/csv")},
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert response.status_code == 401

    async def test_missing_admin_key(
        self, client: AsyncClient, sample_csv: bytes
    ) -> None:
        response = await client.post(
            "/api/v1/admin/collections",
            data={"name": "authtest"},
            files={"file": ("test.csv", sample_csv, "text/csv")},
        )
        assert response.status_code == 401


class TestAuthSkippedWhenNoKey:
    async def test_no_api_key_configured(self) -> None:
        """When api_key setting is empty, auth is skipped."""
        import tempfile
        from unittest.mock import patch

        from httpx import ASGITransport, AsyncClient

        from app.config import Settings

        no_auth_settings = Settings(
            db_path=tempfile.mktemp(suffix=".db"),
            api_key="",
            admin_key="",
            cors_origins="*",
            log_level="debug",
            _env_file=None,  # type: ignore[call-arg]
        )
        with (
            patch("app.main.get_settings", return_value=no_auth_settings),
            patch("app.config.get_settings", return_value=no_auth_settings),
        ):
            from app.config import get_settings
            from app.main import app as test_app

            test_app.dependency_overrides[get_settings] = lambda: no_auth_settings
            async with (
                test_app.router.lifespan_context(test_app),
                AsyncClient(
                    transport=ASGITransport(app=test_app),
                    base_url="http://test",
                ) as ac,
            ):
                response = await ac.get("/api/v1/collections")
                assert response.status_code == 200
            test_app.dependency_overrides.clear()
