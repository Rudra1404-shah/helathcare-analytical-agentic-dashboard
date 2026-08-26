"""Beanie document models for the Unified National Health Platform.

:data:`ALL_DOCUMENT_MODELS` is the single registry passed to ``init_beanie``.
A model that is not in this list is not registered, and every operation on it
fails at runtime -- so new collections must be added here.
"""

from beanie import Document

from src.domain.models.base import (
    Address,
    GeoLocation,
    ProtectedNationalId,
    TimestampedDocument,
    ValueObject,
    utcnow,
)
from src.domain.models.bill import Bill, BillLineItem, money
from src.domain.models.case_type import CaseType
from src.domain.models.complaint import Complaint, EvidenceAttachment
from src.domain.models.department import Department
from src.domain.models.doctor import Doctor
from src.domain.models.hospital import Hospital, HospitalCapacity
from src.domain.models.inventory import InventoryItem
from src.domain.models.patient import EmergencyContact, MedicalDocument, Patient
from src.domain.models.patient_case import PatientCase, Prescription, VitalSigns
from src.domain.models.staff import Staff
from src.domain.models.user import User
from src.domain.models.zone import Zone

__all__ = [
    "ALL_DOCUMENT_MODELS",
    "Address",
    "Bill",
    "BillLineItem",
    "CaseType",
    "Complaint",
    "Department",
    "Doctor",
    "EmergencyContact",
    "EvidenceAttachment",
    "GeoLocation",
    "Hospital",
    "HospitalCapacity",
    "InventoryItem",
    "MedicalDocument",
    "Patient",
    "PatientCase",
    "Prescription",
    "ProtectedNationalId",
    "Staff",
    "TimestampedDocument",
    "User",
    "ValueObject",
    "VitalSigns",
    "Zone",
    "money",
    "utcnow",
]

ALL_DOCUMENT_MODELS: list[type[Document]] = [
    User,
    Zone,
    Hospital,
    Department,
    Staff,
    Doctor,
    Patient,
    CaseType,
    PatientCase,
    InventoryItem,
    Bill,
    Complaint,
]
"""Every collection registered with Beanie, in dependency order."""
