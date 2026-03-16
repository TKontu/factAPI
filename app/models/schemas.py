from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class CollectionMeta(BaseModel):
    name: str
    columns: dict[str, str]
    row_count: int
    created_at: str
    updated_at: str


class CollectionSchema(BaseModel):
    name: str
    columns: dict[str, str]


class CollectionListResponse(BaseModel):
    collections: list[CollectionMeta]


class CollectionResponse(BaseModel):
    collection: str
    total: int
    count: int
    limit: int
    offset: int
    data: list[dict[str, object]]
