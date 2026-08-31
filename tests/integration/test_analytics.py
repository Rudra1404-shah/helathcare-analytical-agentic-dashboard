"""The analytics engine over a real database.

Two things can only be checked here. The first is tenancy as the HTTP surface
actually enforces it, with a real token and a real second hospital rather than a
constructed actor. The second is the BSON round trip: ``CLAUDE.md`` records four
defects that reached Phase 2 precisely because no unit test makes a document
travel through MongoDB and back, and two of them -- ``Decimal128`` on read and
naive datetimes -- bear directly on a module built out of timestamps.
"""

from typing import Any

import pytest
from httpx import AsyncClient

from tests.integration.conftest import auth
from tests.integration.world import World, created, payload

pytestmark = pytest.mark.integration

HOSPITAL_MODULES = (
    "realtime",
    "outbreaks",
    "surge",
    "workforce",
    "resources",
    "alerts",
    "policy-impact",
)
NATIONAL_MODULES = ("overview", *HOSPITAL_MODULES)


class TestAnalyticsTenancy:
    """Who the API lets read what. The security core of this phase."""

    @pytest.mark.parametrize("module", NATIONAL_MODULES)
    async def test_citizen_cannot_read_national_intelligence(
        self, client: AsyncClient, citizen: dict[str, Any], module: str
    ) -> None:
        """A citizen shares the ministry's unscoped resolution and must still be refused.

        ``hospital_scope_of`` returns None for both roles, so the ordinary
        ministry-sweep idiom would read that None as "every hospital".
        """
        # Act
        response = await client.get(
            f"/api/v1/analytics/national/{module}", headers=auth(citizen["token"])
        )

        # Assert
        assert response.status_code == 403, response.text
        assert response.json()["success"] is False

    @pytest.mark.parametrize("module", HOSPITAL_MODULES)
    async def test_citizen_cannot_read_a_hospital_view(
        self, client: AsyncClient, citizen: dict[str, Any], world: World, module: str
    ) -> None:
        """Analytics is staff-only at every scope, not just nationally."""
        # Act
        response = await client.get(
            f"/api/v1/hospitals/{world.hospital_id}/analytics/{module}",
            headers=auth(citizen["token"]),
        )

        # Assert
        assert response.status_code == 403, response.text

    @pytest.mark.parametrize("module", HOSPITAL_MODULES)
    async def test_a_hospital_cannot_read_another_hospitals_analytics(
        self, client: AsyncClient, world: World, rival: World, module: str
    ) -> None:
        """The isolation rule the whole platform rests on, applied to analytics.

        Aggregates leak as readily as records: a rival's occupancy and stockout
        countdown are commercially sensitive even without a patient in them.
        """
        # Act
        response = await client.get(
            f"/api/v1/hospitals/{rival.hospital_id}/analytics/{module}",
            headers=auth(world.admin_token),
        )

        # Assert
        assert response.status_code == 403, response.text

    @pytest.mark.parametrize("module", NATIONAL_MODULES)
    async def test_a_hospital_account_cannot_read_the_national_view(
        self, client: AsyncClient, world: World, module: str
    ) -> None:
        """A scoped account resolving to itself would see a "national" view of one site."""
        # Act
        response = await client.get(
            f"/api/v1/analytics/national/{module}", headers=auth(world.admin_token)
        )

        # Assert
        assert response.status_code == 403, response.text

    @pytest.mark.parametrize("module", HOSPITAL_MODULES)
    async def test_a_hospital_reads_its_own_analytics(
        self, client: AsyncClient, world: World, module: str
    ) -> None:
        """The ordinary path from the hospital portal."""
        # Act
        response = await client.get(
            f"/api/v1/hospitals/{world.hospital_id}/analytics/{module}",
            headers=auth(world.admin_token),
        )

        # Assert
        assert response.status_code == 200, response.text
        assert response.json()["success"] is True

    @pytest.mark.parametrize("module", NATIONAL_MODULES)
    async def test_the_ministry_reads_every_module_nationally(
        self, client: AsyncClient, govt_admin: dict[str, Any], module: str
    ) -> None:
        """Every national route answers with the standard envelope."""
        # Act
        response = await client.get(
            f"/api/v1/analytics/national/{module}", headers=auth(govt_admin["token"])
        )

        # Assert
        assert response.status_code == 200, response.text
        assert response.json()["data"] is not None

    @pytest.mark.parametrize("module", HOSPITAL_MODULES)
    async def test_the_ministry_may_drill_into_one_hospital(
        self, client: AsyncClient, govt_admin: dict[str, Any], world: World, module: str
    ) -> None:
        """Drilling from a flagged zone into the site causing it is the whole workflow."""
        # Act
        response = await client.get(
            f"/api/v1/hospitals/{world.hospital_id}/analytics/{module}",
            headers=auth(govt_admin["token"]),
        )

        # Assert
        assert response.status_code == 200, response.text

    async def test_an_unauthenticated_request_is_refused(
        self, client: AsyncClient, world: World
    ) -> None:
        """No token is a 401, not an anonymous national dashboard."""
        # Act
        response = await client.get(f"/api/v1/hospitals/{world.hospital_id}/analytics/realtime")

        # Assert
        assert response.status_code == 401, response.text


class TestAnalyticsRoundTrip:
    """Shapes that survive BSON, which is where Phase 2's four defects hid."""

    async def test_realtime_reflects_a_case_admitted_through_the_api(
        self, client: AsyncClient, govt_admin: dict[str, Any]
    ) -> None:
        """An admission must move occupancy, end to end through a real database.

        Built on its own hospital rather than the shared one so the assertion is
        exact rather than a lower bound another test could shift.
        """
        # Arrange
        from tests.integration.conftest import _make_account, _token
        from tests.integration.world import build_world

        scene = await build_world(client, govt_admin["token"], _make_account, _token, suffix="03")
        headers = auth(scene.admin_token)

        before = payload(
            await client.get(
                f"/api/v1/hospitals/{scene.hospital_id}/analytics/realtime", headers=headers
            )
        )

        patient = created(
            await client.post(
                f"/api/v1/hospitals/{scene.hospital_id}/patients",
                headers=headers,
                json={
                    "mrn": "MRN-03-0001",
                    "full_name": "Analytics Test Patient",
                    "gender": "FEMALE",
                    "age_years": 41,
                },
            )
        )

        # Act
        created(
            await client.post(
                f"/api/v1/hospitals/{scene.hospital_id}/cases",
                headers=headers,
                json={
                    "case_number": "CASE-03-0001",
                    "patient_id": patient["_id"],
                    "doctor_id": scene.doctor_id,
                    "department_id": scene.department_id,
                    "bed_allocated": "GW-01",
                    "triage_level": 2,
                    "chief_symptoms": ["Fever"],
                },
            )
        )
        after = payload(
            await client.get(
                f"/api/v1/hospitals/{scene.hospital_id}/analytics/realtime", headers=headers
            )
        )

        # Assert
        assert before["open_cases"] == 0
        assert after["open_cases"] == 1
        assert after["bed_occupancy_ratio"] == pytest.approx(1 / 200)
        urgent = next(entry for entry in after["triage_breakdown"] if entry["triage_level"] == 2)
        assert urgent["open_cases"] == 1

    async def test_stored_timestamps_survive_the_forecast(
        self, client: AsyncClient, world: World
    ) -> None:
        """The forecaster reads ``admitted_at`` straight off a stored document.

        MongoDB returns naive datetimes without a tz-aware client, and comparing
        one against an aware "now" raises ``TypeError``. A 200 here proves the
        whole time-series path handles what the driver actually hands back.
        """
        # Act
        data = payload(
            await client.get(
                f"/api/v1/hospitals/{world.hospital_id}/analytics/surge",
                headers=auth(world.admin_token),
                params={"history_days": 30, "horizon_days": 14},
            )
        )

        # Assert
        assert len(data["history"]) == 30
        assert len(data["points"]) == 14
        assert data["points"][0]["horizon_day"] == 1
        assert data["confidence"] in {"HIGH", "MODERATE", "LOW", "INSUFFICIENT_DATA"}

    async def test_resource_projection_labels_itself_as_an_estimate(
        self, client: AsyncClient, world: World
    ) -> None:
        """The platform holds no stock ledger, so a burn rate is inferred.

        Presenting an inference as a measurement is how a dashboard loses its
        credibility, so every projection carries its basis.
        """
        # Act
        data = payload(
            await client.get(
                f"/api/v1/hospitals/{world.hospital_id}/analytics/resources",
                headers=auth(world.admin_token),
            )
        )

        # Assert
        assert data["basis"] in {"ESTIMATED_FROM_CASE_DEMAND", "INSUFFICIENT_HISTORY"}
        for projection in data["projections"]:
            assert projection["basis"] == data["basis"]
            assert projection["window_days"] >= 1

    async def test_national_workforce_view_carries_no_doctor_names(
        self, client: AsyncClient, govt_admin: dict[str, Any], world: World
    ) -> None:
        """Zero PHI, asserted against the serialised response the client receives.

        The hospital view names the doctor to move; the ministry view answers
        the same question at department level and names nobody.
        """
        # Act
        national = await client.get(
            "/api/v1/analytics/national/workforce", headers=auth(govt_admin["token"])
        )
        scoped = payload(
            await client.get(
                f"/api/v1/hospitals/{world.hospital_id}/analytics/workforce",
                headers=auth(world.admin_token),
            )
        )

        # Assert
        assert national.json()["data"]["doctors"] == []
        assert "Dr Meera Iyer" not in national.text
        assert any(entry["full_name"] == "Dr Meera Iyer" for entry in scoped["doctors"])

    async def test_alerts_are_tiered_and_counted_consistently(
        self, client: AsyncClient, govt_admin: dict[str, Any]
    ) -> None:
        """Per-tier counts must agree with the list they summarise."""
        # Act
        data = payload(
            await client.get("/api/v1/analytics/national/alerts", headers=auth(govt_admin["token"]))
        )

        # Assert
        tiers = [alert["tier"] for alert in data["alerts"]]
        assert data["critical_count"] == tiers.count("CRITICAL")
        assert data["high_count"] == tiers.count("HIGH")
        assert data["medium_count"] == tiers.count("MEDIUM")
        assert data["info_count"] == tiers.count("INFO")
        order = ["CRITICAL", "HIGH", "MEDIUM", "INFO"]
        assert tiers == sorted(tiers, key=order.index)

    async def test_outbreak_query_parameters_are_validated(
        self, client: AsyncClient, govt_admin: dict[str, Any]
    ) -> None:
        """A nonsensical window is rejected at the edge, not carried into the maths."""
        # Act
        response = await client.get(
            "/api/v1/analytics/national/outbreaks",
            headers=auth(govt_admin["token"]),
            params={"window_days": 0},
        )

        # Assert
        assert response.status_code == 422, response.text

    async def test_national_overview_summarises_the_platform(
        self, client: AsyncClient, govt_admin: dict[str, Any]
    ) -> None:
        """The command centre's summary strip, over real registered hospitals."""
        # Act
        data = payload(
            await client.get(
                "/api/v1/analytics/national/overview", headers=auth(govt_admin["token"])
            )
        )

        # Assert
        assert data["hospital_count"] >= 1
        assert data["zone_count"] >= 1
        assert data["total_sanctioned_beds"] > 0
        assert data["population_covered"] > 0
        assert data["generated_at"]
