import secrets

import structlog
from fastapi import Depends, Request

from app.config import Settings, get_settings
from app.errors import AuthenticationError

logger = structlog.stdlib.get_logger(__name__)


async def require_api_key(
    request: Request,
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> str:
    """Validate the X-API-Key header. Skips auth if no key is configured."""
    if not settings.api_key:
        return ""
    key = request.headers.get("X-API-Key", "")
    if not key or not secrets.compare_digest(key, settings.api_key):
        logger.warning("auth_failed", auth_type="api_key", path=request.url.path)
        raise AuthenticationError()
    return key


async def require_admin_key(
    request: Request,
    settings: Settings = Depends(get_settings),  # noqa: B008
) -> str:
    """Validate the X-Admin-Key header. Skips auth if no key is configured."""
    if not settings.admin_key:
        return ""
    key = request.headers.get("X-Admin-Key", "")
    if not key or not secrets.compare_digest(key, settings.admin_key):
        logger.warning("auth_failed", auth_type="admin_key", path=request.url.path)
        raise AuthenticationError()
    return key
