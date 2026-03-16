import secrets

import structlog
from fastapi import Depends, Request
from fastapi.security import APIKeyHeader

from app.config import Settings, get_settings
from app.errors import AuthenticationError

logger = structlog.stdlib.get_logger(__name__)

api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="X-API-Key",
    description="API key for read access to collections",
    auto_error=False,
)
admin_key_header = APIKeyHeader(
    name="X-Admin-Key",
    scheme_name="X-Admin-Key",
    description="Admin key for creating, updating, and deleting collections",
    auto_error=False,
)


async def require_api_key(
    request: Request,
    api_key: str | None = Depends(api_key_header),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> str:
    """Validate the X-API-Key header. Skips auth if no key is configured."""
    if not settings.api_key:
        return ""
    if not api_key or not secrets.compare_digest(api_key, settings.api_key):
        logger.warning("auth_failed", auth_type="api_key", path=request.url.path)
        raise AuthenticationError()
    return api_key


async def require_admin_key(
    request: Request,
    admin_key: str | None = Depends(admin_key_header),  # noqa: B008
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> str:
    """Validate the X-Admin-Key header. Skips auth if no key is configured."""
    if not settings.admin_key:
        return ""
    if not admin_key or not secrets.compare_digest(admin_key, settings.admin_key):
        logger.warning("auth_failed", auth_type="admin_key", path=request.url.path)
        raise AuthenticationError()
    return admin_key
