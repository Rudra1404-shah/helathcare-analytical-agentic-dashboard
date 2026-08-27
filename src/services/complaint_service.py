"""Citizen grievances and the ministry investigation workflow.

**Evidence is mandatory.** The submission schema declares ``min_length=1`` and
the stored :class:`~src.domain.models.complaint.Complaint` re-asserts it, so a
complaint with no photo or video cannot be constructed by any code path. This
service adds a third practical guard: it refuses a submission before touching
the database, with a message that names the policy rather than the constraint.

Complaint numbers are generated here rather than supplied by the client. A
citizen filing a grievance has no way to know what number is free, and letting
them choose would let one citizen collide with another's reference.
"""

import secrets
from datetime import datetime

from beanie import PydanticObjectId
from pydantic import ValidationError

from src.core.audit import AuditAction, audit_event
from src.core.errors import ConflictError, PermissionDeniedError, UnprocessableError
from src.domain.enums import (
    CLOSED_INVESTIGATION_STATUSES,
    ComplaintCategory,
    InvestigationStatus,
    UserRole,
)
from src.domain.models import Complaint, Hospital, User
from src.domain.models.base import utcnow
from src.domain.schemas.complaint import ComplaintSubmissionRequest
from src.domain.schemas.govt import ComplaintInvestigationUpdateRequest
from src.services.common import get_or_404, guard_duplicate, translate_validation_error

__all__ = [
    "count_complaints",
    "get_complaint",
    "list_complaints",
    "submit_complaint",
    "update_investigation",
]

_COLLECTION = "complaints"
_NUMBER_PREFIX = "CMP"
_NUMBER_ENTROPY_CHARS = 6
_MAX_NUMBER_ATTEMPTS = 5


async def submit_complaint(
    request: ComplaintSubmissionRequest,
    citizen: User,
) -> Complaint:
    """File a public complaint against a hospital.

    Raises:
        UnprocessableError: If no evidence is attached.
        PermissionDeniedError: If the caller is not a citizen account.
        ConflictError: If the hospital does not exist.
    """
    if citizen.role is not UserRole.CITIZEN:
        msg = "only a citizen account may file a public complaint"
        raise PermissionDeniedError(msg)

    if not request.evidence:
        msg = (
            "a complaint cannot be submitted without evidence: at least one "
            "photo or video attachment is mandatory"
        )
        raise UnprocessableError(msg)

    if await Hospital.get(request.hospital_id) is None:
        msg = f"no hospital exists with id {request.hospital_id}"
        raise ConflictError(msg)

    complaint = await _insert_with_generated_number(request, citizen)
    audit_event(
        AuditAction.CREATE,
        _COLLECTION,
        actor_id=citizen.id,
        actor_role=citizen.role,
        document_id=complaint.id,
        hospital_id=complaint.hospital_id,
        detail=f"{request.category} with {len(request.evidence)} attachment(s)",
    )
    return complaint


async def get_complaint(complaint_id: PydanticObjectId, actor: User) -> Complaint:
    """Fetch one complaint.

    A citizen sees only their own; a hospital account sees only complaints
    filed against their hospital; the ministry sees everything.
    """
    complaint = await get_or_404(Complaint, complaint_id, "complaint")
    _authorise_view(complaint, actor)

    audit_event(
        AuditAction.READ,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=complaint.id,
        hospital_id=complaint.hospital_id,
    )
    return complaint


async def list_complaints(
    actor: User,
    hospital_id: PydanticObjectId | None = None,
    category: ComplaintCategory | None = None,
    investigation_status: InvestigationStatus | None = None,
    open_only: bool = False,
    skip: int = 0,
    limit: int = 50,
) -> list[Complaint]:
    """Return the complaints this actor is entitled to see, newest incident first."""
    query = _complaint_query(actor, hospital_id, category, investigation_status, open_only)
    return await Complaint.find(query).sort("-incident_at").skip(skip).limit(limit).to_list()


async def count_complaints(
    actor: User,
    hospital_id: PydanticObjectId | None = None,
    category: ComplaintCategory | None = None,
    investigation_status: InvestigationStatus | None = None,
    open_only: bool = False,
) -> int:
    """Return how many complaints match the same filters."""
    query = _complaint_query(actor, hospital_id, category, investigation_status, open_only)
    return await Complaint.find(query).count()


async def update_investigation(
    complaint_id: PydanticObjectId,
    request: ComplaintInvestigationUpdateRequest,
    actor: User,
) -> Complaint:
    """Advance the ministry investigation.

    Closing an investigation stamps ``closed_at`` alongside the decision and
    remarks the stored model already insists on, so the resolution timeline is
    recoverable for the impact-tracking module.

    Raises:
        PermissionDeniedError: If the actor is not a government admin.
        ConflictError: If the investigation is already closed.
    """
    if actor.role is not UserRole.GOVT_ADMIN:
        msg = "only the Health Ministry may investigate or resolve a complaint"
        raise PermissionDeniedError(msg)

    complaint = await get_or_404(Complaint, complaint_id, "complaint")
    if complaint.is_closed:
        msg = (
            f"complaint {complaint.complaint_number} is already closed as "
            f"{complaint.investigation_status} and cannot be reopened"
        )
        raise ConflictError(msg)

    closing = request.investigation_status in CLOSED_INVESTIGATION_STATUSES
    try:
        # Assign the supporting fields before the status: the stored model
        # refuses a closed complaint that has no action or remarks yet.
        if request.assigned_officer_id is not None:
            complaint.assigned_officer_id = request.assigned_officer_id
        if request.hospital_explanation is not None:
            complaint.hospital_explanation = request.hospital_explanation
        if request.action_taken is not None:
            complaint.action_taken = request.action_taken
        if request.closure_remarks is not None:
            complaint.closure_remarks = request.closure_remarks
        complaint.investigation_status = request.investigation_status
        if closing:
            complaint.closed_at = utcnow()
    except ValidationError as exc:
        raise translate_validation_error(exc) from exc

    complaint.touch()
    await complaint.save()

    audit_event(
        AuditAction.UPDATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=complaint.id,
        hospital_id=complaint.hospital_id,
        detail=f"investigation -> {request.investigation_status}"
        + (f", action {request.action_taken}" if request.action_taken else ""),
    )
    return complaint


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
async def _insert_with_generated_number(
    request: ComplaintSubmissionRequest,
    citizen: User,
) -> Complaint:
    """Insert the complaint, retrying if a generated number happens to collide.

    Collisions are vanishingly unlikely with the entropy used, but the number
    carries a unique index and a citizen must never see a 500 while trying to
    report a grievance.
    """
    last_error: Exception | None = None

    for _attempt in range(_MAX_NUMBER_ATTEMPTS):
        try:
            complaint = Complaint(
                complaint_number=_generate_number(),
                citizen_user_id=_require_id(citizen),
                hospital_id=request.hospital_id,
                department_id=request.department_id,
                incident_at=request.incident_at,
                category=request.category,
                description=request.description,
                evidence=[item.to_attachment() for item in request.evidence],
            )
        except ValidationError as exc:
            raise translate_validation_error(exc) from exc

        try:
            await guard_duplicate(complaint.insert, "complaint number collision")
        except ConflictError as exc:
            last_error = exc
            continue
        return complaint

    msg = "could not allocate a unique complaint number; please try again"
    raise ConflictError(msg) from last_error


def _generate_number(now: datetime | None = None) -> str:
    """Build a human-quotable complaint reference.

    Shaped ``CMP-20260827-4F2A9C`` so a citizen can read it down a phone line
    and an official can see at a glance when it was filed.
    """
    stamp = (now or utcnow()).strftime("%Y%m%d")
    suffix = secrets.token_hex(_NUMBER_ENTROPY_CHARS // 2).upper()
    return f"{_NUMBER_PREFIX}-{stamp}-{suffix}"


def _require_id(user: User) -> PydanticObjectId:
    """Return a persisted account's id, or fail loudly."""
    if user.id is None:
        msg = "cannot file a complaint from an account that has not been saved"
        raise ConflictError(msg)
    return user.id


def _authorise_view(complaint: Complaint, actor: User) -> None:
    """Refuse a complaint the actor has no standing to read."""
    if actor.role is UserRole.GOVT_ADMIN:
        return
    if actor.role is UserRole.CITIZEN:
        if complaint.citizen_user_id == actor.id:
            return
        msg = "a citizen may only view complaints they filed themselves"
        raise PermissionDeniedError(msg)
    if complaint.hospital_id == actor.hospital_id:
        return
    msg = "this complaint was filed against another hospital"
    raise PermissionDeniedError(msg)


def _complaint_query(
    actor: User,
    hospital_id: PydanticObjectId | None,
    category: ComplaintCategory | None,
    investigation_status: InvestigationStatus | None,
    open_only: bool,
) -> dict[str, object]:
    """Build the desk filter, narrowed by what this actor may see."""
    query: dict[str, object] = {}

    if actor.role is UserRole.CITIZEN:
        query["citizen_user_id"] = actor.id
    elif actor.role is not UserRole.GOVT_ADMIN:
        query["hospital_id"] = actor.hospital_id
    elif hospital_id is not None:
        query["hospital_id"] = hospital_id

    if category is not None:
        query["category"] = category.value
    if investigation_status is not None:
        query["investigation_status"] = investigation_status.value
    elif open_only:
        query["investigation_status"] = {
            "$nin": [status.value for status in CLOSED_INVESTIGATION_STATUSES]
        }
    return query
