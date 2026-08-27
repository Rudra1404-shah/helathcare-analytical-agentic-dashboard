"""Public complaint submission and the ministry investigation desk.

Evidence is mandatory to submit. The request schema declares it, the service
re-checks it, and the stored document enforces it a third time. A client that
strips the attachment array gets a 422 naming the policy, not a length error.
"""

from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Body, Query, status

from src.api.deps import CurrentUser, GovtAdmin, Paging
from src.domain.enums import ComplaintCategory, InvestigationStatus
from src.domain.schemas.common import ApiResponse, PaginatedResponse
from src.domain.schemas.complaint import ComplaintResponse, ComplaintSubmissionRequest
from src.domain.schemas.govt import ComplaintInvestigationUpdateRequest
from src.services import complaint_service

router = APIRouter(prefix="/complaints", tags=["complaints"])


@router.post("", response_model=ApiResponse[ComplaintResponse], status_code=status.HTTP_201_CREATED)
async def submit_complaint(
    request: Annotated[ComplaintSubmissionRequest, Body()],
    actor: CurrentUser,
) -> ApiResponse[ComplaintResponse]:
    """File a public complaint against a hospital.

    **At least one photo or video is mandatory.** Upload the media through
    ``POST /uploads/evidence`` first, then pass the returned URL, content type,
    size, and checksum here.

    The complaint number is generated server-side; a citizen has no way to know
    which references are free.
    """
    complaint = await complaint_service.submit_complaint(request, actor)
    return ApiResponse.ok(ComplaintResponse.model_validate(complaint))


@router.get("", response_model=ApiResponse[PaginatedResponse[ComplaintResponse]])
async def list_complaints(
    actor: CurrentUser,
    paging: Paging,
    hospital_id: Annotated[PydanticObjectId | None, Query()] = None,
    category: Annotated[ComplaintCategory | None, Query()] = None,
    investigation_status: Annotated[InvestigationStatus | None, Query()] = None,
    open_only: Annotated[bool, Query(description="Exclude closed investigations.")] = False,
) -> ApiResponse[PaginatedResponse[ComplaintResponse]]:
    """Return the complaints this account is entitled to see.

    A citizen sees only their own; a hospital account sees only complaints filed
    against their hospital; the ministry sees everything.
    """
    complaints = await complaint_service.list_complaints(
        actor,
        hospital_id=hospital_id,
        category=category,
        investigation_status=investigation_status,
        open_only=open_only,
        skip=paging.skip,
        limit=paging.limit,
    )
    total = await complaint_service.count_complaints(
        actor,
        hospital_id=hospital_id,
        category=category,
        investigation_status=investigation_status,
        open_only=open_only,
    )
    return ApiResponse.ok(
        PaginatedResponse(
            items=[ComplaintResponse.model_validate(item) for item in complaints],
            meta=paging.meta(total),
        )
    )


@router.get("/{complaint_id}", response_model=ApiResponse[ComplaintResponse])
async def read_complaint(
    complaint_id: PydanticObjectId,
    actor: CurrentUser,
) -> ApiResponse[ComplaintResponse]:
    """Return one complaint and its full investigation trail."""
    complaint = await complaint_service.get_complaint(complaint_id, actor)
    return ApiResponse.ok(ComplaintResponse.model_validate(complaint))


@router.patch("/{complaint_id}/investigation", response_model=ApiResponse[ComplaintResponse])
async def update_investigation(
    complaint_id: PydanticObjectId,
    request: Annotated[ComplaintInvestigationUpdateRequest, Body()],
    actor: GovtAdmin,
) -> ApiResponse[ComplaintResponse]:
    """Advance or close the investigation. Ministry only.

    Closing requires both a decision and the reasoning behind it -- an
    enforcement action with no recorded rationale is not auditable.
    """
    complaint = await complaint_service.update_investigation(complaint_id, request, actor)
    return ApiResponse.ok(ComplaintResponse.model_validate(complaint))
