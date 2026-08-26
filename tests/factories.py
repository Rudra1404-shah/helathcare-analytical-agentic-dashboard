"""Builders for valid test documents.

Each helper returns a *valid* instance with sensible defaults; tests override
only the one field under examination. This keeps a test about, say, bed counts
from breaking when an unrelated required field is added.

All data here is synthetic. No real patient, staff, or hospital data appears in
this repository, per the Zero-PHI rule in CLAUDE.md.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from beanie import PydanticObjectId

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
    StaffCategory,
    StaffRole,
    TriageLevel,
    UserRole,
)
from src.domain.models.base import GeoLocation
from src.domain.models.bill import Bill, BillLineItem
from src.domain.models.case_type import CaseType
from src.domain.models.complaint import Complaint, EvidenceAttachment
from src.domain.models.department import Department
from src.domain.models.doctor import Doctor
from src.domain.models.hospital import Hospital, HospitalCapacity
from src.domain.models.inventory import InventoryItem
from src.domain.models.patient import Patient
from src.domain.models.patient_case import PatientCase, VitalSigns
from src.domain.models.staff import Staff
from src.domain.models.user import User
from src.domain.models.zone import Zone

VALID_PASSWORD = "TestPassw0rd!"
PAST_INCIDENT = datetime.now(UTC) - timedelta(days=3)


def object_id() -> PydanticObjectId:
    """Return a fresh ObjectId."""
    return PydanticObjectId()


# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #
def build_user(**overrides: Any) -> User:
    """Build a valid citizen user."""
    data: dict[str, Any] = {
        "email": "citizen@example.com",
        "hashed_password": hash_password(VALID_PASSWORD),
        "role": UserRole.CITIZEN,
        "full_name": "Test Citizen",
    }
    data.update(overrides)
    return User(**data)


def build_hospital_user(**overrides: Any) -> User:
    """Build a valid hospital admin user."""
    data: dict[str, Any] = {
        "email": "admin@hospital.example.com",
        "hashed_password": hash_password(VALID_PASSWORD),
        "role": UserRole.HOSPITAL_ADMIN,
        "full_name": "Test Hospital Admin",
        "hospital_id": object_id(),
    }
    data.update(overrides)
    return User(**data)


# --------------------------------------------------------------------------- #
# Governance
# --------------------------------------------------------------------------- #
def build_zone(**overrides: Any) -> Zone:
    """Build a valid zone."""
    data: dict[str, Any] = {
        "zone_code": "MH-MUM-Z12",
        "name": "Andheri West",
        "state": "Maharashtra",
        "city": "Mumbai",
        "population_covered": 250_000,
    }
    data.update(overrides)
    return Zone(**data)


def build_capacity(**overrides: Any) -> HospitalCapacity:
    """Build a valid hospital capacity block."""
    data: dict[str, Any] = {
        "total_sanctioned_beds": 200,
        "icu_beds": 40,
        "emergency_beds": 20,
        "ventilators": 25,
        "oxygen_bulk_capacity_liters": 10_000.0,
        "ambulance_count": 6,
    }
    data.update(overrides)
    return HospitalCapacity(**data)


def build_hospital(**overrides: Any) -> Hospital:
    """Build a valid hospital."""
    data: dict[str, Any] = {
        "name": "Test General Hospital",
        "license_no": "MH-LIC-00123",
        "sector_type": SectorType.PUBLIC,
        "state": "Maharashtra",
        "city": "Mumbai",
        "zone_code": "MH-MUM-Z12",
        "location": GeoLocation.from_lat_lon(latitude=19.0760, longitude=72.8777),
        "capacity": build_capacity(),
        "accreditation_status": AccreditationStatus.PENDING,
    }
    data.update(overrides)
    return Hospital(**data)


def build_department(**overrides: Any) -> Department:
    """Build a valid department."""
    data: dict[str, Any] = {
        "hospital_id": object_id(),
        "name": "Cardiology",
        "code": "CARD",
        "bed_count": 30,
    }
    data.update(overrides)
    return Department(**data)


# --------------------------------------------------------------------------- #
# Workforce
# --------------------------------------------------------------------------- #
def build_support_staff(**overrides: Any) -> Staff:
    """Build a valid admin/support staff member."""
    data: dict[str, Any] = {
        "hospital_id": object_id(),
        "employee_id": "EMP-1001",
        "full_name": "Test Cleaner",
        "phone": "+919876543210",
        "staff_category": StaffCategory.ADMIN_SUPPORT,
        "role": StaffRole.CLEANER,
        "shift": ShiftType.MORNING,
    }
    data.update(overrides)
    return Staff(**data)


def build_medical_staff(**overrides: Any) -> Staff:
    """Build a valid medical staff member."""
    data: dict[str, Any] = {
        "hospital_id": object_id(),
        "employee_id": "EMP-2001",
        "full_name": "Test Nurse",
        "phone": "+919876543211",
        "staff_category": StaffCategory.MEDICAL,
        "role": StaffRole.STAFF_NURSE,
        "registration_no": "NUR-55512",
        "shift": ShiftType.NIGHT,
    }
    data.update(overrides)
    return Staff(**data)


def build_doctor(**overrides: Any) -> Doctor:
    """Build a valid doctor."""
    data: dict[str, Any] = {
        "hospital_id": object_id(),
        "full_name": "Test Doctor",
        "license_no": "MCI-778899",
        "specialization": "Cardiology",
        "department_id": object_id(),
        "qualification": "MBBS, MD (Medicine)",
        "shifts": [ShiftType.MORNING],
        "max_daily_patients": 40,
    }
    data.update(overrides)
    return Doctor(**data)


# --------------------------------------------------------------------------- #
# Clinical
# --------------------------------------------------------------------------- #
def build_patient(**overrides: Any) -> Patient:
    """Build a valid patient."""
    data: dict[str, Any] = {
        "hospital_id": object_id(),
        "mrn": "MRN-000123",
        "full_name": "Test Patient",
        "gender": Gender.FEMALE,
        "age_years": 34,
        "blood_group": BloodGroup.O_POSITIVE,
    }
    data.update(overrides)
    return Patient(**data)


def build_case_type(**overrides: Any) -> CaseType:
    """Build a valid case type."""
    data: dict[str, Any] = {
        "name": "Acute Gastroenteritis",
        "disease_category": DiseaseCategory.INFECTIOUS,
        "icd10_code": "A09",
        "triage_level": TriageLevel.URGENT,
        "is_notifiable": True,
    }
    data.update(overrides)
    return CaseType(**data)


def build_vitals(**overrides: Any) -> VitalSigns:
    """Build a valid set of vitals."""
    data: dict[str, Any] = {
        "systolic_bp": 120,
        "diastolic_bp": 80,
        "pulse_bpm": 72,
        "spo2_percent": 98.0,
        "temperature_celsius": 36.8,
    }
    data.update(overrides)
    return VitalSigns(**data)


def build_patient_case(**overrides: Any) -> PatientCase:
    """Build a valid open patient case."""
    data: dict[str, Any] = {
        "case_number": "CASE-0001",
        "hospital_id": object_id(),
        "patient_id": object_id(),
        "doctor_id": object_id(),
        "department_id": object_id(),
        "chief_symptoms": ["fever", "dehydration"],
        "status": CaseStatus.ADMITTED,
    }
    data.update(overrides)
    return PatientCase(**data)


# --------------------------------------------------------------------------- #
# Resources and billing
# --------------------------------------------------------------------------- #
def build_inventory_item(**overrides: Any) -> InventoryItem:
    """Build a valid inventory line."""
    data: dict[str, Any] = {
        "hospital_id": object_id(),
        "category": InventoryCategory.ICU_BEDS,
        "item_name": "ICU Bed",
        "total_stock": 40.0,
        "available_stock": 12.0,
        "min_safety_threshold": 5.0,
        "unit": InventoryUnit.UNITS,
    }
    data.update(overrides)
    return InventoryItem(**data)


def build_line_item(
    description: str = "Consultation",
    rate: str = "500.00",
    quantity: str = "2",
) -> BillLineItem:
    """Build a line item with a correctly computed total."""
    return BillLineItem.build(description=description, rate=rate, quantity=quantity)


def build_bill(**overrides: Any) -> Bill:
    """Build a valid bill with one consistent line item."""
    line = build_line_item()
    data: dict[str, Any] = {
        "invoice_no": "INV-0001",
        "hospital_id": object_id(),
        "case_id": object_id(),
        "patient_id": object_id(),
        "line_items": [line],
        "subtotal": Decimal("1000.00"),
        "tax_amount": Decimal("180.00"),
        "discount_amount": Decimal("100.00"),
        "grand_total": Decimal("1080.00"),
    }
    data.update(overrides)
    return Bill(**data)


# --------------------------------------------------------------------------- #
# Grievance
# --------------------------------------------------------------------------- #
def build_evidence(**overrides: Any) -> EvidenceAttachment:
    """Build a valid photo evidence attachment."""
    data: dict[str, Any] = {
        "url": "https://storage.example.test/evidence/photo-1.jpg",
        "evidence_type": EvidenceType.PHOTO,
        "content_type": "image/jpeg",
        "file_name": "photo-1.jpg",
        "size_bytes": 204_800,
    }
    data.update(overrides)
    return EvidenceAttachment(**data)


VALID_COMPLAINT_DESCRIPTION = (
    "The hospital refused to admit the patient despite an available ICU bed "
    "being visible on the public dashboard at the time of arrival."
)


def build_complaint(**overrides: Any) -> Complaint:
    """Build a valid complaint carrying one evidence attachment."""
    data: dict[str, Any] = {
        "complaint_number": "CMP-0001",
        "citizen_user_id": object_id(),
        "hospital_id": object_id(),
        "incident_at": PAST_INCIDENT,
        "category": ComplaintCategory.BED_REFUSAL,
        "description": VALID_COMPLAINT_DESCRIPTION,
        "evidence": [build_evidence()],
    }
    data.update(overrides)
    return Complaint(**data)
