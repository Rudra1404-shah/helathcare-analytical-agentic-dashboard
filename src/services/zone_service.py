"""Zone and area management for the Health Ministry portal.

Zones exist as their own collection because ``population_covered`` is the
denominator the outbreak-detection and surge-forecasting modules divide by. A
zone stored as a loose string on a hospital would make per-capita rates
impossible to compute.
"""

from beanie import PydanticObjectId
from pydantic import ValidationError

from src.core.audit import AuditAction, audit_event
from src.domain.models import Hospital, User, Zone
from src.domain.schemas.govt import ZoneCreateRequest, ZoneUpdateRequest
from src.services.common import (
    apply_partial_update,
    get_or_404,
    guard_duplicate,
    translate_validation_error,
)

__all__ = ["count_zones", "create_zone", "get_zone", "list_zones", "update_zone"]

_COLLECTION = "zones"


async def create_zone(request: ZoneCreateRequest, actor: User) -> Zone:
    """Register an administrative zone.

    Raises:
        ConflictError: If the zone code is already in use.
    """
    try:
        zone = Zone(
            zone_code=request.zone_code,
            name=request.name,
            state=request.state,
            city=request.city,
            population_covered=request.population_covered,
            centroid=request.centroid.to_geo_location() if request.centroid else None,
        )
    except ValidationError as exc:
        raise translate_validation_error(exc) from exc

    await guard_duplicate(
        zone.insert,
        f"zone code {request.zone_code} is already registered",
    )
    audit_event(
        AuditAction.CREATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=zone.id,
    )
    return zone


async def get_zone(zone_id: PydanticObjectId) -> Zone:
    """Fetch one zone.

    Raises:
        NotFoundError: If no such zone exists.
    """
    return await get_or_404(Zone, zone_id, "zone")


async def list_zones(
    state: str | None = None,
    city: str | None = None,
    is_active: bool | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Zone]:
    """Return zones, optionally narrowed to a state, city, or active state."""
    query = _zone_query(state, city, is_active)
    return await Zone.find(query).sort("+zone_code").skip(skip).limit(limit).to_list()


async def count_zones(
    state: str | None = None,
    city: str | None = None,
    is_active: bool | None = None,
) -> int:
    """Return how many zones match the same filters."""
    return await Zone.find(_zone_query(state, city, is_active)).count()


async def update_zone(
    zone_id: PydanticObjectId,
    request: ZoneUpdateRequest,
    actor: User,
) -> Zone:
    """Apply a partial update. The zone code is immutable once registered."""
    zone = await get_or_404(Zone, zone_id, "zone")

    changes: dict[str, object] = {
        "name": request.name,
        "population_covered": request.population_covered,
        "is_active": request.is_active,
    }
    if request.centroid is not None:
        changes["centroid"] = request.centroid.to_geo_location()

    if apply_partial_update(zone, changes):
        zone.touch()
        await zone.save()

    audit_event(
        AuditAction.UPDATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=zone.id,
    )
    return zone


async def count_hospitals_in_zone(zone_code: str) -> int:
    """Return how many hospitals sit inside a zone.

    The ministry portal shows this next to each zone so an official can see at
    a glance whether a densely populated ward is under-served.
    """
    return await Hospital.find(Hospital.zone_code == zone_code).count()


def _zone_query(state: str | None, city: str | None, is_active: bool | None) -> dict[str, object]:
    """Build the MongoDB filter shared by the list and count queries."""
    query: dict[str, object] = {}
    if state:
        query["state"] = state
    if city:
        query["city"] = city
    if is_active is not None:
        query["is_active"] = is_active
    return query
