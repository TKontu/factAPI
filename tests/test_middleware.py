import re

from fastapi import APIRouter
from httpx import AsyncClient


class TestMiddleware:
    async def test_unknown_route_returns_404(self, client: AsyncClient) -> None:
        response = await client.get("/nonexistent")
        assert response.status_code == 404

    async def test_request_id_in_response(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        request_id = response.headers.get("X-Request-ID")
        assert request_id is not None
        assert re.fullmatch(r"[0-9a-f]{32}", request_id)

    async def test_unhandled_exception_returns_safe_500(
        self,
        app,
        client: AsyncClient,  # noqa: ANN001
    ) -> None:
        error_router = APIRouter()

        @error_router.get("/test-error")
        async def raise_error() -> None:
            raise RuntimeError("this should not leak")

        app.include_router(error_router)

        response = await client.get("/test-error")
        assert response.status_code == 500
        body = response.json()
        assert body == {
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Internal server error",
            }
        }
        assert "this should not leak" not in response.text
        assert response.headers.get("X-Request-ID") is not None
