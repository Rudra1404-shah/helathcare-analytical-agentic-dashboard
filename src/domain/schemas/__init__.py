"""Pydantic v2 request and response schemas for every platform form.

One module per form group, mirroring the three portals:

* Government -- :mod:`.govt` (zones, accreditation, complaint investigation)
* Hospital -- :mod:`.hospital`, :mod:`.department`, :mod:`.staff`,
  :mod:`.doctor`, :mod:`.patient`, :mod:`.case_type`, :mod:`.patient_case`,
  :mod:`.inventory`, :mod:`.bill`
* Citizen -- :mod:`.auth`, :mod:`.complaint`, :mod:`.phr`
"""

from src.domain.schemas.auth import (
    CitizenRegistrationRequest,
    GovtLoginRequest,
    LoginRequest,
    PasswordChangeRequest,
    TokenResponse,
    UserCreateRequest,
    UserResponse,
)
from src.domain.schemas.bill import (
    BillCreateRequest,
    BillLineItemRequest,
    BillResponse,
    PaymentRecordRequest,
)
from src.domain.schemas.case_type import (
    CaseTypeCreateRequest,
    CaseTypeResponse,
    CaseTypeUpdateRequest,
)
from src.domain.schemas.common import (
    ApiResponse,
    IdentifiedResponse,
    PageMeta,
    PaginatedResponse,
    RequestSchema,
    ResponseSchema,
)
from src.domain.schemas.complaint import (
    ComplaintResponse,
    ComplaintSubmissionRequest,
    EvidenceAttachmentRequest,
)
from src.domain.schemas.department import (
    DepartmentCreateRequest,
    DepartmentResponse,
    DepartmentUpdateRequest,
)
from src.domain.schemas.doctor import (
    DoctorOnboardingRequest,
    DoctorResponse,
    DoctorUpdateRequest,
)
from src.domain.schemas.govt import (
    ComplaintInvestigationUpdateRequest,
    HospitalAccreditationUpdateRequest,
    ZoneCreateRequest,
    ZoneResponse,
    ZoneUpdateRequest,
)
from src.domain.schemas.hospital import (
    GeoPointPayload,
    HospitalCapacityPayload,
    HospitalCreateRequest,
    HospitalProfileUpdateRequest,
    HospitalResponse,
)
from src.domain.schemas.inventory import (
    InventoryItemCreateRequest,
    InventoryItemResponse,
    InventoryItemUpdateRequest,
    InventoryStockAdjustmentRequest,
    LowStockAlertResponse,
)
from src.domain.schemas.patient import (
    BulkUploadReport,
    BulkUploadRowError,
    PatientBulkUploadRow,
    PatientIntakeRequest,
    PatientResponse,
    PatientUpdateRequest,
)
from src.domain.schemas.patient_case import (
    CaseAdmissionRequest,
    CaseDischargeRequest,
    CaseStatusUpdateRequest,
    PatientCaseResponse,
    PrescriptionRequest,
    VitalSignsRequest,
)
from src.domain.schemas.phr import (
    PersonalHealthRecordResponse,
    PhrBillSummary,
    PhrCaseEntry,
    PhrExportRequest,
    PhrHospitalSummary,
)
from src.domain.schemas.staff import (
    AdminSupportStaffIntakeRequest,
    MedicalStaffIntakeRequest,
    StaffResponse,
    StaffUpdateRequest,
)

__all__ = [
    "AdminSupportStaffIntakeRequest",
    "ApiResponse",
    "BillCreateRequest",
    "BillLineItemRequest",
    "BillResponse",
    "BulkUploadReport",
    "BulkUploadRowError",
    "CaseAdmissionRequest",
    "CaseDischargeRequest",
    "CaseStatusUpdateRequest",
    "CaseTypeCreateRequest",
    "CaseTypeResponse",
    "CaseTypeUpdateRequest",
    "CitizenRegistrationRequest",
    "ComplaintInvestigationUpdateRequest",
    "ComplaintResponse",
    "ComplaintSubmissionRequest",
    "DepartmentCreateRequest",
    "DepartmentResponse",
    "DepartmentUpdateRequest",
    "DoctorOnboardingRequest",
    "DoctorResponse",
    "DoctorUpdateRequest",
    "EvidenceAttachmentRequest",
    "GeoPointPayload",
    "GovtLoginRequest",
    "HospitalAccreditationUpdateRequest",
    "HospitalCapacityPayload",
    "HospitalCreateRequest",
    "HospitalProfileUpdateRequest",
    "HospitalResponse",
    "IdentifiedResponse",
    "InventoryItemCreateRequest",
    "InventoryItemResponse",
    "InventoryItemUpdateRequest",
    "InventoryStockAdjustmentRequest",
    "LoginRequest",
    "LowStockAlertResponse",
    "MedicalStaffIntakeRequest",
    "PageMeta",
    "PaginatedResponse",
    "PasswordChangeRequest",
    "PatientBulkUploadRow",
    "PatientCaseResponse",
    "PatientIntakeRequest",
    "PatientResponse",
    "PatientUpdateRequest",
    "PaymentRecordRequest",
    "PersonalHealthRecordResponse",
    "PhrBillSummary",
    "PhrCaseEntry",
    "PhrExportRequest",
    "PhrHospitalSummary",
    "PrescriptionRequest",
    "RequestSchema",
    "ResponseSchema",
    "StaffResponse",
    "StaffUpdateRequest",
    "TokenResponse",
    "UserCreateRequest",
    "UserResponse",
    "VitalSignsRequest",
    "ZoneCreateRequest",
    "ZoneResponse",
    "ZoneUpdateRequest",
]
