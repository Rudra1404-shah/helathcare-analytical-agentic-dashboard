"""Business logic for the Unified National Health Platform.

Services own the rules that sit between an HTTP request and a Beanie document:
uniqueness checks, cross-collection consistency, capacity allocation, and the
audit trail. They raise :class:`~src.core.errors.DomainError` rather than
``HTTPException``, so the same function is callable from a router, a seed
script, or a scheduled job.

One module per bounded area, mirroring the three portals in ``PROJECT_SPEC.md``.
"""
