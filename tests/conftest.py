import tempfile
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings, get_settings


@pytest.fixture
def settings_override() -> Settings:
    tmp_path = tempfile.mktemp(suffix=".db")
    return Settings(
        db_path=tmp_path,
        api_key="test-api-key",
        admin_key="test-admin-key",
        cors_origins="*",
        log_level="debug",
    )


@pytest.fixture
async def app(settings_override: Settings):  # noqa: ANN201
    with (
        patch("app.main.get_settings", return_value=settings_override),
        patch("app.config.get_settings", return_value=settings_override),
    ):
        from app.main import app as _app

        _app.dependency_overrides[get_settings] = lambda: settings_override
        async with _app.router.lifespan_context(_app):
            yield _app
        _app.dependency_overrides.clear()


@pytest.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:  # noqa: ANN001
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture
def sample_csv() -> bytes:
    return b"name,age,score\nAlice,30,95.5\nBob,25,87.0\nCharlie,35,92.3\nDiana,28,88.1\nEve,32,91.7"


@pytest.fixture
def json_csv() -> bytes:
    return (
        b"name,metadata,tags\n"
        b'Widget A,"{""color"":""red"",""size"":10,""coords"":{""lat"":40.7,""lon"":-74.0}}","[""sale"",""new""]"\n'
        b'Widget B,"{""color"":""blue"",""size"":25,""coords"":{""lat"":34.0,""lon"":-118.2}}","[""featured""]"\n'
        b'Widget C,"{""color"":""red"",""size"":5,""coords"":{""lat"":51.5,""lon"":-0.1}}","[""sale""]"'
    )


@pytest.fixture
def db(app):  # noqa: ANN001, ANN201
    return app.state.db


@pytest.fixture
async def authed_client(app) -> AsyncGenerator[AsyncClient, None]:  # noqa: ANN001
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": "test-api-key"},
    ) as ac:
        yield ac


@pytest.fixture
async def admin_client(app) -> AsyncGenerator[AsyncClient, None]:  # noqa: ANN001
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Admin-Key": "test-admin-key"},
    ) as ac:
        yield ac
