import structlog
from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile

from app.auth import require_admin_key
from app.models.schemas import CollectionMeta
from app.services.collection_manager import delete_collection, get_collection_or_404
from app.services.importer import append_csv, import_csv

logger = structlog.stdlib.get_logger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/collections", status_code=201, response_model=CollectionMeta)
async def create_collection(
    request: Request,
    name: str = Form(...),
    file: UploadFile = File(...),  # noqa: B008
    _key: str = Depends(require_admin_key),
) -> CollectionMeta:
    """Import a CSV file as a new collection."""
    db = request.app.state.db
    content = await file.read()
    meta = await import_csv(db, name, content)
    logger.info("collection_created", collection=name, row_count=meta["row_count"])
    return CollectionMeta(**meta)


@router.delete("/collections/{name}", status_code=204)
async def delete_collection_endpoint(
    name: str,
    request: Request,
    _key: str = Depends(require_admin_key),
) -> Response:
    """Delete a collection and its metadata."""
    db = request.app.state.db
    await delete_collection(db, name)
    logger.info("collection_deleted", collection=name)
    return Response(status_code=204)


@router.put("/collections/{name}", response_model=CollectionMeta)
async def replace_collection(
    name: str,
    request: Request,
    file: UploadFile = File(...),  # noqa: B008
    _key: str = Depends(require_admin_key),
) -> CollectionMeta:
    """Replace an existing collection with new CSV data."""
    db = request.app.state.db
    await get_collection_or_404(db, name)
    content = await file.read()
    meta = await import_csv(db, name, content, overwrite=True)
    logger.info("collection_replaced", collection=name, row_count=meta["row_count"])
    return CollectionMeta(**meta)


@router.post("/collections/{name}/append", response_model=CollectionMeta)
async def append_to_collection(
    name: str,
    request: Request,
    file: UploadFile = File(...),  # noqa: B008
    _key: str = Depends(require_admin_key),
) -> CollectionMeta:
    """Append rows from a CSV file to an existing collection."""
    db = request.app.state.db
    content = await file.read()
    meta = await append_csv(db, name, content)
    logger.info("collection_appended", collection=name, row_count=meta["row_count"])
    return CollectionMeta(**meta)
