"""Cross-hospital Personal Health Record assembly.

This is the payoff of the National ID lookup hash. A citizen treated at a
public hospital in one state and a private one in another has two disconnected
``patients`` documents; both carry the same deterministic hash, so both resolve
to one person here and their encounters merge into a single timeline.

Two resolution paths are used together: the lookup hash, and any patient record
a hospital explicitly linked to the citizen account. Either alone would miss
records -- a walk-in with no National ID recorded is only reachable through the
explicit link, and a record created before the citizen registered is only
reachable through the hash.
"""

from datetime import UTC, date, datetime, time
from typing import TypeVar

from beanie import Document, PydanticObjectId

from src.core.audit import AuditAction, audit_event
from src.core.errors import PermissionDeniedError
from src.domain.enums import BloodGroup, Gender, UserRole
from src.domain.models import (
    Bill,
    CaseType,
    Department,
    Doctor,
    Hospital,
    Patient,
    PatientCase,
    User,
)
from src.domain.models.base import utcnow
from src.domain.schemas.phr import (
    PersonalHealthRecordResponse,
    PhrBillSummary,
    PhrCaseEntry,
    PhrExportRequest,
    PhrHospitalSummary,
)

__all__ = ["assemble_health_record", "linked_patient_records"]

LookupT = TypeVar("LookupT", bound=Document)

_COLLECTION = "patient_cases"


async def linked_patient_records(citizen: User) -> list[Patient]:
    """Return every hospital-local patient record belonging to one citizen.

    Matches on the explicit account link *or* the National ID lookup hash, so a
    record created before the citizen registered is still found.
    """
    clauses: list[dict[str, object]] = [{"citizen_user_id": citizen.id}]
    if citizen.national_id is not None:
        clauses.append({"national_id.lookup_hash": citizen.national_id.lookup_hash})

    return await Patient.find({"$or": clauses}).to_list()


async def assemble_health_record(
    citizen: User,
    actor: User,
    options: PhrExportRequest | None = None,
) -> PersonalHealthRecordResponse:
    """Build a citizen's complete health record across every hospital.

    Args:
        citizen: Whose record to assemble.
        actor: Who is asking. A citizen may only read their own record; the
            ministry may read any.
        options: Which sections to include and an optional date window.

    Returns:
        The unified record, encounters newest first.

    Raises:
        PermissionDeniedError: If the actor may not read this record.
    """
    _authorise(citizen, actor)
    settings = options or PhrExportRequest()

    records = await linked_patient_records(citizen)
    if not records:
        return _empty_record(citizen)

    patient_ids = [record.id for record in records if record.id is not None]
    cases = await _load_cases(patient_ids, settings)
    entries = await _build_entries(cases, settings)

    audit_event(
        AuditAction.EXPORT if options is not None else AuditAction.READ,
        _COLLECTION,
        actor_id=actor.id,
        actor_role=actor.role,
        document_id=citizen.id,
        detail=f"PHR assembled: {len(entries)} encounter(s) across {len(records)} record(s)",
    )

    primary = _most_complete(records)
    return PersonalHealthRecordResponse(
        citizen_user_id=_require_id(citizen),
        full_name=citizen.full_name,
        gender=primary.gender,
        date_of_birth=primary.date_of_birth,
        age_years=primary.effective_age_years,
        blood_group=primary.blood_group,
        allergies=sorted({item for record in records for item in record.allergies}),
        pre_existing_conditions=sorted(
            {item for record in records for item in record.pre_existing_conditions}
        ),
        medical_history_files=[
            document for record in records for document in record.medical_history_files
        ],
        linked_patient_ids=patient_ids,
        cases=entries,
        generated_at=utcnow(),
    )


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
def _authorise(citizen: User, actor: User) -> None:
    """Refuse a health record the actor has no standing to read."""
    if actor.role is UserRole.GOVT_ADMIN:
        return
    if actor.id == citizen.id:
        return
    msg = "a health record may only be read by the citizen it belongs to, or by the ministry"
    raise PermissionDeniedError(msg)


def _empty_record(citizen: User) -> PersonalHealthRecordResponse:
    """Build the record of a citizen no hospital has treated yet."""
    return PersonalHealthRecordResponse(
        citizen_user_id=_require_id(citizen),
        full_name=citizen.full_name,
        gender=Gender.UNDISCLOSED,
        blood_group=BloodGroup.UNKNOWN,
        linked_patient_ids=[],
        cases=[],
        generated_at=utcnow(),
    )


def _most_complete(records: list[Patient]) -> Patient:
    """Pick the record carrying the most demographic detail.

    Hospitals capture different amounts at intake; the fullest record is the
    best single source for the header of the unified view.
    """
    return max(records, key=_completeness_score)


def _completeness_score(record: Patient) -> tuple[int, float]:
    """Score a record by how many optional demographics it carries."""
    filled = sum(
        1
        for value in (
            record.date_of_birth,
            record.age_years,
            record.phone,
            record.emergency_contact,
        )
        if value is not None
    )
    filled += len(record.allergies) + len(record.pre_existing_conditions)
    return filled, record.updated_at.timestamp()


async def _load_cases(
    patient_ids: list[PydanticObjectId],
    options: PhrExportRequest,
) -> list[PatientCase]:
    """Fetch every encounter for these records, honouring the date window."""
    query: dict[str, object] = {"patient_id": {"$in": patient_ids}}

    window: dict[str, object] = {}
    if options.from_date is not None:
        window["$gte"] = _start_of_day(options.from_date)
    if options.to_date is not None:
        window["$lte"] = _end_of_day(options.to_date)
    if window:
        query["admitted_at"] = window

    return await PatientCase.find(query).sort("-admitted_at").to_list()


async def _build_entries(
    cases: list[PatientCase],
    options: PhrExportRequest,
) -> list[PhrCaseEntry]:
    """Turn raw cases into timeline entries with their context resolved.

    Every lookup table is fetched once and indexed, rather than per case. A
    citizen with forty encounters across six hospitals would otherwise trigger
    well over a hundred round trips to render one page.
    """
    hospitals = await _index(Hospital, {case.hospital_id for case in cases})
    departments = await _index(Department, {case.department_id for case in cases})
    doctors = await _index(Doctor, {case.doctor_id for case in cases})
    case_types = await _index(
        CaseType, {case.case_type_id for case in cases if case.case_type_id is not None}
    )
    bills = await _bills_by_case(cases) if options.include_bills else {}

    entries: list[PhrCaseEntry] = []
    for case in cases:
        if case.id is None:
            continue
        hospital = hospitals.get(case.hospital_id)
        if hospital is None or hospital.id is None:
            continue

        department = departments.get(case.department_id)
        doctor = doctors.get(case.doctor_id)
        case_type = case_types.get(case.case_type_id) if case.case_type_id else None

        entries.append(
            PhrCaseEntry(
                case_id=case.id,
                case_number=case.case_number,
                hospital=PhrHospitalSummary(
                    hospital_id=hospital.id,
                    name=hospital.name,
                    city=hospital.city,
                    state=hospital.state,
                ),
                department_name=department.name if department else None,
                doctor_name=doctor.full_name if doctor else None,
                case_type_name=case_type.name if case_type else None,
                admitted_at=case.admitted_at,
                discharged_at=case.discharged_at,
                status=case.status,
                chief_symptoms=list(case.chief_symptoms),
                vitals=list(case.vitals) if options.include_vitals else [],
                prescriptions=list(case.prescriptions) if options.include_prescriptions else [],
                discharge_summary=case.discharge_summary,
                bill=bills.get(case.id),
            )
        )
    return entries


async def _bills_by_case(cases: list[PatientCase]) -> dict[PydanticObjectId, PhrBillSummary]:
    """Index one invoice summary per case."""
    case_ids = [case.id for case in cases if case.id is not None]
    if not case_ids:
        return {}

    invoices = await Bill.find({"case_id": {"$in": case_ids}}).sort("-issued_at").to_list()
    summaries: dict[PydanticObjectId, PhrBillSummary] = {}
    for invoice in invoices:
        summaries.setdefault(
            invoice.case_id,
            PhrBillSummary(
                invoice_no=invoice.invoice_no,
                grand_total=invoice.grand_total,
                amount_paid=invoice.amount_paid,
                payment_status=invoice.payment_status,
                issued_at=invoice.issued_at,
            ),
        )
    return summaries


async def _index(
    model: type[LookupT],
    ids: set[PydanticObjectId],
) -> dict[PydanticObjectId, LookupT]:
    """Fetch a set of documents in one query and index them by id."""
    if not ids:
        return {}
    documents = await model.find({"_id": {"$in": list(ids)}}).to_list()
    return {document.id: document for document in documents if document.id is not None}


def _require_id(user: User) -> PydanticObjectId:
    """Return a persisted account's id, or fail loudly."""
    if user.id is None:
        msg = "cannot assemble a health record for an account that has not been saved"
        raise PermissionDeniedError(msg)
    return user.id


def _start_of_day(day: date) -> datetime:
    """Return midnight UTC at the start of a date."""
    return datetime.combine(day, time.min, tzinfo=UTC)


def _end_of_day(day: date) -> datetime:
    """Return the last instant of a date in UTC.

    The window is inclusive of the end date, so a citizen asking for
    "up to 31 March" sees an admission recorded at 23:50 that evening.
    """
    return datetime.combine(day, time.max, tzinfo=UTC)
