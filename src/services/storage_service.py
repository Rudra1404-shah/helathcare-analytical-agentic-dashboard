"""Storage for complaint evidence and patient medical documents.

Only the pointer and integrity metadata reach MongoDB; the bytes live here. The
whole surface is three functions, so replacing local disk with S3 or GridFS
later is a change to this module alone.

Uploads are treated as hostile. The declared kind (photo or video) must match
the MIME type, the MIME type must be on an allow-list, the size is capped, and
the stored filename is generated rather than taken from the client -- a filename
of ``../../etc/passwd`` cannot escape the upload directory because the client's
filename is never used as a path component.
"""

import hashlib
import secrets
from dataclasses import dataclass
from pathlib import Path

from src.core.config import Settings, get_settings
from src.core.errors import UnprocessableError
from src.domain.enums import EvidenceType

__all__ = [
    "ALLOWED_DOCUMENT_TYPES",
    "ALLOWED_PHOTO_TYPES",
    "ALLOWED_VIDEO_TYPES",
    "StoredFile",
    "store_document",
    "store_evidence",
]

ALLOWED_PHOTO_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
}

ALLOWED_VIDEO_TYPES: dict[str, str] = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
}

ALLOWED_DOCUMENT_TYPES: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}

_RANDOM_NAME_BYTES = 16


@dataclass(frozen=True)
class StoredFile:
    """Where a file ended up, and what it hashes to."""

    url: str
    file_name: str
    content_type: str
    size_bytes: int
    checksum_sha256: str


def store_evidence(
    content: bytes,
    content_type: str,
    evidence_type: EvidenceType,
    settings: Settings | None = None,
) -> StoredFile:
    """Persist one complaint evidence attachment.

    Args:
        content: Raw uploaded bytes.
        content_type: MIME type declared by the client.
        evidence_type: Whether the citizen filed this as a photo or a video.
        settings: Optional settings override.

    Returns:
        The stored file's public URL, size, and SHA-256.

    Raises:
        UnprocessableError: If the file is empty, too large, of a type that is
            not accepted, or of a type that contradicts the declared kind.
    """
    allowed = ALLOWED_PHOTO_TYPES if evidence_type is EvidenceType.PHOTO else ALLOWED_VIDEO_TYPES
    normalised = content_type.split(";")[0].strip().lower()

    if normalised not in allowed:
        expected = "photo" if evidence_type is EvidenceType.PHOTO else "video"
        msg = (
            f"'{content_type}' is not an accepted {expected} type; "
            f"upload one of: {', '.join(sorted(allowed))}"
        )
        raise UnprocessableError(msg)

    return _write(content, normalised, allowed[normalised], settings)


def store_document(
    content: bytes,
    content_type: str,
    settings: Settings | None = None,
) -> StoredFile:
    """Persist one patient medical history document.

    Raises:
        UnprocessableError: If the file is empty, too large, or of a type that
            is not accepted.
    """
    normalised = content_type.split(";")[0].strip().lower()
    if normalised not in ALLOWED_DOCUMENT_TYPES:
        msg = (
            f"'{content_type}' is not an accepted document type; "
            f"upload one of: {', '.join(sorted(ALLOWED_DOCUMENT_TYPES))}"
        )
        raise UnprocessableError(msg)

    return _write(content, normalised, ALLOWED_DOCUMENT_TYPES[normalised], settings)


def _write(
    content: bytes,
    content_type: str,
    extension: str,
    settings: Settings | None,
) -> StoredFile:
    """Validate the payload, write it to disk, and describe where it went."""
    active = settings or get_settings()

    if not content:
        msg = "the uploaded file is empty; there is nothing to attach"
        raise UnprocessableError(msg)

    if len(content) > active.max_upload_bytes:
        limit_mb = active.max_upload_bytes / (1024 * 1024)
        actual_mb = len(content) / (1024 * 1024)
        msg = f"the uploaded file is {actual_mb:.1f} MB; the limit is {limit_mb:.0f} MB"
        raise UnprocessableError(msg)

    directory = Path(active.upload_dir)
    directory.mkdir(parents=True, exist_ok=True)

    # The client's filename is never used as a path component, so a crafted
    # name cannot traverse out of the upload directory.
    file_name = f"{secrets.token_urlsafe(_RANDOM_NAME_BYTES)}{extension}"
    (directory / file_name).write_bytes(content)

    return StoredFile(
        url=f"{active.upload_base_url.rstrip('/')}/{file_name}",
        file_name=file_name,
        content_type=content_type,
        size_bytes=len(content),
        checksum_sha256=hashlib.sha256(content).hexdigest(),
    )
