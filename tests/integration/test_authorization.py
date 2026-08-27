"""Authentication and cross-hospital isolation.

The isolation tests are the security core of the platform: a hospital account
must not be able to read another hospital's patients, staff, cases, or
invoices, whatever it puts in the URL.
"""

from typing import Any

import pytest
from httpx import AsyncClient

from tests.integration.conftest import STRONG_PASSWORD, auth
from tests.integration.world import World, created, payload

pytestmark = pytest.mark.integration


class TestAuthentication:
    """Sign-in, token handling, and the failure envelope."""

    async def test_wrong_password_and_unknown_email_look_identical(
        self, client: AsyncClient, citizen: dict[str, Any]
    ) -> None:
        """Distinguishable errors would enumerate which accounts exist."""
        # Act
        wrong_password = await client.post(
            "/api/v1/auth/login",
            json={"email": citizen["email"], "password": "WrongPassword123"},
        )
        unknown_email = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "WrongPassword123"},
        )

        # Assert
        assert wrong_password.status_code == unknown_email.status_code == 401
        assert wrong_password.json()["error"] == unknown_email.json()["error"]

    async def test_a_citizen_cannot_use_the_government_login(
        self, client: AsyncClient, citizen: dict[str, Any]
    ) -> None:
        """The ministry portal pins the expected role."""
        # Act
        response = await client.post(
            "/api/v1/auth/govt/login",
            json={"official_email": citizen["email"], "password": STRONG_PASSWORD},
        )

        # Assert
        assert response.status_code == 401

    async def test_a_tampered_token_is_refused(
        self, client: AsyncClient, govt_admin: dict[str, Any]
    ) -> None:
        """Editing the payload breaks the signature."""
        # Arrange
        header, body, signature = govt_admin["token"].split(".")
        tampered = f"{header}.{body}.{signature[:-4]}AAAA"

        # Act
        response = await client.get("/api/v1/auth/me", headers=auth(tampered))

        # Assert
        assert response.status_code == 401
        assert response.headers["WWW-Authenticate"] == "Bearer"

    async def test_a_weak_password_is_refused_at_registration(self, client: AsyncClient) -> None:
        """The password policy is enforced before an account exists."""
        # Act
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Weak Password Person",
                "phone": "+919820044556",
                "email": "weak@example.com",
                "password": "alllowercase",
                "national_id": "9999-8888-7777",
                "address": {
                    "line1": "1 Test Road",
                    "city": "Mumbai",
                    "state": "Maharashtra",
                    "pincode": "400001",
                },
            },
        )

        # Assert
        assert response.status_code == 422
        assert "uppercase" in response.json()["error"]

    async def test_registering_the_same_national_id_twice_is_refused(
        self, client: AsyncClient, citizen: dict[str, Any]
    ) -> None:
        """One person, one citizen account -- otherwise the PHR splits in two."""
        # Act
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "Impostor Kulkarni",
                "phone": "+919820044557",
                "email": "impostor@example.com",
                "password": STRONG_PASSWORD,
                "national_id": "4321 8765 2109",
                "address": {
                    "line1": "2 Test Road",
                    "city": "Mumbai",
                    "state": "Maharashtra",
                    "pincode": "400001",
                },
            },
        )

        # Assert
        assert response.status_code == 409
        assert "National ID" in response.json()["error"]

    async def test_unknown_route_answers_in_the_standard_envelope(
        self, client: AsyncClient
    ) -> None:
        """One response shape, whatever went wrong."""
        # Act
        response = await client.get("/api/v1/does-not-exist")

        # Assert
        assert response.status_code == 404
        assert set(response.json()) == {"success", "data", "error", "meta"}

    async def test_registration_response_carries_no_credentials(
        self, client: AsyncClient, citizen: dict[str, Any]
    ) -> None:
        """UserResponse has nowhere to put a hash or a National ID."""
        # Act
        me = payload(await client.get("/api/v1/auth/me", headers=auth(citizen["token"])))

        # Assert -- the id is excluded because a random ObjectId hex can happen
        # to contain the digits being searched for.
        body = {key: value for key, value in me.items() if key != "_id"}
        assert "hashed_password" not in body
        assert "national_id" not in body
        assert "4321" not in str(body)


class TestHospitalIsolation:
    """A hospital account is confined to its own hospital."""

    async def test_cannot_list_another_hospitals_patients(
        self, client: AsyncClient, world: World, rival: World
    ) -> None:
        """The path names another hospital; the token says otherwise."""
        # Act
        response = await client.get(
            f"/api/v1/hospitals/{rival.hospital_id}/patients", headers=auth(world.admin_token)
        )

        # Assert
        assert response.status_code == 403

    async def test_cannot_read_another_hospitals_case(
        self, client: AsyncClient, world: World, rival: World
    ) -> None:
        """Direct-by-id access is guarded in the service, not just the path."""
        # Arrange -- created here so the test does not depend on run order
        case_id = await _rival_case(client, rival)

        # Act
        response = await client.get(f"/api/v1/cases/{case_id}", headers=auth(world.admin_token))

        # Assert
        assert response.status_code == 403

    async def test_cannot_register_staff_at_another_hospital(
        self, client: AsyncClient, world: World, rival: World
    ) -> None:
        """Writes are guarded the same way reads are."""
        # Act
        response = await client.post(
            f"/api/v1/hospitals/{rival.hospital_id}/staff/admin-support",
            headers=auth(world.admin_token),
            json={
                "full_name": "Infiltrator",
                "employee_id": "EMP-INFIL",
                "phone": "+919820000099",
                "role": "SECURITY",
            },
        )

        # Assert
        assert response.status_code == 403

    async def test_hospital_directory_shows_only_the_own_hospital(
        self, client: AsyncClient, world: World
    ) -> None:
        """A hospital account sees itself, whatever filters it passes."""
        # Act
        directory = payload(await client.get("/api/v1/hospitals", headers=auth(world.admin_token)))

        # Assert
        assert [item["_id"] for item in directory["items"]] == [world.hospital_id]

    async def test_a_citizen_cannot_reach_hospital_operations(
        self, client: AsyncClient, citizen: dict[str, Any], world: World
    ) -> None:
        """Operational modules are closed to the public."""
        # Act
        response = await client.get(
            f"/api/v1/hospitals/{world.hospital_id}/cases", headers=auth(citizen["token"])
        )

        # Assert
        assert response.status_code == 403

    async def test_hospital_admin_cannot_provision_a_government_account(
        self, client: AsyncClient, world: World
    ) -> None:
        """Privilege escalation through the provisioning endpoint."""
        # Act
        response = await client.post(
            "/api/v1/auth/users",
            headers=auth(world.admin_token),
            json={
                "email": "selfmade.minister@example.com",
                "password": STRONG_PASSWORD,
                "role": "GOVT_ADMIN",
                "full_name": "Self Made Minister",
            },
        )

        # Assert
        assert response.status_code == 403

    async def test_hospital_admin_provisions_staff_in_own_hospital(
        self, client: AsyncClient, world: World
    ) -> None:
        """The legitimate case still works."""
        # Act
        response = await client.post(
            "/api/v1/auth/users",
            headers=auth(world.admin_token),
            json={
                "email": "desk.clerk@sunrise.example.com",
                "password": STRONG_PASSWORD,
                "role": "HOSPITAL_STAFF",
                "full_name": "Desk Clerk",
                "hospital_id": world.hospital_id,
            },
        )

        # Assert
        assert response.status_code == 201

    async def test_complaints_desk_shows_only_own_hospital_to_a_hospital(
        self, client: AsyncClient, world: World, rival: World
    ) -> None:
        """A hospital sees grievances filed against it, and no others."""
        # Act
        complaints = payload(
            await client.get("/api/v1/complaints", headers=auth(rival.admin_token))
        )

        # Assert
        assert all(item["hospital_id"] == rival.hospital_id for item in complaints["items"])


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _rival_case(client: AsyncClient, rival: World) -> Any:
    """Open a case at the second hospital, for another hospital to fail to read."""
    patient = created(
        await client.post(
            f"/api/v1/hospitals/{rival.hospital_id}/patients",
            headers=auth(rival.admin_token),
            json={
                "mrn": "MRN-RIVAL-PROBE",
                "full_name": "Rival Hospital Patient",
                "gender": "OTHER",
                "age_years": 33,
            },
        )
    )
    case = created(
        await client.post(
            f"/api/v1/hospitals/{rival.hospital_id}/cases",
            headers=auth(rival.admin_token),
            json={
                "case_number": "CASE-RIVAL-PROBE",
                "patient_id": patient["_id"],
                "doctor_id": rival.doctor_id,
                "department_id": rival.department_id,
                "chief_symptoms": ["Abdominal pain"],
            },
        )
    )
    return case["_id"]
