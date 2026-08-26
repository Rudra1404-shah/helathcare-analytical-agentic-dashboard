"""Reusable constrained field types shared across models and schemas.

Defining these once keeps a phone number validated identically whether it
arrives on a citizen registration form, a staff intake form, or a doctor
onboarding form.
"""

from typing import Annotated

from pydantic import Field, StringConstraints

__all__ = [
    "ARGON2_HASH_PREFIX",
    "Icd10Code",
    "LicenseNumber",
    "MedicalRecordNumber",
    "NonEmptyStr",
    "PersonName",
    "PhoneNumber",
    "PinCode",
    "RegistrationNumber",
    "ShortText",
]

ARGON2_HASH_PREFIX = "$argon2"
"""Every Argon2 encoded hash begins with this marker."""

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

PersonName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=120),
]

ShortText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
]

PhoneNumber = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^\+?[1-9]\d{7,14}$"),
    Field(description="E.164-style phone number, optionally prefixed with '+'."),
]

PinCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^\d{6}$"),
    Field(description="Six-digit Indian PIN code."),
]

LicenseNumber = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, min_length=3, max_length=50),
    Field(description="Government-issued licence identifier."),
]

RegistrationNumber = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, min_length=3, max_length=50),
    Field(description="Nursing, pharmacy, or medical council registration number."),
]

MedicalRecordNumber = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, min_length=3, max_length=40),
    Field(description="Hospital-scoped Medical Record Number."),
]

Icd10Code = Annotated[
    str,
    # The pattern is checked against the input before `to_upper` is applied, so it
    # must accept either case; the stored value is always upper-cased.
    StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z]\d{2}(\.\d{1,2})?$"),
    Field(description="ICD-10 code, e.g. 'A09' or 'J18.9'."),
]
