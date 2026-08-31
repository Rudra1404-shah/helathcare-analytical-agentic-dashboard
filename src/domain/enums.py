"""Canonical enumerations for the Unified National Health Platform.

Every controlled vocabulary in the platform lives here so that models, schemas,
and the future analytics engine all agree on exactly the same string values.

``StrEnum`` members serialise to plain strings in MongoDB, which keeps stored
documents human-readable and keeps aggregation pipelines simple.
"""

from enum import IntEnum, StrEnum

__all__ = [
    "CLOSED_INVESTIGATION_STATUSES",
    "MEDICAL_STAFF_ROLES",
    "TERMINAL_CASE_STATUSES",
    "AccreditationStatus",
    "ActionTaken",
    "AlertKind",
    "AlertTier",
    "BloodGroup",
    "CaseStatus",
    "ComplaintCategory",
    "DiseaseCategory",
    "EmploymentType",
    "EstimationBasis",
    "EvidenceType",
    "Gender",
    "InventoryCategory",
    "InventoryUnit",
    "InvestigationStatus",
    "PaymentMode",
    "PaymentStatus",
    "SectorType",
    "ShiftType",
    "SignalConfidence",
    "StaffCategory",
    "StaffRole",
    "StaffStatus",
    "TrendDirection",
    "TriageLevel",
    "UserRole",
]


# --------------------------------------------------------------------------- #
# Identity and access
# --------------------------------------------------------------------------- #
class UserRole(StrEnum):
    """Top-level authorisation role attached to every account."""

    GOVT_ADMIN = "GOVT_ADMIN"
    HOSPITAL_ADMIN = "HOSPITAL_ADMIN"
    HOSPITAL_STAFF = "HOSPITAL_STAFF"
    DOCTOR = "DOCTOR"
    CITIZEN = "CITIZEN"


# --------------------------------------------------------------------------- #
# Hospital governance
# --------------------------------------------------------------------------- #
class SectorType(StrEnum):
    """Ownership sector of a hospital."""

    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    TRUST = "TRUST"


class AccreditationStatus(StrEnum):
    """Government accreditation state issued by the Health Ministry."""

    NABH = "NABH"
    STATE_LICENSED = "STATE_LICENSED"
    PENDING = "PENDING"
    BLACKLISTED = "BLACKLISTED"


# --------------------------------------------------------------------------- #
# Workforce
# --------------------------------------------------------------------------- #
class StaffCategory(StrEnum):
    """Discriminator separating admin/support staff from medical support staff."""

    ADMIN_SUPPORT = "ADMIN_SUPPORT"
    MEDICAL = "MEDICAL"


class StaffRole(StrEnum):
    """Concrete job role. Each role belongs to exactly one :class:`StaffCategory`."""

    # --- ADMIN_SUPPORT roles ---
    CLEANER = "CLEANER"
    SECURITY = "SECURITY"
    DRIVER = "DRIVER"
    DESK_ADMIN = "DESK_ADMIN"
    LIFTMAN = "LIFTMAN"
    HELPER = "HELPER"
    ADMIN = "ADMIN"
    ACCOUNTANT = "ACCOUNTANT"

    # --- MEDICAL roles ---
    STAFF_NURSE = "STAFF_NURSE"
    MATRON = "MATRON"
    LAB_ASSISTANT = "LAB_ASSISTANT"
    WARD_BOY = "WARD_BOY"
    COMPOUNDER = "COMPOUNDER"

    @property
    def category(self) -> "StaffCategory":
        """Return the staff category this role belongs to."""
        if self in MEDICAL_STAFF_ROLES:
            return StaffCategory.MEDICAL
        return StaffCategory.ADMIN_SUPPORT


MEDICAL_STAFF_ROLES: frozenset[StaffRole] = frozenset(
    {
        StaffRole.STAFF_NURSE,
        StaffRole.MATRON,
        StaffRole.LAB_ASSISTANT,
        StaffRole.WARD_BOY,
        StaffRole.COMPOUNDER,
    }
)
"""Roles that require a nursing or pharmacy registration number."""


class ShiftType(StrEnum):
    """Working shift assignment."""

    MORNING = "MORNING"
    EVENING = "EVENING"
    NIGHT = "NIGHT"
    GENERAL = "GENERAL"


class StaffStatus(StrEnum):
    """Employment lifecycle state for staff and doctors."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ON_LEAVE = "ON_LEAVE"
    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"


class EmploymentType(StrEnum):
    """Contract type for an onboarded doctor."""

    FULL_TIME = "FULL_TIME"
    VISITING = "VISITING"
    ON_CALL = "ON_CALL"


# --------------------------------------------------------------------------- #
# Patient demographics
# --------------------------------------------------------------------------- #
class Gender(StrEnum):
    """Patient-recorded gender."""

    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"
    UNDISCLOSED = "UNDISCLOSED"


class BloodGroup(StrEnum):
    """ABO/Rh blood group."""

    A_POSITIVE = "A+"
    A_NEGATIVE = "A-"
    B_POSITIVE = "B+"
    B_NEGATIVE = "B-"
    AB_POSITIVE = "AB+"
    AB_NEGATIVE = "AB-"
    O_POSITIVE = "O+"
    O_NEGATIVE = "O-"
    UNKNOWN = "UNKNOWN"


# --------------------------------------------------------------------------- #
# Clinical classification
# --------------------------------------------------------------------------- #
class DiseaseCategory(StrEnum):
    """Broad disease grouping consumed by the outbreak-detection module."""

    INFECTIOUS = "INFECTIOUS"
    CHRONIC = "CHRONIC"
    TRAUMA = "TRAUMA"
    SURGICAL = "SURGICAL"
    PEDIATRIC = "PEDIATRIC"
    MATERNAL = "MATERNAL"


class TriageLevel(IntEnum):
    """Clinical urgency: 1 (most urgent) through 4 (least urgent)."""

    IMMEDIATE = 1
    URGENT = 2
    STANDARD = 3
    NON_URGENT = 4


class CaseStatus(StrEnum):
    """Lifecycle state of a patient encounter."""

    ADMITTED = "ADMITTED"
    ICU = "ICU"
    OBSERVATION = "OBSERVATION"
    DISCHARGED = "DISCHARGED"
    DECEASED = "DECEASED"


TERMINAL_CASE_STATUSES: frozenset[CaseStatus] = frozenset(
    {CaseStatus.DISCHARGED, CaseStatus.DECEASED}
)
"""Statuses that close a case and therefore require discharge details."""


# --------------------------------------------------------------------------- #
# Resources
# --------------------------------------------------------------------------- #
class InventoryCategory(StrEnum):
    """Resource class tracked by the hospital inventory module."""

    GENERAL_BEDS = "GENERAL_BEDS"
    ICU_BEDS = "ICU_BEDS"
    VENTILATORS = "VENTILATORS"
    OXYGEN_CYLINDERS = "OXYGEN_CYLINDERS"
    OXYGEN_LITERS = "OXYGEN_LITERS"
    MEDICINES = "MEDICINES"
    CONSUMABLES = "CONSUMABLES"


class InventoryUnit(StrEnum):
    """Unit of measure for an inventory item."""

    UNITS = "UNITS"
    LITERS = "LITERS"
    PIECES = "PIECES"
    BOXES = "BOXES"
    VIALS = "VIALS"
    STRIPS = "STRIPS"
    KG = "KG"
    ML = "ML"


# --------------------------------------------------------------------------- #
# Billing
# --------------------------------------------------------------------------- #
class PaymentStatus(StrEnum):
    """Settlement state of an invoice."""

    PENDING = "PENDING"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


class PaymentMode(StrEnum):
    """Tender used to settle an invoice."""

    CASH = "CASH"
    CARD = "CARD"
    UPI = "UPI"
    NET_BANKING = "NET_BANKING"
    INSURANCE = "INSURANCE"
    GOVT_SCHEME = "GOVT_SCHEME"


# --------------------------------------------------------------------------- #
# Public grievance
# --------------------------------------------------------------------------- #
class ComplaintCategory(StrEnum):
    """Nature of a citizen grievance."""

    OVERCHARGING = "OVERCHARGING"
    BED_REFUSAL = "BED_REFUSAL"
    NEGLIGENCE = "NEGLIGENCE"
    HYGIENE = "HYGIENE"
    SHORTAGE = "SHORTAGE"
    FALSE_BILLING = "FALSE_BILLING"


class InvestigationStatus(StrEnum):
    """Ministry investigation workflow state."""

    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    INQUIRY_ASSIGNED = "INQUIRY_ASSIGNED"
    ACTION_TAKEN = "ACTION_TAKEN"
    DISMISSED = "DISMISSED"


CLOSED_INVESTIGATION_STATUSES: frozenset[InvestigationStatus] = frozenset(
    {InvestigationStatus.ACTION_TAKEN, InvestigationStatus.DISMISSED}
)
"""Statuses that close a complaint and therefore require closure details."""


class ActionTaken(StrEnum):
    """Enforcement decision recorded against a hospital."""

    WARNING = "WARNING"
    FINE = "FINE"
    LICENSE_SUSPENSION = "LICENSE_SUSPENSION"
    DISMISSED = "DISMISSED"


class EvidenceType(StrEnum):
    """Media type of a mandatory complaint evidence attachment."""

    PHOTO = "PHOTO"
    VIDEO = "VIDEO"


# --------------------------------------------------------------------------- #
# Analytical intelligence
# --------------------------------------------------------------------------- #
class AlertTier(StrEnum):
    """Severity band of a Smart Alert.

    Four tiers rather than a numeric score because an operations desk acts on a
    tier, not on a decimal: CRITICAL is "now", HIGH is "today", MEDIUM is "this
    week", INFO is "worth knowing".
    """

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    INFO = "INFO"


class AlertKind(StrEnum):
    """What an alert is about, so a client can route or group it."""

    BED_CAPACITY = "BED_CAPACITY"
    ICU_CAPACITY = "ICU_CAPACITY"
    STOCK_DEPLETION = "STOCK_DEPLETION"
    OUTBREAK_ANOMALY = "OUTBREAK_ANOMALY"
    WORKFORCE_OVERLOAD = "WORKFORCE_OVERLOAD"
    SURGE_FORECAST = "SURGE_FORECAST"


class TrendDirection(StrEnum):
    """Which way a fitted time series is moving."""

    RISING = "RISING"
    FALLING = "FALLING"
    STABLE = "STABLE"


class SignalConfidence(StrEnum):
    """How much weight an analytical output can carry.

    ``INSUFFICIENT_DATA`` is not an error. A hospital that opened last week has
    no baseline to compare against, and saying so plainly is more useful than a
    confident number derived from four data points.
    """

    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class EstimationBasis(StrEnum):
    """Where a derived figure came from.

    The platform stores current stock levels but no stock-movement ledger, so a
    consumption rate is inferred from case activity rather than measured. Every
    response that carries an inferred number carries this alongside it: an
    estimate presented as a measurement is how a dashboard loses its credibility.
    """

    ESTIMATED_FROM_CASE_DEMAND = "ESTIMATED_FROM_CASE_DEMAND"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
