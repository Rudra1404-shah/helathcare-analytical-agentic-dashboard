"""Version 1 of the HTTP API.

:data:`api_router` is the single object ``src.main`` mounts. Adding a router
here is the only step needed to expose a new form -- there is no second
registration list to keep in sync.
"""

from fastapi import APIRouter

from src.api.v1 import (
    analytics,
    auth,
    bills,
    cases,
    citizen,
    complaints,
    hospitals,
    inventory,
    patients,
    uploads,
    workforce,
    zones,
)

__all__ = ["api_router"]

api_router = APIRouter(prefix="/api/v1")

# Government portal
api_router.include_router(auth.router)
api_router.include_router(zones.router)
api_router.include_router(hospitals.router)

# Hospital operations
api_router.include_router(workforce.departments_router)
api_router.include_router(workforce.staff_router)
api_router.include_router(workforce.doctors_router)
api_router.include_router(patients.router)
api_router.include_router(cases.case_types_router)
api_router.include_router(cases.cases_router)
api_router.include_router(inventory.router)
api_router.include_router(bills.router)

# Analytical intelligence
api_router.include_router(analytics.router)

# Public grievance and citizen self-service
api_router.include_router(complaints.router)
api_router.include_router(citizen.router)
api_router.include_router(uploads.router)
