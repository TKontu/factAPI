from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import close_db, init_db, init_metadata_table
from app.errors import FactAPIError
from app.logging import setup_logging
from app.middleware import RequestMiddleware
from app.models.schemas import HealthResponse
from app.routers.admin import router as admin_router
from app.routers.collections import router as collections_router

logger = structlog.stdlib.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    setup_logging(settings)
    logger.info("startup", env=settings.env, db_path=settings.db_path)
    db = await init_db(settings.db_path)
    await init_metadata_table(db)
    app.state.db = db
    yield
    logger.info("shutdown")
    await close_db(db)


app = FastAPI(title="factAPI", version="0.1.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(RequestMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router)
app.include_router(collections_router)


@app.exception_handler(FactAPIError)
async def factapi_error_handler(request: Request, exc: FactAPIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="healthy", version="0.1.0")
