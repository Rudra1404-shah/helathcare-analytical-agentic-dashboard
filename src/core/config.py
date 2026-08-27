"""Application configuration loaded from the environment.

All settings are prefixed ``UNHP_`` and read from the process environment or a
local ``.env`` file. Secrets are held as :class:`~pydantic.SecretStr` so they do
not leak into logs, tracebacks, or ``repr`` output.

See ``.env.example`` for the full template.
"""

import base64
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

__all__ = ["Environment", "Settings", "get_settings"]

# Placeholder values shipped in .env.example. Refused outside development so a
# half-configured deployment fails loudly at startup instead of silently
# encrypting National IDs with a publicly known key.
_PLACEHOLDER_MARKERS = ("CHANGE_ME", "changeme")

_REQUIRED_KEY_BYTES = 32

_SECRET_SETTING_NAMES = (
    "national_id_encryption_key",
    "national_id_hmac_secret",
    "jwt_secret",
)
"""Every secret that must not still hold an ``.env.example`` placeholder."""

DEFAULT_CORS_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")
"""Local Next.js development origins allowed by default."""


class Environment(StrEnum):
    """Deployment environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Runtime configuration for the Unified National Health Platform."""

    model_config = SettingsConfigDict(
        env_prefix="UNHP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # --- MongoDB ---------------------------------------------------------- #
    mongo_uri: str = Field(
        default="mongodb://localhost:27017",
        description="MongoDB connection string.",
    )
    mongo_db_name: str = Field(
        default="unhp",
        min_length=1,
        description="Database name holding all platform collections.",
    )

    # --- Application ------------------------------------------------------ #
    environment: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Active deployment environment.",
    )
    debug: bool = Field(default=False, description="Enable verbose debug behaviour.")

    # --- Security --------------------------------------------------------- #
    national_id_encryption_key: SecretStr = Field(
        default=SecretStr("CHANGE_ME_32_BYTE_URLSAFE_BASE64_KEY_HERE="),
        description="urlsafe-base64 encoded 32-byte AES-GCM key for National IDs.",
    )
    national_id_hmac_secret: SecretStr = Field(
        default=SecretStr("CHANGE_ME_HMAC_SECRET"),
        description="Secret used for the deterministic National ID lookup HMAC.",
    )
    jwt_secret: SecretStr = Field(
        default=SecretStr("CHANGE_ME_JWT_SIGNING_SECRET"),
        description="Symmetric signing secret for portal access tokens.",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="JWS algorithm used to sign access tokens.",
    )
    access_token_ttl_minutes: int = Field(
        default=720,
        gt=0,
        le=10_080,
        description="Access token lifetime in minutes; a clinical shift plus handover.",
    )

    # --- API surface ------------------------------------------------------ #
    # NoDecode stops pydantic-settings JSON-parsing the env value before the
    # validator below gets a chance to split it on commas.
    cors_origins: Annotated[tuple[str, ...], NoDecode] = Field(
        default=DEFAULT_CORS_ORIGINS,
        description="Browser origins permitted to call the API, comma-separated in the env.",
    )

    # --- Evidence and document storage ------------------------------------ #
    upload_dir: Path = Field(
        default=Path("uploads"),
        description="Directory holding complaint evidence and medical documents.",
    )
    upload_base_url: str = Field(
        default="http://localhost:8000/uploads",
        description="Public base URL the stored media is served from.",
    )
    max_upload_bytes: int = Field(
        default=25 * 1024 * 1024,
        gt=0,
        description="Largest single evidence or document upload accepted.",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Accept a comma-separated env string as well as a real sequence.

        ``UNHP_CORS_ORIGINS=http://a,http://b`` is how this is set in a
        container; without this the whole string would become one origin and
        every browser call would be blocked.
        """
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    @field_validator("jwt_algorithm")
    @classmethod
    def _validate_jwt_algorithm(cls, value: str) -> str:
        """Refuse an unsigned or unsupported token algorithm.

        ``none`` would make every access token forgeable, so it is rejected
        outright rather than left to the JWT library's defaults.
        """
        allowed = {"HS256", "HS384", "HS512"}
        if value not in allowed:
            msg = f"jwt_algorithm must be one of {sorted(allowed)}, got '{value}'"
            raise ValueError(msg)
        return value

    @field_validator("mongo_uri")
    @classmethod
    def _validate_mongo_uri(cls, value: str) -> str:
        """Reject connection strings that are not MongoDB URIs."""
        if not value.startswith(("mongodb://", "mongodb+srv://")):
            msg = "mongo_uri must start with 'mongodb://' or 'mongodb+srv://'"
            raise ValueError(msg)
        return value

    @property
    def is_production(self) -> bool:
        """Return whether the platform is running in production."""
        return self.environment is Environment.PRODUCTION

    @model_validator(mode="after")
    def _reject_placeholder_secrets_outside_development(self) -> "Settings":
        """Fail fast when production still carries the ``.env.example`` placeholders."""
        if self.environment is Environment.DEVELOPMENT:
            return self

        for name in _SECRET_SETTING_NAMES:
            secret: SecretStr = getattr(self, name)
            revealed = secret.get_secret_value()
            if any(marker in revealed for marker in _PLACEHOLDER_MARKERS):
                msg = (
                    f"{name} still holds the .env.example placeholder; "
                    f"a real secret is required in {self.environment} environments"
                )
                raise ValueError(msg)
        return self

    @property
    def access_token_ttl_seconds(self) -> int:
        """Return the access token lifetime in seconds."""
        return self.access_token_ttl_minutes * 60

    def decoded_encryption_key(self) -> bytes:
        """Return the raw 32-byte AES-GCM key.

        Raises:
            ValueError: If the configured key is not valid urlsafe base64 or does
                not decode to exactly 32 bytes.
        """
        revealed = self.national_id_encryption_key.get_secret_value()
        try:
            raw = base64.urlsafe_b64decode(revealed)
        except (ValueError, TypeError) as exc:
            msg = "national_id_encryption_key is not valid urlsafe base64"
            raise ValueError(msg) from exc

        if len(raw) != _REQUIRED_KEY_BYTES:
            msg = (
                f"national_id_encryption_key must decode to {_REQUIRED_KEY_BYTES} bytes, "
                f"got {len(raw)}"
            )
            raise ValueError(msg)
        return raw


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
