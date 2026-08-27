"""Government portal endpoints: zones, the hospital directory, accreditation."""

from typing import Any

import pytest
from httpx import AsyncClient

from tests.integration.conftest import auth
from tests.integration.world import World, created, payload

pytestmark = pytest.mark.integration


class TestZoneManagement:
    """The Zone/Area Management Form."""

    async def test_ministry_registers_a_zone(
        self, client: AsyncClient, govt_admin: dict[str, Any]
    ) -> None:
        """A zone is created with the population denominator analytics needs."""
        # Act
        response = await client.post(
            "/api/v1/zones",
            headers=auth(govt_admin["token"]),
            json={
                "zone_code": "MH-PUN-Z07",
                "name": "Kothrud",
                "state": "Maharashtra",
                "city": "Pune",
                "population_covered": 310_000,
            },
        )

        # Assert
        zone = created(response)
        assert zone["zone_code"] == "MH-PUN-Z07"
        assert zone["population_covered"] == 310_000

    async def test_duplicate_zone_code_is_refused(
        self, client: AsyncClient, govt_admin: dict[str, Any]
    ) -> None:
        """Zone codes are unique platform-wide; a re-registration answers 409."""
        # Arrange
        body = {
            "zone_code": "MH-PUN-Z08",
            "name": "Baner",
            "state": "Maharashtra",
            "city": "Pune",
            "population_covered": 90_000,
        }
        await client.post("/api/v1/zones", headers=auth(govt_admin["token"]), json=body)

        # Act
        response = await client.post("/api/v1/zones", headers=auth(govt_admin["token"]), json=body)

        # Assert
        assert response.status_code == 409
        assert "already registered" in response.json()["error"]

    async def test_a_citizen_cannot_create_a_zone(
        self, client: AsyncClient, citizen: dict[str, Any]
    ) -> None:
        """Zone management is a ministry function."""
        # Act
        response = await client.post(
            "/api/v1/zones",
            headers=auth(citizen["token"]),
            json={
                "zone_code": "XX-XXX-Z99",
                "name": "Nowhere",
                "state": "Nowhere",
                "city": "Nowhere",
                "population_covered": 1,
            },
        )

        # Assert
        assert response.status_code == 403

    async def test_updating_population_succeeds(
        self, client: AsyncClient, govt_admin: dict[str, Any], world: World
    ) -> None:
        """A census revision changes the per-capita denominator."""
        # Arrange
        zones = payload(
            await client.get(
                "/api/v1/zones", headers=auth(govt_admin["token"]), params={"city": "Mumbai"}
            )
        )
        zone_id = zones["items"][0]["_id"]

        # Act
        response = await client.patch(
            f"/api/v1/zones/{zone_id}",
            headers=auth(govt_admin["token"]),
            json={"population_covered": 512_000},
        )

        # Assert
        assert payload(response)["population_covered"] == 512_000


class TestHospitalDirectory:
    """The multi-hospital directory with city and zone filters."""

    async def test_directory_lists_registered_hospitals(
        self, client: AsyncClient, govt_admin: dict[str, Any], world: World
    ) -> None:
        """The ministry sees every hospital, with pagination metadata."""
        # Act
        response = await client.get("/api/v1/hospitals", headers=auth(govt_admin["token"]))

        # Assert
        body = payload(response)
        assert body["meta"]["total"] >= 1
        assert any(item["_id"] == world.hospital_id for item in body["items"])

    async def test_city_filter_narrows_the_directory(
        self, client: AsyncClient, govt_admin: dict[str, Any], world: World
    ) -> None:
        """Filtering by city returns only hospitals in that city."""
        # Act
        response = await client.get(
            "/api/v1/hospitals",
            headers=auth(govt_admin["token"]),
            params={"city": "Mumbai", "sector_type": "PRIVATE"},
        )

        # Assert
        items = payload(response)["items"]
        assert items
        assert all(item["city"] == "Mumbai" for item in items)

    async def test_city_options_endpoint_returns_distinct_pairs(
        self, client: AsyncClient, govt_admin: dict[str, Any], world: World
    ) -> None:
        """The filter dropdown is populated without paging the whole register."""
        # Act
        response = await client.get("/api/v1/hospitals/cities", headers=auth(govt_admin["token"]))

        # Assert
        cities = payload(response)
        assert {"state": "Maharashtra", "city": "Mumbai"} in cities

    async def test_search_term_with_regex_characters_is_safe(
        self, client: AsyncClient, govt_admin: dict[str, Any], world: World
    ) -> None:
        """An unescaped '(' would be an invalid pattern and a 500."""
        # Act
        response = await client.get(
            "/api/v1/hospitals",
            headers=auth(govt_admin["token"]),
            params={"search": "Sunrise ("},
        )

        # Assert
        assert response.status_code == 200
        assert payload(response)["items"] == []

    async def test_hospital_in_an_unregistered_zone_is_refused(
        self, client: AsyncClient, govt_admin: dict[str, Any]
    ) -> None:
        """Without a zone there is no population denominator for analytics."""
        # Act
        response = await client.post(
            "/api/v1/hospitals",
            headers=auth(govt_admin["token"]),
            json={
                "name": "Orphan Clinic",
                "license_no": "MH-HOSP-ORPHAN",
                "sector_type": "PUBLIC",
                "state": "Maharashtra",
                "city": "Nagpur",
                "zone_code": "MH-NAG-Z99",
                "location": {"latitude": 21.1458, "longitude": 79.0882},
                "capacity": {"total_sanctioned_beds": 50, "icu_beds": 5},
            },
        )

        # Assert
        assert response.status_code == 409
        assert "not registered" in response.json()["error"]

    async def test_duplicate_licence_number_is_refused(
        self, client: AsyncClient, govt_admin: dict[str, Any], world: World
    ) -> None:
        """Licence numbers are unique platform-wide."""
        # Act
        response = await client.post(
            "/api/v1/hospitals",
            headers=auth(govt_admin["token"]),
            json={
                "name": "Copycat Hospital",
                "license_no": "MH-HOSP-0001",
                "sector_type": "TRUST",
                "state": "Maharashtra",
                "city": "Mumbai",
                "zone_code": world.zone_code,
                "location": {"latitude": 19.11, "longitude": 72.84},
                "capacity": {"total_sanctioned_beds": 10, "icu_beds": 1},
            },
        )

        # Assert
        assert response.status_code == 409

    async def test_icu_beds_exceeding_sanctioned_total_is_refused(
        self, client: AsyncClient, govt_admin: dict[str, Any], world: World
    ) -> None:
        """A hospital cannot claim more specialised beds than it was sanctioned."""
        # Act
        response = await client.post(
            "/api/v1/hospitals",
            headers=auth(govt_admin["token"]),
            json={
                "name": "Impossible Hospital",
                "license_no": "MH-HOSP-IMPOSSIBLE",
                "sector_type": "PUBLIC",
                "state": "Maharashtra",
                "city": "Mumbai",
                "zone_code": world.zone_code,
                "location": {"latitude": 19.11, "longitude": 72.84},
                "capacity": {"total_sanctioned_beds": 10, "icu_beds": 20},
            },
        )

        # Assert
        assert response.status_code == 422
        assert "cannot exceed" in response.json()["error"]


class TestAccreditation:
    """Ministry accreditation decisions."""

    async def test_ministry_blacklists_a_hospital(
        self, client: AsyncClient, govt_admin: dict[str, Any], rival: World
    ) -> None:
        """Blacklisting also deactivates the hospital."""
        # Act
        response = await client.patch(
            f"/api/v1/hospitals/{rival.hospital_id}/accreditation",
            headers=auth(govt_admin["token"]),
            json={
                "accreditation_status": "BLACKLISTED",
                "remarks": "Repeated hygiene violations confirmed on inspection.",
            },
        )

        # Assert
        hospital = payload(response)
        assert hospital["accreditation_status"] == "BLACKLISTED"
        assert hospital["is_active"] is False

    async def test_reinstating_reactivates_the_hospital(
        self, client: AsyncClient, govt_admin: dict[str, Any], rival: World
    ) -> None:
        """Restoring accreditation brings the hospital back into service."""
        # Act
        response = await client.patch(
            f"/api/v1/hospitals/{rival.hospital_id}/accreditation",
            headers=auth(govt_admin["token"]),
            json={"accreditation_status": "STATE_LICENSED", "remarks": "Remediation verified."},
        )

        # Assert
        hospital = payload(response)
        assert hospital["accreditation_status"] == "STATE_LICENSED"
        assert hospital["is_active"] is True
        assert hospital["accredited_on"] is not None

    async def test_hospital_admin_cannot_change_own_accreditation(
        self, client: AsyncClient, world: World
    ) -> None:
        """Self-accreditation is exactly what the two-sided split prevents."""
        # Act
        response = await client.patch(
            f"/api/v1/hospitals/{world.hospital_id}/accreditation",
            headers=auth(world.admin_token),
            json={"accreditation_status": "NABH"},
        )

        # Assert
        assert response.status_code == 403

    async def test_hospital_admin_updates_own_infrastructure(
        self, client: AsyncClient, world: World
    ) -> None:
        """The profile form is the hospital's own side of the same document."""
        # Act
        response = await client.patch(
            f"/api/v1/hospitals/{world.hospital_id}/profile",
            headers=auth(world.admin_token),
            json={"ward_area": "K-West Annexe", "contact_phone": "+919820055555"},
        )

        # Assert
        hospital = payload(response)
        assert hospital["ward_area"] == "K-West Annexe"
        assert hospital["license_no"] == "MH-HOSP-0001"
