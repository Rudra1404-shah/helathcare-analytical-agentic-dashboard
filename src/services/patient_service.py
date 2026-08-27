"""Patient registration, search, and bulk import.

A patient record is hospital-local; the *person* is national. The link between
the two is the National ID lookup hash, computed here on write and never stored
in plaintext. When a patient arrives with a National ID that already resolves to
a citizen account, the record is linked to that account automatically -- which
is what makes the record appear in that citizen's PHR without anyone filing
paperwork.
"""

import re

from beanie import PydanticObjectId
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from src.core.audit import AuditAction, audit_event
from src.core.config import Settings, get_settings
from src.core.security import national_id_lookup_hash
from src.domain.enums import Gender, UserRole
from src.domain.models import EmergencyContact, Patient, ProtectedNationalId, User
from src.domain.schemas.patient import (
    BulkUploadReport,
    BulkUploadRowError,
    PatientBulkUploadRow,
    PatientIntakeRequest,
    PatientUpdateRequest,
)
from src.services import bulk_upload
from src.services.common import (
    apply_partial_update,
    ensure_hospital_match,
    get_or_404,
    guard_duplicate,
    hospital_scope_of,
    translate_validation_error,
)

__all__ = [
    "bulk_import_patients",
    "count_patients",
    "find_by_national_id",
    "get_patient",
    "intake_patient",
    "list_patients",
    "update_patient",
]

_COLLECTION = "patients"


async def intake_patient(
    hospital_id: PydanticObjectId,
    request: PatientIntakeRequest,
    actor: User,
    settings: Settings | None = None,
) -> Patient:
    """Register a patient from the manual intake form.

    Raises:
        ConflictError: If the MRN is already used at this hospital.
    """
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "patient")
    active = settings or get_settings()

    protected = (
        ProtectedNationalId.protect(request.national_id, active) if request.national_id else None
    )
    citizen_user_id = request.citizen_user_id
    if citizen_user_id is None and protected is not None:
        citizen_user_id = await _resolve_citizen(protected.lookup_hash)

    try:
        patient = Patient(
            hospital_id=hospital_id,
            mrn=request.mrn,
            citizen_user_id=citizen_user_id,
            national_id=protected,
            full_name=request.full_name,
            gender=request.gender,
            date_of_birth=request.date_of_birth,
            age_years=request.age_years,
            phone=request.phone,
            blood_group=request.blood_group,
            emergency_contact=request.emergency_contact,
            allergies=list(request.allergies),
            pre_existing_conditions=list(request.pre_existing_conditions),
            medical_history_files=list(request.medical_history_files),
        )
    except ValidationError as exc:
        raise translate_validation_error(exc) from exc

    await guard_duplicate(
        patient.insert,
        f"MRN {request.mrn} is already registered at this hospital",
    )
    audit_event(
        AuditAction.CREATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=patient.id,
        hospital_id=hospital_id,
    )
    return patient


async def get_patient(patient_id: PydanticObjectId, actor: User) -> Patient:
    """Fetch one patient, enforcing hospital scope and emitting a read event."""
    patient = await get_or_404(Patient, patient_id, "patient")
    ensure_hospital_match(patient.hospital_id, hospital_scope_of(actor), "patient")

    audit_event(
        AuditAction.READ,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=patient.id,
        hospital_id=patient.hospital_id,
    )
    return patient


async def list_patients(
    hospital_id: PydanticObjectId,
    actor: User,
    search: str | None = None,
    gender: Gender | None = None,
    is_active: bool | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Patient]:
    """Return a hospital's patient register."""
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "patient")
    query = _patient_query(hospital_id, search, gender, is_active)

    patients = await Patient.find(query).sort("-created_at").skip(skip).limit(limit).to_list()
    audit_event(
        AuditAction.READ,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        hospital_id=hospital_id,
        detail=f"listed {len(patients)} patients",
    )
    return patients


async def count_patients(
    hospital_id: PydanticObjectId,
    actor: User,
    search: str | None = None,
    gender: Gender | None = None,
    is_active: bool | None = None,
) -> int:
    """Return how many patients match the same filters."""
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "patient")
    return await Patient.find(_patient_query(hospital_id, search, gender, is_active)).count()


async def update_patient(
    patient_id: PydanticObjectId,
    request: PatientUpdateRequest,
    actor: User,
) -> Patient:
    """Apply a partial update. The MRN and National ID are immutable."""
    patient = await get_or_404(Patient, patient_id, "patient")
    ensure_hospital_match(patient.hospital_id, hospital_scope_of(actor), "patient")

    changes: dict[str, object] = {
        "full_name": request.full_name,
        "phone": request.phone,
        "blood_group": request.blood_group,
        "emergency_contact": request.emergency_contact,
        "allergies": request.allergies,
        "pre_existing_conditions": request.pre_existing_conditions,
        "is_active": request.is_active,
    }
    if apply_partial_update(patient, changes):
        patient.touch()
        await patient.save()

    audit_event(
        AuditAction.UPDATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=patient.id,
        hospital_id=patient.hospital_id,
    )
    return patient


async def bulk_import_patients(
    hospital_id: PydanticObjectId,
    content: bytes,
    filename: str,
    actor: User,
    settings: Settings | None = None,
) -> BulkUploadReport:
    """Import an ``.xlsx``/``.csv`` patient file, row by row.

    A row that parses but collides with an existing MRN is reported as a
    rejection rather than aborting the import, so a re-uploaded file with a few
    already-imported rows still adds the new ones.

    Returns:
        A report reconciling accepted and rejected rows against the file total.
    """
    ensure_hospital_match(hospital_id, hospital_scope_of(actor), "patient")
    active = settings or get_settings()

    parsed = bulk_upload.parse_upload(content, filename)
    errors = list(parsed.errors)
    accepted = 0

    for row in parsed.rows:
        try:
            await _insert_bulk_row(hospital_id, row, active)
        except Exception as exc:  # one bad row must not abort the whole import
            errors.append(_row_rejection(row, exc))
        else:
            accepted += 1

    audit_event(
        AuditAction.CREATE,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        hospital_id=hospital_id,
        detail=f"bulk import: {accepted} accepted, {len(errors)} rejected from {filename}",
    )
    return BulkUploadReport(
        total_rows=parsed.total_rows,
        accepted=accepted,
        rejected=len(errors),
        errors=errors,
    )


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
async def _insert_bulk_row(
    hospital_id: PydanticObjectId,
    row: PatientBulkUploadRow,
    settings: Settings,
) -> Patient:
    """Turn one validated upload row into a stored patient."""
    protected = ProtectedNationalId.protect(row.national_id, settings) if row.national_id else None
    citizen_user_id = await _resolve_citizen(protected.lookup_hash) if protected else None

    emergency_contact = None
    if row.emergency_contact_name and row.emergency_contact_phone:
        emergency_contact = EmergencyContact(
            name=row.emergency_contact_name,
            phone=row.emergency_contact_phone,
            relationship=row.emergency_contact_relationship or "Not stated",
        )

    patient = Patient(
        hospital_id=hospital_id,
        mrn=row.mrn,
        citizen_user_id=citizen_user_id,
        national_id=protected,
        full_name=row.full_name,
        gender=row.gender,
        date_of_birth=row.date_of_birth,
        age_years=row.age_years,
        phone=row.phone,
        blood_group=row.blood_group,
        emergency_contact=emergency_contact,
        allergies=row.split_allergies(),
        pre_existing_conditions=row.split_conditions(),
    )
    await patient.insert()
    return patient


def _row_rejection(row: PatientBulkUploadRow, exc: Exception) -> BulkUploadRowError:
    """Describe why a parsed row could not be stored."""
    message: str
    field: str | None
    if isinstance(exc, DuplicateKeyError):
        message = f"MRN {row.mrn} is already registered at this hospital"
        field = "mrn"
    elif isinstance(exc, ValidationError):
        first = exc.errors()[0]
        message = first["msg"]
        field = ".".join(str(part) for part in first["loc"]) or None
    else:
        message = str(exc)
        field = None
    return BulkUploadRowError(row_number=row.row_number, field=field, message=message)


async def _resolve_citizen(lookup_hash: str) -> PydanticObjectId | None:
    """Find the citizen account this National ID belongs to, if any."""
    citizen = await User.find_one(
        {"national_id.lookup_hash": lookup_hash, "role": UserRole.CITIZEN.value}
    )
    return citizen.id if citizen else None


def _patient_query(
    hospital_id: PydanticObjectId,
    search: str | None,
    gender: Gender | None,
    is_active: bool | None,
) -> dict[str, object]:
    """Build the register filter shared by the list and count queries."""
    query: dict[str, object] = {"hospital_id": hospital_id}
    if gender is not None:
        query["gender"] = gender.value
    if is_active is not None:
        query["is_active"] = is_active
    if search:
        escaped = re.escape(search.strip())
        query["$or"] = [
            {"full_name": {"$regex": escaped, "$options": "i"}},
            {"mrn": {"$regex": escaped, "$options": "i"}},
            {"phone": {"$regex": escaped, "$options": "i"}},
        ]
    return query


async def find_by_national_id(
    national_id: str,
    settings: Settings | None = None,
) -> list[Patient]:
    """Return every hospital-local record for one person.

    This is the cross-hospital identity resolution the unified health record is
    built on: the deterministic lookup hash matches regardless of whether the
    ID was typed as ``1234-5678-9012``, ``1234 5678 9012``, or ``123456789012``.
    """
    active = settings or get_settings()
    lookup = national_id_lookup_hash(national_id, active)
    return await Patient.find({"national_id.lookup_hash": lookup}).to_list()
