"""Shared schema bases and the standard API response envelope.

Request schemas forbid unknown fields so a typo in a form payload fails loudly
instead of being silently dropped. Response schemas read from model attributes
so a Beanie document can be converted directly.
"""

from datetime import datetime
from typing import Generic, TypeVar

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ApiResponse",
    "IdentifiedResponse",
    "PageMeta",
    "PaginatedResponse",
    "RequestSchema",
    "ResponseSchema",
]

T = TypeVar("T")


class RequestSchema(BaseModel):
    """Base for every inbound form payload."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class ResponseSchema(BaseModel):
    """Base for every outbound payload."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        ser_json_timedelta="iso8601",
    )


class IdentifiedResponse(ResponseSchema):
    """Response carrying the stored document's identity and timestamps."""

    id: PydanticObjectId = Field(alias="_id", description="MongoDB document identifier.")
    created_at: datetime
    updated_at: datetime


class PageMeta(ResponseSchema):
    """Pagination metadata attached to a list response."""

    total: int = Field(ge=0, description="Total matching records.")
    page: int = Field(ge=1, description="Current page, 1-indexed.")
    limit: int = Field(ge=1, le=200, description="Records per page.")

    @property
    def total_pages(self) -> int:
        """Return the number of pages available."""
        if self.limit == 0:
            return 0
        return -(-self.total // self.limit)


class ApiResponse(ResponseSchema, Generic[T]):
    """The platform-wide response envelope.

    Every endpoint returns this shape, so clients parse one structure whether
    the call succeeded or failed.
    """

    success: bool = Field(description="Whether the operation succeeded.")
    data: T | None = Field(default=None, description="Payload on success.")
    error: str | None = Field(default=None, description="Human-readable error on failure.")
    meta: PageMeta | None = Field(default=None, description="Pagination metadata, if any.")

    @classmethod
    def ok(cls, data: T, meta: PageMeta | None = None) -> "ApiResponse[T]":
        """Build a success envelope."""
        return cls(success=True, data=data, error=None, meta=meta)

    @classmethod
    def fail(cls, error: str) -> "ApiResponse[T]":
        """Build a failure envelope."""
        return cls(success=False, data=None, error=error, meta=None)


class PaginatedResponse(ResponseSchema, Generic[T]):
    """A page of results plus its metadata."""

    items: list[T] = Field(default_factory=list)
    meta: PageMeta
