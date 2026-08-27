"""A minimal but complete hospital, built once through the real API.

Every operational test needs the same scaffolding: a zone, an accredited
hospital, an admin who works there, a department, a doctor, and enough bed
inventory to admit somebody. Building it through the HTTP endpoints rather than
by inserting documents means the scaffolding itself is a test -- if hospital
registration breaks, every downstream test says so immediately.
"""

from dataclasses import dataclass
from typing import Any

from httpx import AsyncClient

__all__ = ["World", "build_world", "created", "payload"]


@dataclass
class World:
    """Identifiers for the scaffolding, plus the tokens to act on it."""

    zone_code: str
    hospital_id: str
    admin_token: str
    admin_email: str
    department_id: str
    doctor_id: str
    general_bed_item_id: str
    icu_bed_item_id: str


def payload(response: Any) -> Any:
    """Return the ``data`` field of a successful envelope, asserting success."""
    assert response.status_code < 400, f"{response.status_code}: {response.text}"
    body = response.json()
    assert body["success"] is True, response.text
    return body["data"]


def created(response: Any) -> Any:
    """Return the ``data`` field of a 201 response."""
    assert response.status_code == 201, f"{response.status_code}: {response.text}"
    return response.json()["data"]


async def build_world(
    client: AsyncClient,
    govt_token: str,
    make_account: Any,
    token_for: Any,
    suffix: str = "",
) -> World:
    """Create the scaffolding and return its identifiers.

    Args:
        client: HTTP client bound to the app.
        govt_token: A ministry token, used for the zone and hospital.
        make_account: Callable inserting an account directly.
        token_for: Callable signing an account in.
        suffix: Appended to every unique key, so a second world does not
            collide with the first.
    """
    from src.domain.enums import UserRole
    from tests.integration.conftest import auth

    govt = auth(govt_token)

    zone_code = f"MH-MUM-Z{suffix or '01'}"
    await client.post(
        "/api/v1/zones",
        headers=govt,
        json={
            "zone_code": zone_code,
            "name": f"Andheri West {suffix}".strip(),
            "state": "Maharashtra",
            "city": "Mumbai",
            "population_covered": 480_000,
            "centroid": {"latitude": 19.1197, "longitude": 72.8464},
        },
    )

    hospital = created(
        await client.post(
            "/api/v1/hospitals",
            headers=govt,
            json={
                "name": f"Sunrise Multispeciality {suffix}".strip(),
                "license_no": f"MH-HOSP-{suffix or '0001'}",
                "sector_type": "PRIVATE",
                "state": "Maharashtra",
                "city": "Mumbai",
                "zone_code": zone_code,
                "ward_area": "K-West",
                "location": {"latitude": 19.1197, "longitude": 72.8464},
                "capacity": {
                    "total_sanctioned_beds": 200,
                    "icu_beds": 30,
                    "emergency_beds": 20,
                    "ventilators": 15,
                    "oxygen_bulk_capacity_liters": 20000.0,
                    "ambulance_count": 4,
                },
                "accreditation_status": "NABH",
                "accredited_on": "2024-04-01",
                "nodal_officer_name": "Officer Rao",
                "contact_phone": "+919820012345",
                "contact_email": f"contact{suffix}@sunrise.example.com",
            },
        )
    )
    hospital_id = hospital["_id"]

    admin_email = f"admin{suffix}@sunrise.example.com"
    await make_account(admin_email, UserRole.HOSPITAL_ADMIN, hospital_id)
    admin_token = await token_for(client, admin_email)
    admin = auth(admin_token)

    department = created(
        await client.post(
            f"/api/v1/hospitals/{hospital_id}/departments",
            headers=admin,
            json={
                "name": "General Medicine",
                "code": f"GMED{suffix}",
                "floor": "2",
                "wing": "East",
                "bed_count": 60,
            },
        )
    )
    department_id = department["_id"]

    doctor = created(
        await client.post(
            f"/api/v1/hospitals/{hospital_id}/doctors",
            headers=admin,
            json={
                "full_name": "Dr Meera Iyer",
                "license_no": f"MCI-{suffix or '00001'}",
                "specialization": "Internal Medicine",
                "department_id": department_id,
                "qualification": "MBBS, MD (Medicine)",
                "phone": "+919820099887",
                "employment_type": "FULL_TIME",
                "shifts": ["MORNING", "EVENING"],
                "max_daily_patients": 40,
            },
        )
    )
    doctor_id = doctor["_id"]

    general = created(
        await client.post(
            f"/api/v1/hospitals/{hospital_id}/inventory",
            headers=admin,
            json={
                "category": "GENERAL_BEDS",
                "item_name": "Ward A General Bed",
                "total_stock": 60,
                "available_stock": 60,
                "min_safety_threshold": 5,
                "unit": "UNITS",
            },
        )
    )
    icu = created(
        await client.post(
            f"/api/v1/hospitals/{hospital_id}/inventory",
            headers=admin,
            json={
                "category": "ICU_BEDS",
                "item_name": "ICU Bed",
                "total_stock": 30,
                "available_stock": 30,
                "min_safety_threshold": 4,
                "unit": "UNITS",
            },
        )
    )

    return World(
        zone_code=zone_code,
        hospital_id=hospital_id,
        admin_token=admin_token,
        admin_email=admin_email,
        department_id=department_id,
        doctor_id=doctor_id,
        general_bed_item_id=general["_id"],
        icu_bed_item_id=icu["_id"],
    )
