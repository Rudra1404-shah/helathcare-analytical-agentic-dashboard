"""Populate a development database with synthetic demonstration data.

**Entirely synthetic.** Every name, National ID, licence number, and phone
number here is invented. No real patient, staff, or hospital data belongs in
this file -- see ``CLAUDE.md``, rule 1.

Run with the API's own environment:

    python -m scripts.seed            # add to whatever is already there
    python -m scripts.seed --reset    # drop the database first

The accounts it creates all share the password ``Str0ngPassword!``:

    ministry@health.gov.example.com    GOVT_ADMIN
    admin@sunrise.example.com          HOSPITAL_ADMIN  (Sunrise Multispeciality)
    admin@cityhealth.example.com       HOSPITAL_ADMIN  (City Health District)
    asha.kulkarni@example.com          CITIZEN
"""

import argparse
import asyncio
import logging
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from beanie import PydanticObjectId

from src.core.config import Settings, get_settings
from src.core.security import hash_password
from src.domain.enums import (
    AccreditationStatus,
    BloodGroup,
    CaseStatus,
    ComplaintCategory,
    DiseaseCategory,
    EvidenceType,
    Gender,
    InventoryCategory,
    InventoryUnit,
    SectorType,
    ShiftType,
    StaffRole,
    TriageLevel,
    UserRole,
)
from src.domain.models import (
    Bill,
    BillLineItem,
    CaseType,
    Complaint,
    Department,
    Doctor,
    EvidenceAttachment,
    GeoLocation,
    Hospital,
    HospitalCapacity,
    InventoryItem,
    Patient,
    PatientCase,
    ProtectedNationalId,
    Staff,
    User,
    VitalSigns,
    Zone,
    money,
)
from src.infrastructure.database import mongo

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed")

SEED_PASSWORD = "Str0ngPassword!"
RANDOM = random.Random(20260827)

SYMPTOMS = [
    ["Fever", "Cough"],
    ["Breathlessness", "Chest tightness"],
    ["Abdominal pain", "Vomiting"],
    ["Severe headache", "Photophobia"],
    ["Fracture", "Swelling"],
    ["Dizziness", "Palpitations"],
]

FIRST_NAMES = [
    "Aarav",
    "Priya",
    "Rohan",
    "Sneha",
    "Vikram",
    "Kavita",
    "Arjun",
    "Meera",
    "Farah",
    "Nikhil",
    "Anjali",
    "Rahul",
    "Divya",
    "Sameer",
    "Neha",
    "Imran",
]
LAST_NAMES = [
    "Sharma",
    "Nair",
    "Mehta",
    "Pillai",
    "Joshi",
    "Rao",
    "Iyer",
    "Khan",
    "Deshmukh",
    "Patil",
    "Kulkarni",
    "Bose",
    "Reddy",
    "Gupta",
]


def person() -> str:
    """Return a synthetic full name."""
    return f"{RANDOM.choice(FIRST_NAMES)} {RANDOM.choice(LAST_NAMES)}"


def phone(index: int) -> str:
    """Return a synthetic Indian mobile number."""
    return f"+9198{200_00000 + index:08d}"


async def seed(settings: Settings, reset: bool) -> None:
    """Build the demonstration dataset."""
    await mongo.connect(settings)
    if reset:
        logger.info("Dropping database %s", settings.mongo_db_name)
        await _drop_all()

    ministry = await _account(
        "ministry@health.gov.example.com", UserRole.GOVT_ADMIN, "Dr Anita Deshpande"
    )
    zones = await _zones()
    hospitals = await _hospitals(zones)
    case_types = await _case_types()

    citizen = await _citizen(settings)

    for index, hospital in enumerate(hospitals):
        await _staff_hospital(hospital, index, settings)
        await _inventory(hospital)
        patients = await _patients(hospital, index, citizen, settings)
        await _cases_and_bills(hospital, patients, case_types)

    await _complaints(citizen, hospitals[0], ministry)

    logger.info("")
    logger.info("Seed complete. Sign in with password: %s", SEED_PASSWORD)
    logger.info("  ministry@health.gov.example.com    GOVT_ADMIN")
    for hospital in hospitals:
        logger.info("  %-34s HOSPITAL_ADMIN (%s)", hospital.contact_email, hospital.name)
    logger.info("  asha.kulkarni@example.com          CITIZEN")
    await mongo.disconnect()


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #
async def _drop_all() -> None:
    """Empty every collection without dropping indexes."""
    from src.domain.models import ALL_DOCUMENT_MODELS

    for model in ALL_DOCUMENT_MODELS:
        await model.delete_all()


async def _account(
    email: str,
    role: UserRole,
    full_name: str,
    hospital_id: PydanticObjectId | None = None,
) -> User:
    """Create an account, or return the existing one."""
    existing = await User.find_one(User.email == email)
    if existing is not None:
        return existing

    user = User(
        email=email,
        hashed_password=hash_password(SEED_PASSWORD),
        role=role,
        full_name=full_name,
        hospital_id=hospital_id,
        is_verified=True,
    )
    await user.insert()
    return user


async def _zones() -> list[Zone]:
    """Register the administrative zones the hospitals sit in."""
    definitions = [
        ("MH-MUM-Z12", "Andheri West", "Maharashtra", "Mumbai", 482_000, 19.1197, 72.8464),
        ("MH-MUM-Z07", "Dadar", "Maharashtra", "Mumbai", 356_000, 19.0176, 72.8562),
        ("MH-PUN-Z03", "Kothrud", "Maharashtra", "Pune", 311_000, 18.5074, 73.8077),
        ("KA-BLR-Z09", "Whitefield", "Karnataka", "Bengaluru", 528_000, 12.9698, 77.7500),
    ]
    zones: list[Zone] = []
    for code, name, state, city, population, lat, lon in definitions:
        existing = await Zone.find_one(Zone.zone_code == code)
        if existing is not None:
            zones.append(existing)
            continue
        zone = Zone(
            zone_code=code,
            name=name,
            state=state,
            city=city,
            population_covered=population,
            centroid=GeoLocation.from_lat_lon(lat, lon),
        )
        await zone.insert()
        zones.append(zone)
    logger.info("Zones: %d", len(zones))
    return zones


async def _hospitals(zones: list[Zone]) -> list[Hospital]:
    """Register three hospitals across two sectors and two cities."""
    definitions = [
        (
            "Sunrise Multispeciality",
            "MH-HOSP-10021",
            SectorType.PRIVATE,
            zones[0],
            AccreditationStatus.NABH,
            240,
            34,
            18,
            22,
            "admin@sunrise.example.com",
        ),
        (
            "City Health District Hospital",
            "MH-HOSP-10088",
            SectorType.PUBLIC,
            zones[1],
            AccreditationStatus.STATE_LICENSED,
            420,
            52,
            30,
            40,
            "admin@cityhealth.example.com",
        ),
        (
            "Shanti Trust Hospital",
            "KA-HOSP-20114",
            SectorType.TRUST,
            zones[3],
            AccreditationStatus.PENDING,
            120,
            12,
            8,
            6,
            "admin@shanti.example.com",
        ),
    ]

    hospitals: list[Hospital] = []
    for (
        name,
        licence,
        sector,
        zone,
        accreditation,
        beds,
        icu,
        emergency,
        vents,
        email,
    ) in definitions:
        existing = await Hospital.find_one(Hospital.license_no == licence)
        if existing is not None:
            hospitals.append(existing)
            continue

        hospital = Hospital(
            name=name,
            license_no=licence,
            sector_type=sector,
            state=zone.state,
            city=zone.city,
            zone_code=zone.zone_code,
            ward_area=zone.name,
            location=zone.centroid or GeoLocation.from_lat_lon(19.0, 72.8),
            capacity=HospitalCapacity(
                total_sanctioned_beds=beds,
                icu_beds=icu,
                emergency_beds=emergency,
                ventilators=vents,
                oxygen_bulk_capacity_liters=float(beds * 120),
                ambulance_count=max(2, beds // 60),
            ),
            accreditation_status=accreditation,
            accredited_on=(
                None
                if accreditation is AccreditationStatus.PENDING
                else datetime.now(UTC).date() - timedelta(days=400)
            ),
            nodal_officer_name="Officer " + RANDOM.choice(LAST_NAMES),
            contact_phone=phone(len(hospitals)),
            contact_email=email,
        )
        await hospital.insert()
        await _account(email, UserRole.HOSPITAL_ADMIN, f"Admin {person()}", hospital.id)
        hospitals.append(hospital)

    logger.info("Hospitals: %d", len(hospitals))
    return hospitals


async def _case_types() -> list[CaseType]:
    """Define national standard case types, including notifiable ones."""
    definitions = [
        ("Acute Gastroenteritis", DiseaseCategory.INFECTIOUS, "A09", TriageLevel.STANDARD, True),
        (
            "Community-Acquired Pneumonia",
            DiseaseCategory.INFECTIOUS,
            "J18.9",
            TriageLevel.URGENT,
            True,
        ),
        ("Dengue Fever", DiseaseCategory.INFECTIOUS, "A90", TriageLevel.URGENT, True),
        ("Type 2 Diabetes Mellitus", DiseaseCategory.CHRONIC, "E11", TriageLevel.NON_URGENT, False),
        (
            "Acute Myocardial Infarction",
            DiseaseCategory.CHRONIC,
            "I21",
            TriageLevel.IMMEDIATE,
            False,
        ),
        ("Femoral Fracture", DiseaseCategory.TRAUMA, "S72", TriageLevel.URGENT, False),
        ("Appendicectomy", DiseaseCategory.SURGICAL, "K35", TriageLevel.URGENT, False),
        ("Normal Delivery", DiseaseCategory.MATERNAL, "O80", TriageLevel.STANDARD, False),
    ]
    case_types: list[CaseType] = []
    for name, category, code, triage, notifiable in definitions:
        existing = await CaseType.find_one({"hospital_id": None, "icd10_code": code})
        if existing is not None:
            case_types.append(existing)
            continue
        case_type = CaseType(
            hospital_id=None,
            name=name,
            disease_category=category,
            icd10_code=code,
            triage_level=triage,
            is_notifiable=notifiable,
        )
        await case_type.insert()
        case_types.append(case_type)
    logger.info("Case types: %d", len(case_types))
    return case_types


async def _citizen(settings: Settings) -> User:
    """Create the demonstration citizen, whose PHR spans two hospitals."""
    email = "asha.kulkarni@example.com"
    existing = await User.find_one(User.email == email)
    if existing is not None:
        return existing

    citizen = User(
        email=email,
        hashed_password=hash_password(SEED_PASSWORD),
        role=UserRole.CITIZEN,
        full_name="Asha Kulkarni",
        phone=phone(999),
        national_id=ProtectedNationalId.protect("4321-8765-2109", settings),
        is_verified=True,
    )
    await citizen.insert()
    return citizen


async def _staff_hospital(hospital: Hospital, index: int, settings: Settings) -> None:
    """Register departments, doctors, and staff for one hospital."""
    if await Department.find(Department.hospital_id == hospital.id).count():
        return

    department_specs = [
        ("General Medicine", "GMED", "Internal Medicine"),
        ("Cardiology", "CARD", "Cardiology"),
        ("Emergency", "EMER", "Emergency Medicine"),
        ("Paediatrics", "PAED", "Paediatrics"),
    ]

    for order, (name, code, specialisation) in enumerate(department_specs):
        department = Department(
            hospital_id=_id(hospital),
            name=name,
            code=code,
            floor=str(order + 1),
            wing="East" if order % 2 == 0 else "West",
            bed_count=hospital.capacity.total_sanctioned_beds // len(department_specs),
        )
        await department.insert()

        for seat in range(2):
            doctor = Doctor(
                hospital_id=_id(hospital),
                full_name=f"Dr {person()}",
                license_no=f"MCI-{index}{order}{seat}-{RANDOM.randint(10000, 99999)}",
                specialization=specialisation,
                department_id=_id(department),
                qualification="MBBS, MD",
                phone=phone(index * 100 + order * 10 + seat),
                shifts=[ShiftType.MORNING] if seat == 0 else [ShiftType.EVENING, ShiftType.NIGHT],
                max_daily_patients=RANDOM.choice([25, 30, 40]),
                is_emergency_on_call=(name == "Emergency"),
            )
            await doctor.insert()

    medical_roles = [StaffRole.STAFF_NURSE, StaffRole.MATRON, StaffRole.LAB_ASSISTANT]
    support_roles = [StaffRole.DESK_ADMIN, StaffRole.CLEANER, StaffRole.SECURITY, StaffRole.DRIVER]

    for seat, role in enumerate([*medical_roles, *medical_roles, *support_roles]):
        is_medical = role in medical_roles
        staff = Staff(
            hospital_id=_id(hospital),
            employee_id=f"EMP-{index}-{seat:03d}",
            full_name=person(),
            phone=phone(index * 1000 + seat),
            national_id=ProtectedNationalId.protect(
                f"{RANDOM.randint(1000, 9999)}-{RANDOM.randint(1000, 9999)}-"
                f"{RANDOM.randint(1000, 9999)}",
                settings,
            ),
            staff_category=role.category,
            role=role,
            registration_no=f"MNC-{RANDOM.randint(10000, 99999)}" if is_medical else None,
            shift=RANDOM.choice(list(ShiftType)),
            is_emergency_on_call=is_medical and seat % 3 == 0,
        )
        await staff.insert()


async def _inventory(hospital: Hospital) -> None:
    """Stock the four capacity categories plus medicines and consumables."""
    if await InventoryItem.find(InventoryItem.hospital_id == hospital.id).count():
        return

    capacity = hospital.capacity
    lines: list[tuple[InventoryCategory, str, float, float, float, InventoryUnit]] = [
        (
            InventoryCategory.GENERAL_BEDS,
            "General Ward Bed",
            float(capacity.total_sanctioned_beds - capacity.icu_beds - capacity.emergency_beds),
            0.0,
            8.0,
            InventoryUnit.UNITS,
        ),
        (
            InventoryCategory.ICU_BEDS,
            "ICU Bed",
            float(capacity.icu_beds),
            0.0,
            4.0,
            InventoryUnit.UNITS,
        ),
        (
            InventoryCategory.VENTILATORS,
            "Adult Ventilator",
            float(capacity.ventilators),
            0.0,
            3.0,
            InventoryUnit.UNITS,
        ),
        (
            InventoryCategory.OXYGEN_LITERS,
            "Bulk Medical Oxygen",
            capacity.oxygen_bulk_capacity_liters,
            0.0,
            capacity.oxygen_bulk_capacity_liters * 0.15,
            InventoryUnit.LITERS,
        ),
        (InventoryCategory.MEDICINES, "Paracetamol 500mg", 4000, 0.0, 500, InventoryUnit.STRIPS),
        (InventoryCategory.MEDICINES, "Azithromycin 500mg", 900, 0.0, 200, InventoryUnit.STRIPS),
        (InventoryCategory.CONSUMABLES, "Surgical Gloves", 12000, 0.0, 2000, InventoryUnit.PIECES),
        (InventoryCategory.OXYGEN_CYLINDERS, "D-Type Cylinder", 80, 0.0, 20, InventoryUnit.UNITS),
    ]

    for category, item_name, total, _unused, threshold, unit in lines:
        # Leave a realistic amount already in use, and push one line under its
        # threshold so the alerts view has something to show.
        used_fraction = 0.92 if item_name == "Azithromycin 500mg" else RANDOM.uniform(0.25, 0.7)
        available = round(total * (1 - used_fraction), 2)
        item = InventoryItem(
            hospital_id=_id(hospital),
            category=category,
            item_name=item_name,
            total_stock=total,
            available_stock=available,
            min_safety_threshold=threshold,
            unit=unit,
            last_restocked_at=datetime.now(UTC) - timedelta(days=RANDOM.randint(1, 20)),
        )
        await item.insert()


async def _patients(
    hospital: Hospital,
    index: int,
    citizen: User,
    settings: Settings,
) -> list[Patient]:
    """Register patients, linking two of them to the demonstration citizen."""
    existing = await Patient.find(Patient.hospital_id == hospital.id).to_list()
    if existing:
        return existing

    patients: list[Patient] = []
    for seat in range(14):
        patient = Patient(
            hospital_id=_id(hospital),
            mrn=f"MRN-{index}{seat:04d}",
            full_name=person(),
            gender=RANDOM.choice([Gender.MALE, Gender.FEMALE, Gender.OTHER]),
            age_years=RANDOM.randint(2, 88),
            phone=phone(index * 10_000 + seat),
            blood_group=RANDOM.choice(list(BloodGroup)),
            allergies=RANDOM.choice([[], ["Penicillin"], ["Dust", "Pollen"]]),
            pre_existing_conditions=RANDOM.choice([[], ["Hypertension"], ["Type 2 Diabetes"]]),
        )
        await patient.insert()
        patients.append(patient)

    # The citizen is treated at the first two hospitals, which is what makes
    # the unified health record demonstrable.
    if index < 2:
        linked = Patient(
            hospital_id=_id(hospital),
            mrn=f"MRN-{index}-ASHA",
            citizen_user_id=citizen.id,
            national_id=ProtectedNationalId.protect("4321-8765-2109", settings),
            full_name="Asha Kulkarni",
            gender=Gender.FEMALE,
            age_years=41,
            phone=citizen.phone,
            blood_group=BloodGroup.B_POSITIVE,
            allergies=["Sulfa drugs"] if index == 0 else [],
            pre_existing_conditions=["Hypothyroidism"] if index == 1 else [],
        )
        await linked.insert()
        patients.append(linked)

    return patients


async def _cases_and_bills(
    hospital: Hospital,
    patients: list[Patient],
    case_types: list[CaseType],
) -> None:
    """Open a mix of live and discharged cases, invoicing the closed ones."""
    if await PatientCase.find(PatientCase.hospital_id == hospital.id).count():
        return

    doctors = await Doctor.find(Doctor.hospital_id == hospital.id).to_list()
    departments = await Department.find(Department.hospital_id == hospital.id).to_list()
    if not doctors or not departments:
        return

    for seat, patient in enumerate(patients):
        doctor = RANDOM.choice(doctors)
        case_type = RANDOM.choice(case_types)
        admitted = datetime.now(UTC) - timedelta(
            days=RANDOM.randint(0, 25), hours=RANDOM.randint(0, 23)
        )
        closing = seat % 3 == 0

        status = (
            CaseStatus.DISCHARGED
            if closing
            else RANDOM.choice([CaseStatus.ADMITTED, CaseStatus.ICU, CaseStatus.OBSERVATION])
        )
        discharged = admitted + timedelta(days=RANDOM.randint(1, 6)) if closing else None

        case = PatientCase(
            case_number=f"{hospital.license_no[-5:]}-C{seat:04d}",
            hospital_id=_id(hospital),
            patient_id=_id(patient),
            doctor_id=_id(doctor),
            department_id=_id(RANDOM.choice(departments)),
            case_type_id=case_type.id,
            bed_allocated=f"{'ICU' if status is CaseStatus.ICU else 'GW'}-{RANDOM.randint(1, 60)}",
            triage_level=case_type.triage_level,
            admitted_at=admitted,
            discharged_at=discharged,
            chief_symptoms=RANDOM.choice(SYMPTOMS),
            vitals=_vitals(admitted),
            status=status,
            discharge_summary=(
                f"{case_type.name}. Treated and stabilised. Advised follow-up in one week."
                if closing
                else None
            ),
        )
        await case.insert()

        if closing:
            await _bill(hospital, case, patient, seat)


def _vitals(admitted: datetime) -> list[VitalSigns]:
    """Generate a short observation trend for one case."""
    readings: list[VitalSigns] = []
    for step in range(RANDOM.randint(2, 4)):
        readings.append(
            VitalSigns(
                systolic_bp=RANDOM.randint(105, 158),
                diastolic_bp=RANDOM.randint(62, 95),
                pulse_bpm=RANDOM.randint(58, 118),
                spo2_percent=round(RANDOM.uniform(88.0, 99.0), 1),
                temperature_celsius=round(RANDOM.uniform(36.2, 39.4), 1),
                respiratory_rate=RANDOM.randint(12, 26),
                recorded_at=admitted + timedelta(hours=8 * step),
            )
        )
    return readings


async def _bill(hospital: Hospital, case: PatientCase, patient: Patient, seat: int) -> None:
    """Raise an invoice for a closed case, some settled and some outstanding."""
    nights = RANDOM.randint(1, 6)
    line_items = [
        BillLineItem.build("Ward charges", Decimal("2500.00"), Decimal(nights)),
        BillLineItem.build("Consultation", Decimal("800.00"), Decimal(RANDOM.randint(1, 3))),
        BillLineItem.build("Pharmacy", Decimal("142.50"), Decimal(RANDOM.randint(2, 9))),
        BillLineItem.build("Diagnostics", Decimal("1150.00"), Decimal(RANDOM.randint(1, 2))),
    ]
    subtotal = money(sum((item.total for item in line_items), Decimal("0")))
    tax = money(subtotal * Decimal("0.05"))
    discount = money(subtotal * Decimal("0.02")) if seat % 4 == 0 else Decimal("0.00")
    grand_total = money(subtotal + tax - discount)

    from src.domain.enums import PaymentMode, PaymentStatus

    settled = seat % 2 == 0
    partial = not settled and seat % 3 == 0
    paid = grand_total if settled else (money(grand_total / 2) if partial else Decimal("0.00"))

    bill = Bill(
        invoice_no=f"{hospital.license_no[-5:]}-INV{seat:04d}",
        hospital_id=_id(hospital),
        case_id=_id(case),
        patient_id=_id(patient),
        line_items=line_items,
        subtotal=subtotal,
        tax_amount=tax,
        discount_amount=discount,
        grand_total=grand_total,
        amount_paid=paid,
        payment_status=(
            PaymentStatus.PAID
            if settled
            else (PaymentStatus.PARTIALLY_PAID if partial else PaymentStatus.PENDING)
        ),
        payment_mode=RANDOM.choice(list(PaymentMode)) if paid > 0 else None,
        issued_at=case.discharged_at or datetime.now(UTC),
        settled_at=case.discharged_at if settled else None,
    )
    await bill.insert()


async def _complaints(citizen: User, hospital: Hospital, ministry: User) -> None:
    """File grievances across the investigation workflow's states."""
    if await Complaint.find(Complaint.citizen_user_id == citizen.id).count():
        return

    from src.domain.enums import ActionTaken, InvestigationStatus

    definitions: list[tuple[ComplaintCategory, str, InvestigationStatus]] = [
        (
            ComplaintCategory.OVERCHARGING,
            "I was charged for an ICU bed for three days although my father was in "
            "the general ward the whole time. The final invoice does not match the "
            "treatment actually given, and the billing desk refused to explain it.",
            InvestigationStatus.SUBMITTED,
        ),
        (
            ComplaintCategory.HYGIENE,
            "The general ward toilets were flooded for the entire two days of my "
            "stay and were not cleaned once. Several patients on the same floor "
            "raised it with the nursing station and nothing was done.",
            InvestigationStatus.UNDER_REVIEW,
        ),
        (
            ComplaintCategory.BED_REFUSAL,
            "My mother was refused admission at the emergency desk even though the "
            "public bed availability page showed four free general beds at the time. "
            "We had to travel another eleven kilometres to a different hospital.",
            InvestigationStatus.ACTION_TAKEN,
        ),
    ]

    for seat, (category, description, status) in enumerate(definitions):
        closed = status is InvestigationStatus.ACTION_TAKEN
        complaint = Complaint(
            complaint_number=f"CMP-20260801-{seat:04d}A",
            citizen_user_id=_id(citizen),
            hospital_id=_id(hospital),
            incident_at=datetime.now(UTC) - timedelta(days=RANDOM.randint(3, 40)),
            category=category,
            description=description,
            evidence=[
                EvidenceAttachment(
                    url=f"https://placehold.co/800x600/png?text=Evidence+{seat + 1}",
                    evidence_type=EvidenceType.PHOTO,
                    content_type="image/png",
                    file_name=f"evidence-{seat + 1}.png",
                    size_bytes=48_120,
                )
            ],
            investigation_status=status,
            assigned_officer_id=ministry.id
            if status is not InvestigationStatus.SUBMITTED
            else None,
            hospital_explanation=(
                "Bed availability feed was stale at the time of the incident." if closed else None
            ),
            action_taken=ActionTaken.WARNING if closed else None,
            closure_remarks=(
                "Refusal confirmed. Formal warning issued and the availability feed "
                "moved to a five-minute refresh."
                if closed
                else None
            ),
            closed_at=datetime.now(UTC) - timedelta(days=2) if closed else None,
        )
        await complaint.insert()


def _id(document: Any) -> PydanticObjectId:
    """Return a persisted document's id, or fail loudly."""
    if document.id is None:
        msg = f"{type(document).__name__} was never persisted and has no id"
        raise RuntimeError(msg)
    identifier: PydanticObjectId = document.id
    return identifier


def main() -> None:
    """Parse arguments and run the seeder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Empty every collection before seeding.",
    )
    arguments = parser.parse_args()

    settings = get_settings()
    logger.info("Seeding %s at %s", settings.mongo_db_name, settings.mongo_uri)
    asyncio.run(seed(settings, arguments.reset))


if __name__ == "__main__":
    main()
