from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(description="Service status", examples=["healthy"])
    version: str = Field(description="API version", examples=["0.1.0"])


class ErrorDetail(BaseModel):
    """Error detail payload."""

    code: str = Field(description="Machine-readable error code", examples=["NOT_FOUND"])
    message: str = Field(
        description="Human-readable error message",
        examples=["Resource not found"],
    )


class ErrorResponse(BaseModel):
    """Standard error response wrapper."""

    error: ErrorDetail


class CollectionMeta(BaseModel):
    """Metadata about a data collection."""

    name: str = Field(description="Collection name", examples=["cities"])
    columns: dict[str, str] = Field(
        description="Column names mapped to types (TEXT, INTEGER, REAL, JSON)",
        examples=[{"city": "TEXT", "population": "INTEGER"}],
    )
    row_count: int = Field(description="Total number of rows", examples=[47868])
    created_at: str = Field(description="ISO timestamp of creation")
    updated_at: str = Field(description="ISO timestamp of last update")


class CollectionSchema(BaseModel):
    """Column schema for a collection."""

    name: str = Field(description="Collection name", examples=["cities"])
    columns: dict[str, str] = Field(
        description="Column names mapped to types (TEXT, INTEGER, REAL, JSON)",
        examples=[{"city": "TEXT", "population": "INTEGER", "metadata": "JSON"}],
    )


class CollectionListResponse(BaseModel):
    """List of all available collections."""

    collections: list[CollectionMeta]


class CollectionResponse(BaseModel):
    """Query response with data rows and pagination metadata."""

    collection: str = Field(description="Collection name", examples=["cities"])
    total: int = Field(
        description="Total matching rows (before pagination)", examples=[47868]
    )
    count: int = Field(
        description="Number of rows returned in this page", examples=[10]
    )
    limit: int = Field(description="Page size used", examples=[100])
    offset: int = Field(description="Number of rows skipped", examples=[0])
    data: list[dict[str, object]] = Field(description="Array of row objects")
