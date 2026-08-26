"""Remaining form schemas: hospital, department, staff, doctor, case, inventory, bill.

These cover the API-boundary rules that mirror -- or add to -- the stored model
constraints, plus the shared "an update must change something" guard.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.domain.enums import (
    AccreditationStatus,
    CaseStatus,
    SectorType,
    ShiftType,
    StaffRole,
    TriageLevel,
)
from src.domain.schemas.bill import BillCreateRequest, BillLineItemRequest
from src.domain.schemas.case_type import CaseTypeUpdateRequest
from src.domain.schemas.department import DepartmentUpdateRequest
from src.domain.schemas.doctor import DoctorOnboardingRequest, DoctorUpdateRequest
from src.domain.schemas.govt import ZoneCreateRequest, ZoneUpdateRequest
from src.domain.schemas.hospital import (
    GeoPointPayload,
    HospitalCapacityPayload,
    HospitalCreateRequest,
    HospitalProfileUpdateRequest,
)
from src.domain.schemas.inventory import (
    InventoryItemCreateRequest,
    InventoryItemUpdateRequest,
    InventoryStockAdjustmentRequest,
)
from src.domain.schemas.patient_case import (
    CaseAdmissionRequest,
    CaseDischargeRequest,
    CaseStatusUpdateRequest,
    VitalSignsRequest,
)
from src.domain.schemas.staff import (
    AdminSupportStaffIntakeRequest,
    MedicalStaffIntakeRequest,
)
from tests import factories


class TestGeoPointPayload:
    """Human-ordered coordinates convert to GeoJSON order."""

    def test_conversion_flips_the_order(self) -> None:
        """A form supplies lat/lon; MongoDB stores lon/lat."""
        point = GeoPointPayload(latitude=19.076, longitude=72.8777).to_geo_location()
        assert point.coordinates == (72.8777, 19.076)

    def test_out_of_range_latitude_is_rejected(self) -> None:
        """Bounds are enforced at the API boundary too."""
        with pytest.raises(ValidationError):
            GeoPointPayload(latitude=95.0, longitude=0.0)


class TestHospitalForms:
    """Hospital registration and profile update."""

    def _valid_create(self, **overrides: object) -> HospitalCreateRequest:
        data: dict[str, object] = {
            "name": "Test General Hospital",
            "license_no": "MH-LIC-1",
            "sector_type": SectorType.PRIVATE,
            "state": "Maharashtra",
            "city": "Mumbai",
            "zone_code": "MH-MUM-Z12",
            "location": GeoPointPayload(latitude=19.076, longitude=72.8777),
            "capacity": HospitalCapacityPayload(
                total_sanctioned_beds=100, icu_beds=20, emergency_beds=10
            ),
        }
        data.update(overrides)
        return HospitalCreateRequest(**data)  # type: ignore[arg-type]

    def test_valid_registration_is_accepted(self) -> None:
        """A complete registration passes."""
        assert self._valid_create().license_no == "MH-LIC-1"

    def test_capacity_overflow_is_rejected_at_the_boundary(self) -> None:
        """The API rejects impossible capacity before it reaches the model."""
        with pytest.raises(ValidationError, match="cannot exceed"):
            HospitalCapacityPayload(total_sanctioned_beds=50, icu_beds=40, emergency_beds=20)

    def test_accredited_registration_requires_a_date(self) -> None:
        """Accreditation must record when it was granted."""
        with pytest.raises(ValidationError, match="accredited_on is required"):
            self._valid_create(accreditation_status=AccreditationStatus.NABH)

    def test_profile_update_rejects_licence_changes(self) -> None:
        """Hospital admins must not be able to edit their own licence number."""
        assert "license_no" not in HospitalProfileUpdateRequest.model_fields
        assert "accreditation_status" not in HospitalProfileUpdateRequest.model_fields

    def test_empty_profile_update_is_rejected(self) -> None:
        """An update that changes nothing is a client bug."""
        with pytest.raises(ValidationError, match="at least one field"):
            HospitalProfileUpdateRequest()


class TestZoneForms:
    """Zone management."""

    def test_valid_zone_creation_is_accepted(self) -> None:
        """A complete zone form passes."""
        request = ZoneCreateRequest(
            zone_code="MH-MUM-Z12",
            name="Andheri West",
            state="Maharashtra",
            city="Mumbai",
            population_covered=250_000,
        )
        assert request.population_covered == 250_000

    def test_negative_population_is_rejected(self) -> None:
        """A negative denominator would corrupt per-capita analytics."""
        with pytest.raises(ValidationError):
            ZoneCreateRequest(
                zone_code="Z1",
                name="Zone",
                state="S",
                city="C",
                population_covered=-1,
            )

    def test_zone_code_is_immutable_on_update(self) -> None:
        """The code identifies the zone and must not change."""
        assert "zone_code" not in ZoneUpdateRequest.model_fields

    def test_empty_zone_update_is_rejected(self) -> None:
        """An update must change something."""
        with pytest.raises(ValidationError, match="at least one field"):
            ZoneUpdateRequest()


class TestStaffIntakeForms:
    """The two intake forms accept disjoint role sets."""

    def test_support_form_accepts_a_support_role(self) -> None:
        """A cleaner belongs on the admin/support form."""
        request = AdminSupportStaffIntakeRequest(
            full_name="Test Cleaner",
            employee_id="EMP-1",
            phone="+919876543210",
            role=StaffRole.CLEANER,
        )
        assert request.role is StaffRole.CLEANER

    def test_support_form_rejects_a_medical_role(self) -> None:
        """A nurse filed on the support form would skew clinical staffing."""
        with pytest.raises(ValidationError, match="cannot be filed"):
            AdminSupportStaffIntakeRequest(
                full_name="Test Nurse",
                employee_id="EMP-2",
                phone="+919876543210",
                role=StaffRole.STAFF_NURSE,
            )

    def test_medical_form_accepts_a_medical_role(self) -> None:
        """A nurse with a registration number passes."""
        request = MedicalStaffIntakeRequest(
            full_name="Test Nurse",
            employee_id="EMP-3",
            phone="+919876543210",
            role=StaffRole.STAFF_NURSE,
            registration_no="NUR-1",
        )
        assert request.registration_no == "NUR-1"

    def test_medical_form_rejects_a_support_role(self) -> None:
        """A driver does not belong on the medical form."""
        with pytest.raises(ValidationError, match="cannot be filed"):
            MedicalStaffIntakeRequest(
                full_name="Test Driver",
                employee_id="EMP-4",
                phone="+919876543210",
                role=StaffRole.DRIVER,
                registration_no="REG-1",
            )

    def test_medical_form_requires_a_registration_number(self) -> None:
        """Registration is mandatory on the medical intake form."""
        with pytest.raises(ValidationError):
            MedicalStaffIntakeRequest(  # type: ignore[call-arg]
                full_name="Test Nurse",
                employee_id="EMP-5",
                phone="+919876543210",
                role=StaffRole.STAFF_NURSE,
            )


class TestDoctorForms:
    """Doctor onboarding."""

    def test_valid_onboarding_is_accepted(self) -> None:
        """A complete onboarding form passes."""
        request = DoctorOnboardingRequest(
            full_name="Test Doctor",
            license_no="MCI-1",
            specialization="Cardiology",
            department_id=factories.object_id(),
            qualification="MBBS",
        )
        assert request.max_daily_patients > 0

    def test_duplicate_shifts_are_rejected(self) -> None:
        """A duplicated shift would double-count availability."""
        with pytest.raises(ValidationError, match="duplicates"):
            DoctorOnboardingRequest(
                full_name="Test Doctor",
                license_no="MCI-2",
                specialization="Cardiology",
                department_id=factories.object_id(),
                qualification="MBBS",
                shifts=[ShiftType.MORNING, ShiftType.MORNING],
            )

    def test_licence_is_immutable_on_update(self) -> None:
        """A doctor's council licence must not be editable."""
        assert "license_no" not in DoctorUpdateRequest.model_fields

    def test_empty_doctor_update_is_rejected(self) -> None:
        """An update must change something."""
        with pytest.raises(ValidationError, match="at least one field"):
            DoctorUpdateRequest()


class TestCaseForms:
    """Admission, status change, and discharge."""

    def _admission(self, **overrides: object) -> CaseAdmissionRequest:
        data: dict[str, object] = {
            "case_number": "CASE-1",
            "patient_id": factories.object_id(),
            "doctor_id": factories.object_id(),
            "department_id": factories.object_id(),
            "chief_symptoms": ["fever"],
        }
        data.update(overrides)
        return CaseAdmissionRequest(**data)  # type: ignore[arg-type]

    def test_valid_admission_is_accepted(self) -> None:
        """A complete admission passes."""
        assert self._admission().status is CaseStatus.ADMITTED

    def test_admission_without_symptoms_is_rejected(self) -> None:
        """A case with no presenting complaint cannot be triaged."""
        with pytest.raises(ValidationError):
            self._admission(chief_symptoms=[])

    @pytest.mark.parametrize("status", [CaseStatus.DISCHARGED, CaseStatus.DECEASED])
    def test_admission_with_terminal_status_is_rejected(self, status: CaseStatus) -> None:
        """A case cannot be opened already closed."""
        with pytest.raises(ValidationError, match="cannot be admitted"):
            self._admission(status=status)

    @pytest.mark.parametrize("status", [CaseStatus.DISCHARGED, CaseStatus.DECEASED])
    def test_status_update_cannot_close_a_case(self, status: CaseStatus) -> None:
        """Closing must go through the discharge form, which demands a summary.

        Without this, a case could be closed without any clinical outcome.
        """
        with pytest.raises(ValidationError, match="discharge form"):
            CaseStatusUpdateRequest(status=status)

    def test_status_update_to_icu_is_accepted(self) -> None:
        """Escalation between open states is allowed."""
        assert CaseStatusUpdateRequest(status=CaseStatus.ICU).status is CaseStatus.ICU

    def test_discharge_requires_a_terminal_status(self) -> None:
        """The discharge form only accepts closing statuses."""
        with pytest.raises(ValidationError, match="requires status"):
            CaseDischargeRequest(status=CaseStatus.ADMITTED, discharge_summary="Summary.")

    def test_valid_discharge_is_accepted(self) -> None:
        """A complete discharge passes."""
        request = CaseDischargeRequest(
            status=CaseStatus.DISCHARGED,
            discharged_at=datetime.now(UTC),
            discharge_summary="Recovered fully.",
        )
        assert request.status is CaseStatus.DISCHARGED

    def test_discharge_without_summary_is_rejected(self) -> None:
        """A summary is mandatory on discharge."""
        with pytest.raises(ValidationError):
            CaseDischargeRequest(status=CaseStatus.DISCHARGED)  # type: ignore[call-arg]

    def test_inverted_blood_pressure_is_rejected(self) -> None:
        """The vitals rule is enforced at the API boundary too."""
        with pytest.raises(ValidationError, match="must be greater than"):
            VitalSignsRequest(
                systolic_bp=70,
                diastolic_bp=110,
                pulse_bpm=70,
                spo2_percent=98.0,
                temperature_celsius=36.8,
            )

    def test_triage_level_out_of_range_is_rejected(self) -> None:
        """Only levels 1-4 exist."""
        with pytest.raises(ValidationError):
            self._admission(triage_level=9)

    def test_valid_triage_level_is_accepted(self) -> None:
        """Level 1 is the most urgent."""
        request = self._admission(triage_level=TriageLevel.IMMEDIATE)
        assert request.triage_level is TriageLevel.IMMEDIATE


class TestInventoryForms:
    """Inventory creation, update, and stock adjustment."""

    def test_valid_item_is_accepted(self) -> None:
        """A consistent inventory line passes."""
        request = InventoryItemCreateRequest(
            category="ICU_BEDS",  # type: ignore[arg-type]
            item_name="ICU Bed",
            total_stock=40.0,
            available_stock=12.0,
        )
        assert request.available_stock == 12.0

    def test_available_exceeding_total_is_rejected(self) -> None:
        """The stock invariant is enforced at the boundary."""
        with pytest.raises(ValidationError, match="cannot exceed"):
            InventoryItemCreateRequest(
                category="ICU_BEDS",  # type: ignore[arg-type]
                item_name="ICU Bed",
                total_stock=10.0,
                available_stock=20.0,
            )

    def test_partial_update_checks_the_invariant_when_both_supplied(self) -> None:
        """Supplying both quantities together must still reconcile."""
        with pytest.raises(ValidationError, match="cannot exceed"):
            InventoryItemUpdateRequest(total_stock=5.0, available_stock=10.0)

    def test_partial_update_of_one_quantity_is_accepted(self) -> None:
        """Updating only the threshold is valid."""
        assert InventoryItemUpdateRequest(min_safety_threshold=3.0) is not None

    def test_empty_inventory_update_is_rejected(self) -> None:
        """An update must change something."""
        with pytest.raises(ValidationError, match="at least one field"):
            InventoryItemUpdateRequest()

    def test_zero_stock_adjustment_is_rejected(self) -> None:
        """A no-op adjustment is almost always a client bug."""
        with pytest.raises(ValidationError, match="non-zero"):
            InventoryStockAdjustmentRequest(delta=0, reason="none")

    @pytest.mark.parametrize("delta", [-1.0, 1.0, -5.5])
    def test_non_zero_adjustments_are_accepted(self, delta: float) -> None:
        """Consuming and releasing stock are both valid."""
        request = InventoryStockAdjustmentRequest(delta=delta, reason="bed allocated")
        assert request.delta == delta


class TestBillForms:
    """Billing totals are computed server-side, never supplied."""

    def test_line_total_is_computed(self) -> None:
        """The client supplies rate and quantity; the server multiplies."""
        item = BillLineItemRequest(
            description="X-Ray", rate=Decimal("750.00"), quantity=Decimal("2")
        )
        assert item.computed_total == Decimal("1500.00")

    def test_client_cannot_supply_a_line_total(self) -> None:
        """Accepting a client total would make overcharging indistinguishable from a bug."""
        assert "total" not in BillLineItemRequest.model_fields

    def test_bill_totals_are_derived(self) -> None:
        """Subtotal and grand total follow from the line items."""
        request = BillCreateRequest(
            invoice_no="INV-1",
            case_id=factories.object_id(),
            patient_id=factories.object_id(),
            line_items=[
                BillLineItemRequest(
                    description="Consultation",
                    rate=Decimal("500.00"),
                    quantity=Decimal("2"),
                )
            ],
            tax_amount=Decimal("180.00"),
            discount_amount=Decimal("100.00"),
        )
        assert request.computed_subtotal == Decimal("1000.00")
        assert request.computed_grand_total == Decimal("1080.00")

    def test_discount_exceeding_subtotal_is_rejected(self) -> None:
        """A discount larger than the charge would produce a negative invoice."""
        with pytest.raises(ValidationError, match="cannot exceed"):
            BillCreateRequest(
                invoice_no="INV-2",
                case_id=factories.object_id(),
                patient_id=factories.object_id(),
                line_items=[
                    BillLineItemRequest(
                        description="Consultation",
                        rate=Decimal("100.00"),
                        quantity=Decimal("1"),
                    )
                ],
                discount_amount=Decimal("500.00"),
            )

    def test_bill_without_line_items_is_rejected(self) -> None:
        """An invoice must charge for at least one thing."""
        with pytest.raises(ValidationError):
            BillCreateRequest(
                invoice_no="INV-3",
                case_id=factories.object_id(),
                patient_id=factories.object_id(),
                line_items=[],
            )


class TestUpdateGuards:
    """Every partial-update schema refuses a no-op."""

    @pytest.mark.parametrize(
        "schema",
        [
            DepartmentUpdateRequest,
            CaseTypeUpdateRequest,
            ZoneUpdateRequest,
            DoctorUpdateRequest,
            InventoryItemUpdateRequest,
            HospitalProfileUpdateRequest,
        ],
        ids=lambda s: s.__name__,
    )
    def test_empty_update_is_rejected(self, schema: type) -> None:
        """A request that changes nothing indicates a client bug."""
        with pytest.raises(ValidationError, match="at least one field"):
            schema()


class TestTimezoneHandling:
    """Timestamps carry timezone information."""

    def test_past_incident_uses_aware_datetime(self) -> None:
        """Naive datetimes would make cross-region analytics ambiguous."""
        assert factories.PAST_INCIDENT.tzinfo is not None

    def test_admission_accepts_an_aware_datetime(self) -> None:
        """An explicit admission time is preserved."""
        moment = datetime.now(UTC) - timedelta(hours=2)
        request = CaseAdmissionRequest(
            case_number="CASE-2",
            patient_id=factories.object_id(),
            doctor_id=factories.object_id(),
            department_id=factories.object_id(),
            chief_symptoms=["cough"],
            admitted_at=moment,
        )
        assert request.admitted_at == moment
