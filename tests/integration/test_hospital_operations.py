"""Hospital operational modules: workforce, patients, cases, inventory, billing.

The tests follow one patient end to end -- registered, admitted onto a real
bed, given vitals and a prescription, discharged, invoiced, and paid -- because
that is the path where the modules actually interact. Bed inventory moving in
step with case state is only observable across that whole journey.
"""

from typing import Any

import pytest
from httpx import AsyncClient

from tests.integration.conftest import auth
from tests.integration.world import World, created, payload

pytestmark = pytest.mark.integration


class TestWorkforce:
    """Department registration and the two staff intake forms."""

    async def test_medical_staff_intake_requires_registration_number(
        self, client: AsyncClient, world: World
    ) -> None:
        """A nurse without a nursing registration number cannot be filed."""
        # Act
        response = await client.post(
            f"/api/v1/hospitals/{world.hospital_id}/staff/medical",
            headers=auth(world.admin_token),
            json={
                "full_name": "Nurse Without Papers",
                "employee_id": "EMP-NOPAPERS",
                "phone": "+919820000001",
                "role": "STAFF_NURSE",
            },
        )

        # Assert
        assert response.status_code == 422

    async def test_medical_role_rejected_on_the_admin_support_form(
        self, client: AsyncClient, world: World
    ) -> None:
        """A Staff Nurse filed as support staff would distort clinical counts."""
        # Act
        response = await client.post(
            f"/api/v1/hospitals/{world.hospital_id}/staff/admin-support",
            headers=auth(world.admin_token),
            json={
                "full_name": "Misfiled Nurse",
                "employee_id": "EMP-MISFILED",
                "phone": "+919820000002",
                "role": "STAFF_NURSE",
            },
        )

        # Assert
        assert response.status_code == 422
        assert "cannot be filed" in response.json()["error"]

    async def test_staff_intake_and_roster_filtering(
        self, client: AsyncClient, world: World
    ) -> None:
        """Both intake forms land in one roster, filterable by shift."""
        # Arrange
        nurse = created(
            await client.post(
                f"/api/v1/hospitals/{world.hospital_id}/staff/medical",
                headers=auth(world.admin_token),
                json={
                    "full_name": "Sister Fatima Sheikh",
                    "employee_id": "EMP-N001",
                    "phone": "+919820000003",
                    "role": "STAFF_NURSE",
                    "registration_no": "MNC-44821",
                    "department_id": world.department_id,
                    "shift": "NIGHT",
                    "is_emergency_on_call": True,
                },
            )
        )
        await client.post(
            f"/api/v1/hospitals/{world.hospital_id}/staff/admin-support",
            headers=auth(world.admin_token),
            json={
                "full_name": "Ramesh Patil",
                "employee_id": "EMP-A001",
                "phone": "+919820000004",
                "role": "DESK_ADMIN",
                "shift": "MORNING",
            },
        )

        # Act
        night = payload(
            await client.get(
                f"/api/v1/hospitals/{world.hospital_id}/staff",
                headers=auth(world.admin_token),
                params={"shift": "NIGHT"},
            )
        )

        # Assert
        assert nurse["staff_category"] == "MEDICAL"
        assert [member["employee_id"] for member in night["items"]] == ["EMP-N001"]

    async def test_staff_response_never_carries_a_national_id(
        self, client: AsyncClient, world: World
    ) -> None:
        """A National ID supplied at intake is stored protected and never returned."""
        # Act
        staff = created(
            await client.post(
                f"/api/v1/hospitals/{world.hospital_id}/staff/admin-support",
                headers=auth(world.admin_token),
                json={
                    "full_name": "Sunita Deshmukh",
                    "employee_id": "EMP-A002",
                    "phone": "+919820000005",
                    "national_id": "1111-2222-3333",
                    "role": "ACCOUNTANT",
                },
            )
        )

        # Assert -- the id is excluded because a random ObjectId hex can happen
        # to contain the digits being searched for.
        body = {key: value for key, value in staff.items() if key != "_id"}
        assert "national_id" not in body
        assert "1111" not in str(body)

    async def test_hierarchy_groups_clinical_roles_first(
        self, client: AsyncClient, world: World
    ) -> None:
        """The roster reads top-down as a clinical chain of command."""
        # Act
        hierarchy = payload(
            await client.get(
                f"/api/v1/hospitals/{world.hospital_id}/staff/hierarchy",
                headers=auth(world.admin_token),
            )
        )

        # Assert
        roles = list(hierarchy)
        assert "STAFF_NURSE" in roles
        assert roles.index("STAFF_NURSE") < roles.index("DESK_ADMIN")

    async def test_duplicate_employee_id_within_a_hospital_is_refused(
        self, client: AsyncClient, world: World
    ) -> None:
        """Employee IDs are unique per hospital, enforced by a compound index."""
        # Act
        response = await client.post(
            f"/api/v1/hospitals/{world.hospital_id}/staff/admin-support",
            headers=auth(world.admin_token),
            json={
                "full_name": "Duplicate Person",
                "employee_id": "EMP-A001",
                "phone": "+919820000006",
                "role": "HELPER",
            },
        )

        # Assert
        assert response.status_code == 409

    async def test_same_employee_id_is_allowed_at_another_hospital(
        self, client: AsyncClient, rival: World
    ) -> None:
        """Uniqueness is hospital-scoped, not platform-wide."""
        # Act
        response = await client.post(
            f"/api/v1/hospitals/{rival.hospital_id}/staff/admin-support",
            headers=auth(rival.admin_token),
            json={
                "full_name": "Different Person Same Badge",
                "employee_id": "EMP-A001",
                "phone": "+919820000007",
                "role": "SECURITY",
            },
        )

        # Assert
        assert response.status_code == 201

    async def test_doctor_licence_is_unique_across_the_platform(
        self, client: AsyncClient, rival: World, world: World
    ) -> None:
        """A medical council licence belongs to one person nationally."""
        # Act
        response = await client.post(
            f"/api/v1/hospitals/{rival.hospital_id}/doctors",
            headers=auth(rival.admin_token),
            json={
                "full_name": "Impersonator",
                "license_no": "MCI-00001",
                "specialization": "Cardiology",
                "department_id": rival.department_id,
                "qualification": "MBBS",
            },
        )

        # Assert
        assert response.status_code == 409

    async def test_doctor_cannot_be_assigned_another_hospitals_department(
        self, client: AsyncClient, world: World, rival: World
    ) -> None:
        """Cross-hospital references would corrupt departmental staffing counts."""
        # Act
        response = await client.post(
            f"/api/v1/hospitals/{world.hospital_id}/doctors",
            headers=auth(world.admin_token),
            json={
                "full_name": "Dr Wrong Department",
                "license_no": "MCI-90210",
                "specialization": "Neurology",
                "department_id": rival.department_id,
                "qualification": "MBBS, DM",
            },
        )

        # Assert
        assert response.status_code == 409


class TestPatientAndCaseJourney:
    """One patient, from intake through discharge and settlement."""

    async def test_patient_intake_succeeds(self, client: AsyncClient, world: World) -> None:
        """A patient is registered with a hospital-scoped MRN."""
        # Act
        response = await client.post(
            f"/api/v1/hospitals/{world.hospital_id}/patients",
            headers=auth(world.admin_token),
            json={
                "mrn": "MRN-0001",
                "full_name": "Vikram Joshi",
                "gender": "MALE",
                "age_years": 54,
                "phone": "+919820022334",
                "blood_group": "O+",
                "allergies": ["Penicillin"],
                "pre_existing_conditions": ["Type 2 Diabetes"],
            },
        )

        # Assert
        patient = created(response)
        assert patient["mrn"] == "MRN-0001"
        assert "national_id" not in patient

    async def test_patient_without_age_or_date_of_birth_is_refused(
        self, client: AsyncClient, world: World
    ) -> None:
        """A record with neither cannot be triaged: protocols differ by age."""
        # Act
        response = await client.post(
            f"/api/v1/hospitals/{world.hospital_id}/patients",
            headers=auth(world.admin_token),
            json={"mrn": "MRN-NOAGE", "full_name": "Ageless Person", "gender": "OTHER"},
        )

        # Assert
        assert response.status_code == 422

    async def test_admission_reserves_a_bed_from_inventory(
        self, client: AsyncClient, world: World
    ) -> None:
        """Opening a case consumes one general bed."""
        # Arrange
        before = payload(
            await client.get(
                f"/api/v1/inventory/{world.general_bed_item_id}", headers=auth(world.admin_token)
            )
        )
        patients = payload(
            await client.get(
                f"/api/v1/hospitals/{world.hospital_id}/patients",
                headers=auth(world.admin_token),
                params={"search": "MRN-0001"},
            )
        )
        patient_id = patients["items"][0]["_id"]

        # Act
        case = created(
            await client.post(
                f"/api/v1/hospitals/{world.hospital_id}/cases",
                headers=auth(world.admin_token),
                json={
                    "case_number": "CASE-0001",
                    "patient_id": patient_id,
                    "doctor_id": world.doctor_id,
                    "department_id": world.department_id,
                    "bed_allocated": "GW-14",
                    "triage_level": 2,
                    "chief_symptoms": ["Fever", "Breathlessness"],
                    "initial_vitals": {
                        "systolic_bp": 138,
                        "diastolic_bp": 88,
                        "pulse_bpm": 96,
                        "spo2_percent": 94.0,
                        "temperature_celsius": 38.6,
                    },
                },
            )
        )
        after = payload(
            await client.get(
                f"/api/v1/inventory/{world.general_bed_item_id}", headers=auth(world.admin_token)
            )
        )

        # Assert
        assert case["status"] == "ADMITTED"
        assert len(case["vitals"]) == 1
        assert after["available_stock"] == before["available_stock"] - 1

    async def test_vitals_accumulate_rather_than_overwrite(
        self, client: AsyncClient, world: World
    ) -> None:
        """Deterioration is only visible as a trend, so readings are appended."""
        # Arrange
        case_id = await _case_id(client, world, "CASE-0001")

        # Act
        case = payload(
            await client.post(
                f"/api/v1/cases/{case_id}/vitals",
                headers=auth(world.admin_token),
                json={
                    "systolic_bp": 128,
                    "diastolic_bp": 82,
                    "pulse_bpm": 88,
                    "spo2_percent": 96.5,
                    "temperature_celsius": 37.4,
                },
            )
        )

        # Assert
        assert len(case["vitals"]) == 2

    async def test_impossible_blood_pressure_is_refused(
        self, client: AsyncClient, world: World
    ) -> None:
        """Systolic below diastolic is a data entry error, not an observation."""
        # Arrange
        case_id = await _case_id(client, world, "CASE-0001")

        # Act
        response = await client.post(
            f"/api/v1/cases/{case_id}/vitals",
            headers=auth(world.admin_token),
            json={
                "systolic_bp": 70,
                "diastolic_bp": 120,
                "pulse_bpm": 80,
                "spo2_percent": 98.0,
                "temperature_celsius": 37.0,
            },
        )

        # Assert
        assert response.status_code == 422
        assert "greater than" in response.json()["error"]

    async def test_prescription_is_added_to_the_case(
        self, client: AsyncClient, world: World
    ) -> None:
        """Medication orders accumulate on the encounter."""
        # Arrange
        case_id = await _case_id(client, world, "CASE-0001")

        # Act
        case = payload(
            await client.post(
                f"/api/v1/cases/{case_id}/prescriptions",
                headers=auth(world.admin_token),
                json={
                    "medicine_name": "Azithromycin",
                    "dosage": "500 mg",
                    "frequency": "once daily",
                    "duration_days": 5,
                },
            )
        )

        # Assert
        assert case["prescriptions"][0]["medicine_name"] == "Azithromycin"

    async def test_case_cannot_be_closed_through_the_status_endpoint(
        self, client: AsyncClient, world: World
    ) -> None:
        """Closing requires the discharge form, which demands a summary."""
        # Arrange
        case_id = await _case_id(client, world, "CASE-0001")

        # Act
        response = await client.patch(
            f"/api/v1/cases/{case_id}",
            headers=auth(world.admin_token),
            json={"status": "DISCHARGED"},
        )

        # Assert
        assert response.status_code == 422
        assert "discharge form" in response.json()["error"]

    async def test_triage_board_groups_open_cases_by_urgency(
        self, client: AsyncClient, world: World
    ) -> None:
        """The board is keyed by triage level name, most urgent first."""
        # Act
        board = payload(
            await client.get(
                f"/api/v1/hospitals/{world.hospital_id}/cases/triage-board",
                headers=auth(world.admin_token),
            )
        )

        # Assert
        assert "URGENT" in board
        assert board["URGENT"][0]["case_number"] == "CASE-0001"

    async def test_discharge_closes_the_case_and_releases_the_bed(
        self, client: AsyncClient, world: World
    ) -> None:
        """A discharged case must stop occupying capacity."""
        # Arrange
        case_id = await _case_id(client, world, "CASE-0001")
        before = payload(
            await client.get(
                f"/api/v1/inventory/{world.general_bed_item_id}", headers=auth(world.admin_token)
            )
        )

        # Act
        case = payload(
            await client.post(
                f"/api/v1/cases/{case_id}/discharge",
                headers=auth(world.admin_token),
                json={
                    "status": "DISCHARGED",
                    "discharge_summary": (
                        "Community-acquired pneumonia. Responded to azithromycin. "
                        "Afebrile for 48 hours, SpO2 stable on room air. "
                        "Advised follow-up in one week."
                    ),
                },
            )
        )
        after = payload(
            await client.get(
                f"/api/v1/inventory/{world.general_bed_item_id}", headers=auth(world.admin_token)
            )
        )

        # Assert
        assert case["status"] == "DISCHARGED"
        assert case["discharged_at"] is not None
        assert after["available_stock"] == before["available_stock"] + 1

    async def test_a_closed_case_cannot_be_amended(self, client: AsyncClient, world: World) -> None:
        """Appending vitals to a discharged case would corrupt the record."""
        # Arrange
        case_id = await _case_id(client, world, "CASE-0001")

        # Act
        response = await client.post(
            f"/api/v1/cases/{case_id}/vitals",
            headers=auth(world.admin_token),
            json={
                "systolic_bp": 120,
                "diastolic_bp": 80,
                "pulse_bpm": 72,
                "spo2_percent": 99.0,
                "temperature_celsius": 36.8,
            },
        )

        # Assert
        assert response.status_code == 409


class TestBilling:
    """Invoicing and settlement."""

    async def test_totals_are_derived_server_side(self, client: AsyncClient, world: World) -> None:
        """The client supplies rates and quantities; the server does the arithmetic."""
        # Arrange
        case_id = await _case_id(client, world, "CASE-0001")
        case = payload(
            await client.get(f"/api/v1/cases/{case_id}", headers=auth(world.admin_token))
        )

        # Act
        bill = created(
            await client.post(
                f"/api/v1/hospitals/{world.hospital_id}/bills",
                headers=auth(world.admin_token),
                json={
                    "invoice_no": "INV-0001",
                    "case_id": case_id,
                    "patient_id": case["patient_id"],
                    "line_items": [
                        {"description": "General ward, 4 days", "rate": "2500.00", "quantity": "4"},
                        {"description": "Azithromycin 500mg", "rate": "42.50", "quantity": "5"},
                    ],
                    "tax_amount": "515.63",
                    "discount_amount": "200.00",
                },
            )
        )

        # Assert
        assert bill["subtotal"] == "10212.50"
        assert bill["grand_total"] == "10528.13"
        assert bill["payment_status"] == "PENDING"

    async def test_partial_then_full_payment_settles_the_invoice(
        self, client: AsyncClient, world: World
    ) -> None:
        """Status only reaches PAID when the running total matches exactly."""
        # Arrange
        bill_id = await _bill_id(client, world, "INV-0001")

        # Act
        partial = payload(
            await client.post(
                f"/api/v1/bills/{bill_id}/payments",
                headers=auth(world.admin_token),
                json={"amount": "5000.00", "payment_mode": "UPI"},
            )
        )
        settled = payload(
            await client.post(
                f"/api/v1/bills/{bill_id}/payments",
                headers=auth(world.admin_token),
                json={"amount": "5528.13", "payment_mode": "CARD"},
            )
        )

        # Assert
        assert partial["payment_status"] == "PARTIALLY_PAID"
        assert settled["payment_status"] == "PAID"
        assert settled["settled_at"] is not None

    async def test_overpayment_is_refused(self, client: AsyncClient, world: World) -> None:
        """A payment beyond the balance due is a client error, not a credit."""
        # Arrange
        bill_id = await _bill_id(client, world, "INV-0001")

        # Act
        response = await client.post(
            f"/api/v1/bills/{bill_id}/payments",
            headers=auth(world.admin_token),
            json={"amount": "1.00", "payment_mode": "CASH"},
        )

        # Assert
        assert response.status_code == 409
        assert "already paid in full" in response.json()["error"]

    async def test_a_paid_invoice_cannot_be_cancelled(
        self, client: AsyncClient, world: World
    ) -> None:
        """Cancelling would erase the payment trail; a refund is the right path."""
        # Arrange
        bill_id = await _bill_id(client, world, "INV-0001")

        # Act
        response = await client.post(
            f"/api/v1/bills/{bill_id}/cancel",
            headers=auth(world.admin_token),
            params={"reason": "Filed against the wrong case"},
        )

        # Assert
        assert response.status_code == 409
        assert "refund" in response.json()["error"]


class TestInventory:
    """Stock tracking, capacity cards, and threshold alerts."""

    async def test_capacity_summary_reports_the_four_categories(
        self, client: AsyncClient, world: World
    ) -> None:
        """The overview cards come from one aggregated call."""
        # Act
        summary = payload(
            await client.get(
                f"/api/v1/hospitals/{world.hospital_id}/inventory/capacity",
                headers=auth(world.admin_token),
            )
        )

        # Assert
        categories = [card["category"] for card in summary]
        assert categories == ["GENERAL_BEDS", "ICU_BEDS", "VENTILATORS", "OXYGEN_LITERS"]
        assert next(c for c in summary if c["category"] == "ICU_BEDS")["total_stock"] == 30.0

    async def test_consuming_more_than_available_is_refused(
        self, client: AsyncClient, world: World
    ) -> None:
        """A hospital cannot allocate resources it does not have."""
        # Act
        response = await client.post(
            f"/api/v1/inventory/{world.icu_bed_item_id}/adjust",
            headers=auth(world.admin_token),
            json={"delta": -999, "reason": "Impossible allocation"},
        )

        # Assert
        assert response.status_code == 409
        assert "only 30" in response.json()["error"]

    async def test_low_stock_alert_fires_at_the_threshold(
        self, client: AsyncClient, world: World
    ) -> None:
        """The alert is what the Smart Alerts module will consume."""
        # Arrange
        created(
            await client.post(
                f"/api/v1/hospitals/{world.hospital_id}/inventory",
                headers=auth(world.admin_token),
                json={
                    "category": "OXYGEN_LITERS",
                    "item_name": "Bulk Oxygen Tank A",
                    "total_stock": 20000,
                    "available_stock": 900,
                    "min_safety_threshold": 1000,
                    "unit": "LITERS",
                },
            )
        )

        # Act
        alerts = payload(
            await client.get(
                "/api/v1/inventory/alerts",
                headers=auth(world.admin_token),
                params={"hospital_id": world.hospital_id},
            )
        )

        # Assert
        assert any(alert["item_name"] == "Bulk Oxygen Tank A" for alert in alerts)

    async def test_available_stock_above_total_is_refused(
        self, client: AsyncClient, world: World
    ) -> None:
        """Advertising beds the hospital does not own is the fragmentation
        this platform exists to fix."""
        # Act
        response = await client.post(
            f"/api/v1/hospitals/{world.hospital_id}/inventory",
            headers=auth(world.admin_token),
            json={
                "category": "VENTILATORS",
                "item_name": "Phantom Ventilator",
                "total_stock": 5,
                "available_stock": 50,
            },
        )

        # Assert
        assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _case_id(client: AsyncClient, world: World, case_number: str) -> Any:
    """Look up a case by its human-facing number."""
    cases = payload(
        await client.get(
            f"/api/v1/hospitals/{world.hospital_id}/cases", headers=auth(world.admin_token)
        )
    )
    return next(case["_id"] for case in cases["items"] if case["case_number"] == case_number)


async def _bill_id(client: AsyncClient, world: World, invoice_no: str) -> Any:
    """Look up an invoice by its number."""
    bills = payload(
        await client.get(
            f"/api/v1/hospitals/{world.hospital_id}/bills", headers=auth(world.admin_token)
        )
    )
    return next(bill["_id"] for bill in bills["items"] if bill["invoice_no"] == invoice_no)
