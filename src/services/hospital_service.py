"""Hospital onboarding, directory search, and ministry accreditation.

Two portals write to the same ``hospitals`` document from different sides. The
ministry owns identity and accreditation -- licence number, sector, sanctioned
capacity, accreditation state. A hospital admin owns operational infrastructure
-- working bed counts, oxygen, ambulances, contact details. Splitting those into
two functions here is what stops a hospital from quietly upgrading its own
accreditation.
"""

import re
from datetime import date

from beanie import PydanticObjectId
from pydantic import BaseModel, ValidationError

from src.core.audit import AuditAction, audit_event
from src.core.errors import ConflictError
from src.domain.enums import AccreditationStatus, SectorType
from src.domain.models import Hospital, HospitalCapacity, User, Zone
from src.domain.models.base import utcnow
from src.domain.schemas.govt import HospitalAccreditationUpdateRequest
from src.domain.schemas.hospital import (
    HospitalCapacityPayload,
    HospitalCreateRequest,
    HospitalProfileUpdateRequest,
)
from src.services.common import (
    apply_partial_update,
    ensure_hospital_match,
    get_or_404,
    guard_duplicate,
    hospital_scope_of,
    translate_validation_error,
)

__all__ = [
    "count_hospitals",
    "create_hospital",
    "get_hospital",
    "list_cities",
    "list_hospitals",
    "update_accreditation",
    "update_profile",
]

_COLLECTION = "hospitals"


async def create_hospital(request: HospitalCreateRequest, actor: User) -> Hospital:
    """Register a hospital from the Government Verification & Accreditation Form.

    Raises:
        ConflictError: If the licence number is already registered, or the
            zone code does not exist.
    """
    await _require_known_zone(request.zone_code)

    try:
        hospital = Hospital(
            name=request.name,
            license_no=request.license_no,
            sector_type=request.sector_type,
            state=request.state,
            city=request.city,
            zone_code=request.zone_code,
            ward_area=request.ward_area,
            location=request.location.to_geo_location(),
            address=request.address,
            capacity=_to_capacity(request.capacity),
            accreditation_status=request.accreditation_status,
            accredited_on=request.accredited_on,
            license_valid_until=request.license_valid_until,
            nodal_officer_name=request.nodal_officer_name,
            nodal_officer_id=request.nodal_officer_id,
            contact_phone=request.contact_phone,
            contact_email=request.contact_email,
        )
    except ValidationError as exc:
        raise translate_validation_error(exc) from exc

    await guard_duplicate(
        hospital.insert,
        f"licence number {request.license_no} is already registered to another hospital",
    )
    audit_event(
        AuditAction.CREATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=hospital.id,
        hospital_id=hospital.id,
    )
    return hospital


async def get_hospital(hospital_id: PydanticObjectId, actor: User) -> Hospital:
    """Fetch one hospital, enforcing hospital scope for non-ministry actors."""
    hospital = await get_or_404(Hospital, hospital_id, "hospital")
    ensure_hospital_match(hospital.id, hospital_scope_of(actor), "hospital")
    return hospital


async def list_hospitals(
    actor: User,
    state: str | None = None,
    city: str | None = None,
    zone_code: str | None = None,
    sector_type: SectorType | None = None,
    accreditation_status: AccreditationStatus | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Hospital]:
    """Return the hospital directory, filtered as the ministry portal requires.

    A hospital-scoped actor only ever sees their own hospital, whatever filters
    they pass.
    """
    query = _directory_query(
        actor, state, city, zone_code, sector_type, accreditation_status, search
    )
    return await Hospital.find(query).sort("+name").skip(skip).limit(limit).to_list()


async def count_hospitals(
    actor: User,
    state: str | None = None,
    city: str | None = None,
    zone_code: str | None = None,
    sector_type: SectorType | None = None,
    accreditation_status: AccreditationStatus | None = None,
    search: str | None = None,
) -> int:
    """Return how many hospitals match the same filters, for pagination."""
    query = _directory_query(
        actor, state, city, zone_code, sector_type, accreditation_status, search
    )
    return await Hospital.find(query).count()


async def list_cities(actor: User) -> list[dict[str, str]]:
    """Return the distinct state/city pairs present in the directory.

    Powers the city filter in the ministry portal without the client having to
    page through every hospital to discover the options.
    """
    query = _directory_query(actor, None, None, None, None, None, None)
    hospitals = await Hospital.find(query).project(_CityProjection).to_list()
    pairs = {(item.state, item.city) for item in hospitals}
    return [
        {"state": state, "city": city} for state, city in sorted(pairs, key=lambda p: (p[0], p[1]))
    ]


async def update_profile(
    hospital_id: PydanticObjectId,
    request: HospitalProfileUpdateRequest,
    actor: User,
) -> Hospital:
    """Apply the Hospital Profile & Infrastructure Setup Form.

    Deliberately cannot touch licence number, sector, or accreditation state.
    """
    hospital = await get_or_404(Hospital, hospital_id, "hospital")
    ensure_hospital_match(hospital.id, hospital_scope_of(actor), "hospital")

    changes: dict[str, object] = {
        "ward_area": request.ward_area,
        "address": request.address,
        "contact_phone": request.contact_phone,
        "contact_email": request.contact_email,
    }
    if request.capacity is not None:
        changes["capacity"] = _to_capacity(request.capacity)
    if request.location is not None:
        changes["location"] = request.location.to_geo_location()

    if apply_partial_update(hospital, changes):
        hospital.touch()
        await hospital.save()

    audit_event(
        AuditAction.UPDATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=hospital.id,
        hospital_id=hospital.id,
        detail="profile updated",
    )
    return hospital


async def update_accreditation(
    hospital_id: PydanticObjectId,
    request: HospitalAccreditationUpdateRequest,
    actor: User,
) -> Hospital:
    """Record a ministry accreditation decision.

    Granting NABH or State Licensed status stamps ``accredited_on`` when the
    hospital does not already carry one, because the stored model refuses an
    accredited hospital with no grant date.
    """
    hospital = await get_or_404(Hospital, hospital_id, "hospital")

    granted = {AccreditationStatus.NABH, AccreditationStatus.STATE_LICENSED}
    if request.accreditation_status in granted and hospital.accredited_on is None:
        hospital.accredited_on = _today()

    changes: dict[str, object] = {
        "accreditation_status": request.accreditation_status,
        "nodal_officer_id": request.nodal_officer_id,
        "nodal_officer_name": request.nodal_officer_name,
    }
    apply_partial_update(hospital, changes)

    if request.accreditation_status is AccreditationStatus.BLACKLISTED:
        hospital.is_active = False
    elif not hospital.is_active:
        hospital.is_active = True

    hospital.touch()
    await hospital.save()

    audit_event(
        AuditAction.UPDATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=hospital.id,
        hospital_id=hospital.id,
        detail=f"accreditation set to {request.accreditation_status}"
        + (f"; {request.remarks}" if request.remarks else ""),
    )
    return hospital


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
class _CityProjection(BaseModel):
    """Only the two fields the city filter needs."""

    state: str
    city: str


def _today() -> date:
    """Return today's date in UTC."""
    return utcnow().date()


def _to_capacity(payload: HospitalCapacityPayload) -> HospitalCapacity:
    """Convert the request payload into the stored value object."""
    return HospitalCapacity(
        total_sanctioned_beds=payload.total_sanctioned_beds,
        icu_beds=payload.icu_beds,
        emergency_beds=payload.emergency_beds,
        ventilators=payload.ventilators,
        oxygen_bulk_capacity_liters=payload.oxygen_bulk_capacity_liters,
        ambulance_count=payload.ambulance_count,
    )


def _directory_query(
    actor: User,
    state: str | None,
    city: str | None,
    zone_code: str | None,
    sector_type: SectorType | None,
    accreditation_status: AccreditationStatus | None,
    search: str | None,
) -> dict[str, object]:
    """Build the MongoDB filter behind both the list and the count."""
    query: dict[str, object] = {}

    scope = hospital_scope_of(actor)
    if scope is not None:
        query["_id"] = scope
    if state:
        query["state"] = state
    if city:
        query["city"] = city
    if zone_code:
        query["zone_code"] = zone_code
    if sector_type is not None:
        query["sector_type"] = sector_type.value
    if accreditation_status is not None:
        query["accreditation_status"] = accreditation_status.value
    if search:
        escaped = _escape_regex(search)
        query["$or"] = [
            {"name": {"$regex": escaped, "$options": "i"}},
            {"license_no": {"$regex": escaped, "$options": "i"}},
        ]
    return query


def _escape_regex(value: str) -> str:
    """Escape a user-supplied search term before it becomes a regex.

    Without this, a citizen typing ``(`` produces an invalid pattern and a 500,
    and a crafted term could force catastrophic backtracking.
    """
    return re.escape(value.strip())


async def _require_known_zone(zone_code: str) -> None:
    """Reject a hospital filed against a zone that was never registered.

    A hospital in an unknown zone has no population denominator, which silently
    removes it from every per-capita outbreak and surge calculation.
    """
    if await Zone.find_one(Zone.zone_code == zone_code) is None:
        msg = (
            f"zone '{zone_code}' is not registered; create the zone first so "
            f"per-capita analytics have a population denominator"
        )
        raise ConflictError(msg)
