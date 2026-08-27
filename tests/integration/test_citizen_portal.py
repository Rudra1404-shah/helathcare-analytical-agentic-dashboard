"""Citizen portal: complaints with mandatory evidence, and the unified PHR.

The PHR test is the one that proves the platform's whole premise. The same
citizen is registered as a patient at two different hospitals, under two
different MRNs, using two different formattings of the same National ID -- and
comes back as one person with one timeline.
"""

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from tests.integration.conftest import auth
from tests.integration.world import World, created, payload

pytestmark = pytest.mark.integration

# A 1x1 PNG. Small enough to inline, real enough to have a valid MIME type.
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


def evidence_payload(url: str, checksum: str, size: int) -> dict[str, Any]:
    """Build one evidence attachment referencing an uploaded file."""
    return {
        "url": url,
        "evidence_type": "PHOTO",
        "content_type": "image/png",
        "file_name": "ward.png",
        "size_bytes": size,
        "checksum_sha256": checksum,
    }


async def upload_photo(client: AsyncClient, token: str) -> dict[str, Any]:
    """Upload the tiny PNG and return the stored-file descriptor."""
    response = await client.post(
        "/api/v1/uploads/evidence",
        headers=auth(token),
        data={"evidence_type": "PHOTO"},
        files={"file": ("ward.png", TINY_PNG, "image/png")},
    )
    return created(response)


class TestEvidenceUpload:
    """Media has to land somewhere before a complaint can reference it."""

    async def test_photo_upload_returns_a_url_and_checksum(
        self, client: AsyncClient, citizen: dict[str, Any]
    ) -> None:
        """The response lines up with the evidence attachment schema."""
        # Act
        stored = await upload_photo(client, citizen["token"])

        # Assert
        assert stored["url"].startswith("http://testserver/uploads/")
        assert stored["checksum_sha256"] == hashlib.sha256(TINY_PNG).hexdigest()
        assert stored["size_bytes"] == len(TINY_PNG)

    async def test_client_filename_is_not_used_as_a_path(
        self, client: AsyncClient, citizen: dict[str, Any]
    ) -> None:
        """A traversal filename must not escape the upload directory."""
        # Act
        stored = created(
            await client.post(
                "/api/v1/uploads/evidence",
                headers=auth(citizen["token"]),
                data={"evidence_type": "PHOTO"},
                files={"file": ("../../../etc/passwd.png", TINY_PNG, "image/png")},
            )
        )

        # Assert
        assert ".." not in stored["file_name"]
        assert "/" not in stored["file_name"]

    async def test_video_mime_type_filed_as_a_photo_is_refused(
        self, client: AsyncClient, citizen: dict[str, Any]
    ) -> None:
        """The evidence viewer renders by declared type; a mismatch breaks it."""
        # Act
        response = await client.post(
            "/api/v1/uploads/evidence",
            headers=auth(citizen["token"]),
            data={"evidence_type": "PHOTO"},
            files={"file": ("clip.mp4", b"not really a video", "video/mp4")},
        )

        # Assert
        assert response.status_code == 422
        assert "not an accepted photo type" in response.json()["error"]

    async def test_an_empty_file_is_refused(
        self, client: AsyncClient, citizen: dict[str, Any]
    ) -> None:
        """An empty attachment substantiates nothing."""
        # Act
        response = await client.post(
            "/api/v1/uploads/evidence",
            headers=auth(citizen["token"]),
            data={"evidence_type": "PHOTO"},
            files={"file": ("empty.png", b"", "image/png")},
        )

        # Assert
        assert response.status_code == 422


class TestComplaintSubmission:
    """The Public Complaint Form and its mandatory-evidence rule."""

    async def test_complaint_without_evidence_is_refused(
        self, client: AsyncClient, citizen: dict[str, Any], world: World
    ) -> None:
        """The rule that defines the whole grievance module."""
        # Act
        response = await client.post(
            "/api/v1/complaints",
            headers=auth(citizen["token"]),
            json={
                "hospital_id": world.hospital_id,
                "incident_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
                "category": "HYGIENE",
                "description": (
                    "The general ward toilets were flooded and had not been cleaned "
                    "for the whole of my two day stay."
                ),
                "evidence": [],
            },
        )

        # Assert
        assert response.status_code == 422
        assert "evidence" in response.json()["error"]

    async def test_description_below_fifty_characters_is_refused(
        self, client: AsyncClient, citizen: dict[str, Any], world: World
    ) -> None:
        """A one-line grievance cannot be investigated."""
        # Arrange
        stored = await upload_photo(client, citizen["token"])

        # Act
        response = await client.post(
            "/api/v1/complaints",
            headers=auth(citizen["token"]),
            json={
                "hospital_id": world.hospital_id,
                "incident_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
                "category": "NEGLIGENCE",
                "description": "It was bad.",
                "evidence": [
                    evidence_payload(stored["url"], stored["checksum_sha256"], stored["size_bytes"])
                ],
            },
        )

        # Assert
        assert response.status_code == 422

    async def test_incident_in_the_future_is_refused(
        self, client: AsyncClient, citizen: dict[str, Any], world: World
    ) -> None:
        """An incident cannot be reported before it happens."""
        # Arrange
        stored = await upload_photo(client, citizen["token"])

        # Act
        response = await client.post(
            "/api/v1/complaints",
            headers=auth(citizen["token"]),
            json={
                "hospital_id": world.hospital_id,
                "incident_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
                "category": "SHORTAGE",
                "description": (
                    "There was no oxygen available in the emergency ward when my "
                    "father was brought in for breathlessness."
                ),
                "evidence": [
                    evidence_payload(stored["url"], stored["checksum_sha256"], stored["size_bytes"])
                ],
            },
        )

        # Assert
        assert response.status_code == 422
        assert "future" in response.json()["error"]

    async def test_complaint_with_evidence_is_accepted_and_numbered(
        self, client: AsyncClient, citizen: dict[str, Any], world: World
    ) -> None:
        """A valid complaint gets a server-generated, human-quotable reference."""
        # Arrange
        stored = await upload_photo(client, citizen["token"])

        # Act
        complaint = created(
            await client.post(
                "/api/v1/complaints",
                headers=auth(citizen["token"]),
                json={
                    "hospital_id": world.hospital_id,
                    "department_id": world.department_id,
                    "incident_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
                    "category": "OVERCHARGING",
                    "description": (
                        "I was charged for an ICU bed for three days although my "
                        "father was in the general ward the entire time. The final "
                        "invoice does not match the treatment given."
                    ),
                    "evidence": [
                        evidence_payload(
                            stored["url"], stored["checksum_sha256"], stored["size_bytes"]
                        )
                    ],
                },
            )
        )

        # Assert
        assert complaint["complaint_number"].startswith("CMP-")
        assert complaint["investigation_status"] == "SUBMITTED"
        assert len(complaint["evidence"]) == 1


class TestInvestigationWorkflow:
    """The ministry's side of the grievance module."""

    async def test_citizen_cannot_investigate_their_own_complaint(
        self, client: AsyncClient, citizen: dict[str, Any]
    ) -> None:
        """Investigation is a ministry power."""
        # Arrange
        complaint_id = await _first_complaint_id(client, citizen["token"])

        # Act
        response = await client.patch(
            f"/api/v1/complaints/{complaint_id}/investigation",
            headers=auth(citizen["token"]),
            json={"investigation_status": "DISMISSED"},
        )

        # Assert
        assert response.status_code == 403

    async def test_closing_without_an_action_is_refused(
        self, client: AsyncClient, govt_admin: dict[str, Any], citizen: dict[str, Any]
    ) -> None:
        """An enforcement decision with no recorded rationale is not auditable."""
        # Arrange
        complaint_id = await _first_complaint_id(client, citizen["token"])

        # Act
        response = await client.patch(
            f"/api/v1/complaints/{complaint_id}/investigation",
            headers=auth(govt_admin["token"]),
            json={"investigation_status": "ACTION_TAKEN"},
        )

        # Assert
        assert response.status_code == 422
        assert "action_taken is required" in response.json()["error"]

    async def test_inquiry_assignment_requires_an_officer(
        self, client: AsyncClient, govt_admin: dict[str, Any], citizen: dict[str, Any]
    ) -> None:
        """An assigned inquiry must name who is running it."""
        # Arrange
        complaint_id = await _first_complaint_id(client, citizen["token"])

        # Act
        response = await client.patch(
            f"/api/v1/complaints/{complaint_id}/investigation",
            headers=auth(govt_admin["token"]),
            json={"investigation_status": "INQUIRY_ASSIGNED"},
        )

        # Assert
        assert response.status_code == 422

    async def test_ministry_closes_the_investigation_with_an_action(
        self, client: AsyncClient, govt_admin: dict[str, Any], citizen: dict[str, Any]
    ) -> None:
        """Closing stamps the decision, the reasoning, and the time."""
        # Arrange
        complaint_id = await _first_complaint_id(client, citizen["token"])

        # Act
        complaint = payload(
            await client.patch(
                f"/api/v1/complaints/{complaint_id}/investigation",
                headers=auth(govt_admin["token"]),
                json={
                    "investigation_status": "ACTION_TAKEN",
                    "action_taken": "FINE",
                    "hospital_explanation": "Billing clerk applied the wrong tariff sheet.",
                    "closure_remarks": (
                        "Overcharge confirmed on audit. Refund ordered and a fine "
                        "levied under the state tariff rules."
                    ),
                },
            )
        )

        # Assert
        assert complaint["investigation_status"] == "ACTION_TAKEN"
        assert complaint["action_taken"] == "FINE"
        assert complaint["closed_at"] is not None

    async def test_a_closed_investigation_cannot_be_reopened(
        self, client: AsyncClient, govt_admin: dict[str, Any], citizen: dict[str, Any]
    ) -> None:
        """Reopening would let a resolution be quietly rewritten."""
        # Arrange
        complaint_id = await _first_complaint_id(client, citizen["token"])

        # Act
        response = await client.patch(
            f"/api/v1/complaints/{complaint_id}/investigation",
            headers=auth(govt_admin["token"]),
            json={"investigation_status": "UNDER_REVIEW"},
        )

        # Assert
        assert response.status_code == 409


class TestPersonalHealthRecord:
    """The unified cross-hospital record."""

    async def test_records_from_two_hospitals_resolve_to_one_citizen(
        self, client: AsyncClient, citizen: dict[str, Any], world: World, rival: World
    ) -> None:
        """The same National ID, formatted differently, unifies both records.

        This is the platform's founding claim: a citizen treated privately in
        one place and publicly in another has one history, not two.
        """
        # Arrange -- registered at both hospitals, with differently formatted IDs
        created(
            await client.post(
                f"/api/v1/hospitals/{world.hospital_id}/patients",
                headers=auth(world.admin_token),
                json={
                    "mrn": "MRN-PHR-A",
                    "full_name": "Asha Kulkarni",
                    "gender": "FEMALE",
                    "age_years": 41,
                    "blood_group": "B+",
                    "national_id": "4321-8765-2109",
                    "allergies": ["Sulfa drugs"],
                },
            )
        )
        created(
            await client.post(
                f"/api/v1/hospitals/{rival.hospital_id}/patients",
                headers=auth(rival.admin_token),
                json={
                    "mrn": "MRN-PHR-B",
                    "full_name": "Asha Kulkarni",
                    "gender": "FEMALE",
                    "age_years": 41,
                    "blood_group": "B+",
                    "national_id": "432187652109",
                    "pre_existing_conditions": ["Hypothyroidism"],
                },
            )
        )

        # Act
        records = payload(
            await client.get("/api/v1/citizen/records", headers=auth(citizen["token"]))
        )

        # Assert -- a superset, because bulk upload may have linked more records
        assert {"MRN-PHR-A", "MRN-PHR-B"} <= {record["mrn"] for record in records}

    async def test_health_record_merges_encounters_across_hospitals(
        self, client: AsyncClient, citizen: dict[str, Any], world: World, rival: World
    ) -> None:
        """One timeline, both hospitals, newest first."""
        # Arrange
        await _admit(client, world, "MRN-PHR-A", "CASE-PHR-A", ["Palpitations"])
        await _admit(client, rival, "MRN-PHR-B", "CASE-PHR-B", ["Fatigue"])

        # Act
        record = payload(
            await client.get("/api/v1/citizen/health-record", headers=auth(citizen["token"]))
        )

        # Assert
        case_numbers = {entry["case_number"] for entry in record["cases"]}
        hospitals = {entry["hospital"]["hospital_id"] for entry in record["cases"]}
        assert {"CASE-PHR-A", "CASE-PHR-B"} <= case_numbers
        assert {world.hospital_id, rival.hospital_id} <= hospitals
        assert "Sulfa drugs" in record["allergies"]
        assert "Hypothyroidism" in record["pre_existing_conditions"]

    async def test_export_can_exclude_sections(
        self, client: AsyncClient, citizen: dict[str, Any]
    ) -> None:
        """A citizen chooses what their export carries."""
        # Act
        record = payload(
            await client.post(
                "/api/v1/citizen/health-record/export",
                headers=auth(citizen["token"]),
                json={
                    "include_bills": False,
                    "include_prescriptions": False,
                    "include_vitals": True,
                },
            )
        )

        # Assert
        assert record["cases"]
        assert all(entry["bill"] is None for entry in record["cases"])
        assert all(entry["prescriptions"] == [] for entry in record["cases"])

    async def test_one_citizen_cannot_read_anothers_record(
        self, client: AsyncClient, citizen: dict[str, Any], govt_admin: dict[str, Any]
    ) -> None:
        """The ministry endpoint is closed to citizens."""
        # Act
        response = await client.get(
            f"/api/v1/citizen/{citizen['id']}/health-record", headers=auth(citizen["token"])
        )

        # Assert
        assert response.status_code == 403

    async def test_ministry_can_read_a_citizen_record(
        self, client: AsyncClient, citizen: dict[str, Any], govt_admin: dict[str, Any]
    ) -> None:
        """Ministry access is permitted, and audited."""
        # Act
        response = await client.get(
            f"/api/v1/citizen/{citizen['id']}/health-record", headers=auth(govt_admin["token"])
        )

        # Assert
        assert payload(response)["citizen_user_id"] == citizen["id"]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _first_complaint_id(client: AsyncClient, token: str) -> Any:
    """Return the citizen's own most recent complaint."""
    complaints = payload(await client.get("/api/v1/complaints", headers=auth(token)))
    assert complaints["items"], "no complaint has been filed yet"
    return complaints["items"][0]["_id"]


async def _admit(
    client: AsyncClient,
    world: World,
    mrn: str,
    case_number: str,
    symptoms: list[str],
) -> Any:
    """Register an encounter for an existing patient at one hospital."""
    patients = payload(
        await client.get(
            f"/api/v1/hospitals/{world.hospital_id}/patients",
            headers=auth(world.admin_token),
            params={"search": mrn},
        )
    )
    patient_id = patients["items"][0]["_id"]
    return created(
        await client.post(
            f"/api/v1/hospitals/{world.hospital_id}/cases",
            headers=auth(world.admin_token),
            json={
                "case_number": case_number,
                "patient_id": patient_id,
                "doctor_id": world.doctor_id,
                "department_id": world.department_id,
                "chief_symptoms": symptoms,
            },
        )
    )
