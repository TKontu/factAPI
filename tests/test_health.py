from httpx import AsyncClient


class TestHealthEndpoint:
    async def test_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200

    async def test_response_body(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"
