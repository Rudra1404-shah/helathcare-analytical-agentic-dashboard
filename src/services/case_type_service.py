"""Case type definitions: disease classification and triage priority.

A case type with no ``hospital_id`` is a national standard definition visible to
every hospital; one with a hospital is local to it. Both kinds are returned to a
hospital's case-type picker, because a clinician classifying an admission should
reach for the national code first and only define a local one when none fits.
"""

from beanie import PydanticObjectId
from pydantic import ValidationError

from src.core.audit import AuditAction, audit_event
from src.core.errors import PermissionDeniedError
from src.domain.enums import DiseaseCategory, TriageLevel, UserRole
from src.domain.models import CaseType, User
from src.domain.schemas.case_type import CaseTypeCreateRequest, CaseTypeUpdateRequest
from src.services.common import (
    apply_partial_update,
    ensure_hospital_match,
    get_or_404,
    guard_duplicate,
    hospital_scope_of,
    translate_validation_error,
)

__all__ = [
    "count_case_types",
    "create_case_type",
    "get_case_type",
    "list_case_types",
    "update_case_type",
]

_COLLECTION = "case_types"


async def create_case_type(
    request: CaseTypeCreateRequest,
    actor: User,
    hospital_id: PydanticObjectId | None = None,
) -> CaseType:
    """Define a case type.

    A ministry actor passing no hospital creates a national standard; a hospital
    actor always creates a definition scoped to their own hospital.

    Raises:
        ConflictError: If this ICD-10 code is already defined at that scope.
    """
    scope = hospital_scope_of(actor)
    if scope is not None:
        hospital_id = scope
    elif actor.role is not UserRole.GOVT_ADMIN and hospital_id is None:
        msg = "only a government admin may define a national standard case type"
        raise PermissionDeniedError(msg)

    try:
        case_type = CaseType(
            hospital_id=hospital_id,
            name=request.name,
            disease_category=request.disease_category,
            icd10_code=request.icd10_code,
            triage_level=request.triage_level,
            description=request.description,
            is_notifiable=request.is_notifiable,
        )
    except ValidationError as exc:
        raise translate_validation_error(exc) from exc

    scope_label = "nationally" if hospital_id is None else "at this hospital"
    await guard_duplicate(
        case_type.insert,
        f"ICD-10 code {request.icd10_code} is already defined {scope_label}",
    )
    audit_event(
        AuditAction.CREATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=case_type.id,
        hospital_id=hospital_id,
    )
    return case_type


async def get_case_type(case_type_id: PydanticObjectId, actor: User) -> CaseType:
    """Fetch one case type. National definitions are visible to everyone."""
    case_type = await get_or_404(CaseType, case_type_id, "case type")
    if case_type.hospital_id is not None:
        ensure_hospital_match(case_type.hospital_id, hospital_scope_of(actor), "case type")
    return case_type


async def list_case_types(
    actor: User,
    hospital_id: PydanticObjectId | None = None,
    disease_category: DiseaseCategory | None = None,
    triage_level: TriageLevel | None = None,
    is_notifiable: bool | None = None,
    include_national: bool = True,
    skip: int = 0,
    limit: int = 200,
) -> list[CaseType]:
    """Return the case types a hospital may classify an admission with."""
    query = _case_type_query(
        actor, hospital_id, disease_category, triage_level, is_notifiable, include_national
    )
    return await CaseType.find(query).sort("+name").skip(skip).limit(limit).to_list()


async def count_case_types(
    actor: User,
    hospital_id: PydanticObjectId | None = None,
    disease_category: DiseaseCategory | None = None,
    triage_level: TriageLevel | None = None,
    is_notifiable: bool | None = None,
    include_national: bool = True,
) -> int:
    """Return how many case types match the same filters."""
    query = _case_type_query(
        actor, hospital_id, disease_category, triage_level, is_notifiable, include_national
    )
    return await CaseType.find(query).count()


async def update_case_type(
    case_type_id: PydanticObjectId,
    request: CaseTypeUpdateRequest,
    actor: User,
) -> CaseType:
    """Apply a partial update. The ICD-10 code is immutable once defined."""
    case_type = await get_or_404(CaseType, case_type_id, "case type")

    if case_type.hospital_id is None and actor.role is not UserRole.GOVT_ADMIN:
        msg = "a national standard case type may only be amended by the ministry"
        raise PermissionDeniedError(msg)
    if case_type.hospital_id is not None:
        ensure_hospital_match(case_type.hospital_id, hospital_scope_of(actor), "case type")

    changes: dict[str, object] = {
        "name": request.name,
        "disease_category": request.disease_category,
        "triage_level": request.triage_level,
        "description": request.description,
        "is_notifiable": request.is_notifiable,
        "is_active": request.is_active,
    }
    if apply_partial_update(case_type, changes):
        case_type.touch()
        await case_type.save()

    audit_event(
        AuditAction.UPDATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=case_type.id,
        hospital_id=case_type.hospital_id,
    )
    return case_type


def _case_type_query(
    actor: User,
    hospital_id: PydanticObjectId | None,
    disease_category: DiseaseCategory | None,
    triage_level: TriageLevel | None,
    is_notifiable: bool | None,
    include_national: bool,
) -> dict[str, object]:
    """Build the picker filter shared by the list and count queries."""
    query: dict[str, object] = {}

    scope = hospital_scope_of(actor) or hospital_id
    if scope is not None:
        query["hospital_id"] = {"$in": [scope, None]} if include_national else scope
    elif not include_national:
        query["hospital_id"] = {"$ne": None}

    if disease_category is not None:
        query["disease_category"] = disease_category.value
    if triage_level is not None:
        query["triage_level"] = int(triage_level)
    if is_notifiable is not None:
        query["is_notifiable"] = is_notifiable
    return query
