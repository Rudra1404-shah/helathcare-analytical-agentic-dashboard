"""Settings validation, including the production placeholder-secret guard."""

import base64

import pytest
from pydantic import ValidationError

from src.core.config import Environment, Settings

VALID_KEY = base64.urlsafe_b64encode(bytes(range(32))).decode("ascii")


class TestMongoUri:
    """Connection string validation."""

    @pytest.mark.parametrize(
        "uri",
        ["mongodb://localhost:27017", "mongodb+srv://cluster.example.test"],
    )
    def test_valid_schemes_are_accepted(self, uri: str) -> None:
        """Both MongoDB URI schemes must pass."""
        assert Settings(mongo_uri=uri).mongo_uri == uri

    @pytest.mark.parametrize("uri", ["postgres://localhost", "http://localhost", "localhost"])
    def test_non_mongodb_uris_are_rejected(self, uri: str) -> None:
        """A non-MongoDB URI is a misconfiguration that should fail at startup."""
        with pytest.raises(ValidationError, match="mongodb"):
            Settings(mongo_uri=uri)


class TestEncryptionKey:
    """The AES-GCM key must be exactly 32 bytes of urlsafe base64."""

    def test_valid_key_decodes_to_32_bytes(self) -> None:
        """A correctly sized key decodes cleanly."""
        settings = Settings(national_id_encryption_key=VALID_KEY)  # type: ignore[arg-type]
        assert len(settings.decoded_encryption_key()) == 32

    def test_short_key_is_rejected(self) -> None:
        """A 16-byte key would silently weaken encryption if accepted."""
        # Arrange
        short_key = base64.urlsafe_b64encode(bytes(16)).decode("ascii")
        settings = Settings(national_id_encryption_key=short_key)  # type: ignore[arg-type]

        # Act / Assert
        with pytest.raises(ValueError, match="must decode to 32 bytes"):
            settings.decoded_encryption_key()

    def test_non_base64_key_is_rejected(self) -> None:
        """A key that is not base64 must fail with a clear message."""
        settings = Settings(national_id_encryption_key="!!!not base64!!!")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="not valid urlsafe base64"):
            settings.decoded_encryption_key()


class TestPlaceholderSecretGuard:
    """Placeholder secrets must never reach a deployed environment."""

    def test_development_tolerates_placeholders(self) -> None:
        """Local development works out of the box with .env.example defaults."""
        settings = Settings(environment=Environment.DEVELOPMENT)
        assert settings.is_production is False

    @pytest.mark.parametrize("environment", [Environment.STAGING, Environment.PRODUCTION])
    def test_deployed_environments_reject_placeholder_key(self, environment: Environment) -> None:
        """Shipping the example key would encrypt National IDs with a public key."""
        with pytest.raises(ValidationError, match="placeholder"):
            Settings(
                environment=environment,
                national_id_hmac_secret="a-real-secret",  # type: ignore[arg-type]
            )

    @pytest.mark.parametrize("environment", [Environment.STAGING, Environment.PRODUCTION])
    def test_deployed_environments_reject_placeholder_hmac(self, environment: Environment) -> None:
        """The lookup HMAC secret is guarded the same way."""
        with pytest.raises(ValidationError, match="placeholder"):
            Settings(
                environment=environment,
                national_id_encryption_key=VALID_KEY,  # type: ignore[arg-type]
            )

    def test_production_with_real_secrets_is_accepted(self) -> None:
        """A properly configured production environment passes."""
        settings = Settings(
            environment=Environment.PRODUCTION,
            national_id_encryption_key=VALID_KEY,  # type: ignore[arg-type]
            national_id_hmac_secret="a-real-production-secret",  # type: ignore[arg-type]
        )
        assert settings.is_production is True


class TestSecretsAreNotLeaked:
    """Secrets must not appear in logs or tracebacks."""

    def test_repr_hides_the_encryption_key(self) -> None:
        """SecretStr must mask the value in repr output."""
        settings = Settings(national_id_encryption_key=VALID_KEY)  # type: ignore[arg-type]
        assert VALID_KEY not in repr(settings)

    def test_repr_hides_the_hmac_secret(self) -> None:
        """The HMAC secret is masked the same way."""
        settings = Settings(national_id_hmac_secret="super-secret-value")  # type: ignore[arg-type]
        assert "super-secret-value" not in repr(settings)

    def test_settings_are_frozen(self) -> None:
        """Configuration must not drift at runtime."""
        settings = Settings()
        with pytest.raises(ValidationError):
            settings.mongo_db_name = "other"
