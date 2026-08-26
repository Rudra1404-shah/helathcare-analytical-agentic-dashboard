"""Password hashing and National ID protection."""

import pytest

from src.core.config import Environment, Settings
from src.core.security import (
    decrypt_national_id,
    encrypt_national_id,
    hash_password,
    national_id_lookup_hash,
    needs_rehash,
    verify_password,
)

PLAIN_PASSWORD = "CorrectHorse9Battery"
SAMPLE_NATIONAL_ID = "1234-5678-9012"


class TestPasswordHashing:
    """Argon2 password handling."""

    def test_hash_is_not_the_plaintext(self) -> None:
        """The stored value must never contain the password itself."""
        # Act
        hashed = hash_password(PLAIN_PASSWORD)

        # Assert
        assert hashed != PLAIN_PASSWORD
        assert PLAIN_PASSWORD not in hashed
        assert hashed.startswith("$argon2")

    def test_correct_password_verifies(self) -> None:
        """A matching password returns True."""
        hashed = hash_password(PLAIN_PASSWORD)
        assert verify_password(PLAIN_PASSWORD, hashed) is True

    def test_wrong_password_does_not_verify(self) -> None:
        """A non-matching password returns False rather than raising."""
        hashed = hash_password(PLAIN_PASSWORD)
        assert verify_password("WrongPassword1", hashed) is False

    def test_malformed_hash_returns_false_rather_than_raising(self) -> None:
        """A corrupt stored hash must not leak the reason for failure."""
        assert verify_password(PLAIN_PASSWORD, "not-a-real-hash") is False

    def test_same_password_hashes_differently_each_time(self) -> None:
        """Argon2 salts every hash, so identical passwords differ on disk."""
        assert hash_password(PLAIN_PASSWORD) != hash_password(PLAIN_PASSWORD)

    def test_empty_password_is_rejected(self) -> None:
        """An empty password is a caller bug, not a valid credential."""
        with pytest.raises(ValueError, match="must not be empty"):
            hash_password("")

    def test_needs_rehash_is_false_for_a_fresh_hash(self) -> None:
        """A hash just produced uses current parameters."""
        assert needs_rehash(hash_password(PLAIN_PASSWORD)) is False

    def test_needs_rehash_is_true_for_a_malformed_hash(self) -> None:
        """An unparseable hash should be replaced."""
        assert needs_rehash("garbage") is True


class TestNationalIdEncryption:
    """AES-GCM round-tripping of National IDs."""

    def test_round_trip_recovers_the_original(self, test_settings: Settings) -> None:
        """Encryption must be reversible for the citizen's own PHR view."""
        # Act
        token = encrypt_national_id(SAMPLE_NATIONAL_ID, test_settings)
        recovered = decrypt_national_id(token, test_settings)

        # Assert
        assert recovered == SAMPLE_NATIONAL_ID

    def test_ciphertext_does_not_contain_the_plaintext(self, test_settings: Settings) -> None:
        """The stored token must not leak the ID it protects."""
        token = encrypt_national_id(SAMPLE_NATIONAL_ID, test_settings)
        assert SAMPLE_NATIONAL_ID not in token
        assert "123456789012" not in token

    def test_encrypting_twice_gives_different_ciphertexts(self, test_settings: Settings) -> None:
        """A fresh nonce per call prevents ciphertext equality leaking ID equality."""
        first = encrypt_national_id(SAMPLE_NATIONAL_ID, test_settings)
        second = encrypt_national_id(SAMPLE_NATIONAL_ID, test_settings)
        assert first != second

    def test_tampered_ciphertext_is_rejected(self, test_settings: Settings) -> None:
        """AES-GCM authentication must catch modification."""
        # Arrange
        token = encrypt_national_id(SAMPLE_NATIONAL_ID, test_settings)
        tampered = ("A" if token[-1] != "A" else "B").join([token[:-1], ""])

        # Act / Assert
        with pytest.raises(ValueError):
            decrypt_national_id(tampered, test_settings)

    def test_truncated_token_is_rejected(self, test_settings: Settings) -> None:
        """A token shorter than the nonce cannot be valid."""
        with pytest.raises(ValueError, match="truncated"):
            decrypt_national_id("AAAA", test_settings)

    def test_non_base64_token_is_rejected(self, test_settings: Settings) -> None:
        """Malformed input must fail cleanly."""
        with pytest.raises(ValueError):
            decrypt_national_id("!!!not base64!!!", test_settings)

    def test_empty_national_id_is_rejected(self, test_settings: Settings) -> None:
        """An empty ID is a caller bug."""
        with pytest.raises(ValueError, match="must not be empty"):
            encrypt_national_id("   ", test_settings)


class TestNationalIdLookupHash:
    """The deterministic hash that makes cross-hospital lookup possible."""

    def test_same_id_gives_the_same_hash(self, test_settings: Settings) -> None:
        """Determinism is what allows an indexed lookup."""
        first = national_id_lookup_hash(SAMPLE_NATIONAL_ID, test_settings)
        second = national_id_lookup_hash(SAMPLE_NATIONAL_ID, test_settings)
        assert first == second

    def test_different_ids_give_different_hashes(self, test_settings: Settings) -> None:
        """Distinct citizens must not collide."""
        first = national_id_lookup_hash("1111-2222-3333", test_settings)
        second = national_id_lookup_hash("4444-5555-6666", test_settings)
        assert first != second

    @pytest.mark.parametrize(
        "variant",
        ["1234-5678-9012", "1234 5678 9012", "123456789012", " 1234-5678-9012 "],
    )
    def test_formatting_variants_normalise_to_one_hash(
        self, variant: str, test_settings: Settings
    ) -> None:
        """A citizen typing spaces instead of dashes must still resolve to one person.

        This is what makes the unified cross-hospital record work in practice.
        """
        canonical = national_id_lookup_hash("123456789012", test_settings)
        assert national_id_lookup_hash(variant, test_settings) == canonical

    def test_hash_is_64_hex_characters(self, test_settings: Settings) -> None:
        """The digest shape must match what the model field accepts."""
        digest = national_id_lookup_hash(SAMPLE_NATIONAL_ID, test_settings)
        assert len(digest) == 64
        assert all(char in "0123456789abcdef" for char in digest)

    def test_hash_does_not_contain_the_plaintext(self, test_settings: Settings) -> None:
        """The indexed value must not leak the ID."""
        digest = national_id_lookup_hash(SAMPLE_NATIONAL_ID, test_settings)
        assert "123456789012" not in digest

    def test_different_secrets_give_different_hashes(self, test_settings: Settings) -> None:
        """The HMAC key must actually participate in the digest."""
        # Arrange
        other = Settings(
            environment=Environment.DEVELOPMENT,
            national_id_encryption_key=test_settings.national_id_encryption_key,
            national_id_hmac_secret="a-completely-different-secret",  # type: ignore[arg-type]
        )

        # Act / Assert
        assert national_id_lookup_hash(
            SAMPLE_NATIONAL_ID, test_settings
        ) != national_id_lookup_hash(SAMPLE_NATIONAL_ID, other)
