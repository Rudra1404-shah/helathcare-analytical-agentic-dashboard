"""Cryptographic primitives for credentials and National ID protection.

Two distinct concerns live here:

* **Passwords** are hashed with Argon2id and are never recoverable.
* **National IDs** must stay recoverable (a citizen can view their own record),
  so they are encrypted with AES-GCM *and* accompanied by a deterministic
  HMAC-SHA256 lookup hash. The HMAC makes "find the patient with this National
  ID" possible without ever storing or indexing the plaintext.

Nothing in this module reads the environment directly; callers pass a
:class:`~src.core.config.Settings` instance so tests can supply their own keys.
"""

import base64
import hmac
import os
from hashlib import sha256

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.core.config import Settings, get_settings

__all__ = [
    "NATIONAL_ID_LOOKUP_HASH_LENGTH",
    "decrypt_national_id",
    "encrypt_national_id",
    "hash_password",
    "national_id_lookup_hash",
    "needs_rehash",
    "verify_password",
]

_hasher = PasswordHasher()

_NONCE_BYTES = 12
"""AES-GCM standard nonce length."""

NATIONAL_ID_LOOKUP_HASH_LENGTH = 64
"""Hex character length of an HMAC-SHA256 digest."""


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with Argon2id.

    Args:
        plain_password: The password as supplied by the user.

    Returns:
        An Argon2 encoded hash string, safe to persist.

    Raises:
        ValueError: If ``plain_password`` is empty.
    """
    if not plain_password:
        msg = "password must not be empty"
        raise ValueError(msg)
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plaintext password against a stored Argon2 hash.

    Returns ``False`` rather than raising for any mismatch or malformed hash, so
    callers cannot accidentally leak *why* authentication failed.
    """
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed_password: str) -> bool:
    """Return whether a stored hash was made with outdated Argon2 parameters."""
    try:
        return _hasher.check_needs_rehash(hashed_password)
    except InvalidHashError:
        return True


# --------------------------------------------------------------------------- #
# National ID protection
# --------------------------------------------------------------------------- #
def _normalise_national_id(national_id: str) -> str:
    """Normalise a National ID so lookup hashes are stable across formatting."""
    return national_id.replace(" ", "").replace("-", "").strip().upper()


def encrypt_national_id(national_id: str, settings: Settings | None = None) -> str:
    """Encrypt a National ID with AES-GCM.

    A fresh random nonce is generated per call, so encrypting the same ID twice
    produces different ciphertexts. Use :func:`national_id_lookup_hash` when you
    need a stable value to index or search on.

    Args:
        national_id: Plaintext National ID.
        settings: Optional settings override; defaults to the process settings.

    Returns:
        urlsafe-base64 of ``nonce || ciphertext``.

    Raises:
        ValueError: If ``national_id`` is empty or the configured key is invalid.
    """
    if not national_id.strip():
        msg = "national_id must not be empty"
        raise ValueError(msg)

    active = settings or get_settings()
    aesgcm = AESGCM(active.decoded_encryption_key())
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = aesgcm.encrypt(nonce, national_id.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_national_id(token: str, settings: Settings | None = None) -> str:
    """Recover a National ID previously produced by :func:`encrypt_national_id`.

    Raises:
        ValueError: If the token is malformed, truncated, or fails authentication.
    """
    active = settings or get_settings()
    try:
        raw = base64.urlsafe_b64decode(token)
    except (ValueError, TypeError) as exc:
        msg = "national ID token is not valid urlsafe base64"
        raise ValueError(msg) from exc

    if len(raw) <= _NONCE_BYTES:
        msg = "national ID token is truncated"
        raise ValueError(msg)

    aesgcm = AESGCM(active.decoded_encryption_key())
    try:
        plaintext = aesgcm.decrypt(raw[:_NONCE_BYTES], raw[_NONCE_BYTES:], None)
    except InvalidTag as exc:
        msg = "national ID token failed authentication; it may have been tampered with"
        raise ValueError(msg) from exc
    return plaintext.decode("utf-8")


def national_id_lookup_hash(national_id: str, settings: Settings | None = None) -> str:
    """Return a deterministic, indexable HMAC-SHA256 of a National ID.

    The same National ID always maps to the same hash, which supports
    "find this citizen" queries without persisting the plaintext. The HMAC key
    keeps the digest resistant to offline dictionary attacks over the (small)
    National ID space.

    Raises:
        ValueError: If ``national_id`` is empty.
    """
    if not national_id.strip():
        msg = "national_id must not be empty"
        raise ValueError(msg)

    active = settings or get_settings()
    key = active.national_id_hmac_secret.get_secret_value().encode("utf-8")
    normalised = _normalise_national_id(national_id).encode("utf-8")
    return hmac.new(key, normalised, sha256).hexdigest()
