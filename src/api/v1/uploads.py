"""Media and document upload endpoints.

Uploading is a separate step from filing a complaint. The citizen's browser
posts the photo or video here, gets back a URL and a checksum, and only then
submits the complaint referencing them. Splitting the two means a large video
upload that fails does not lose the typed description with it, and the
complaint payload stays small enough to retry.
"""

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status
from pydantic import Field

from src.api.deps import CurrentUser, HospitalActor, SettingsDep
from src.core.errors import UnprocessableError
from src.domain.enums import EvidenceType
from src.domain.schemas.common import ApiResponse, ResponseSchema
from src.services import storage_service

router = APIRouter(prefix="/uploads", tags=["uploads"])


class UploadedFileResponse(ResponseSchema):
    """Where an uploaded file landed, ready to paste into a form payload.

    The fields line up one-for-one with
    :class:`~src.domain.schemas.complaint.EvidenceAttachmentRequest`, so the
    client forwards this object almost verbatim.
    """

    url: str = Field(description="Public URL of the stored media.")
    file_name: str = Field(description="Server-generated name; the client's name is never used.")
    content_type: str
    size_bytes: int = Field(gt=0)
    checksum_sha256: str = Field(description="Hex SHA-256, for tamper detection.")


@router.post(
    "/evidence",
    response_model=ApiResponse[UploadedFileResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_evidence(
    _actor: CurrentUser,
    settings: SettingsDep,
    evidence_type: Annotated[EvidenceType, Form(description="PHOTO or VIDEO.")],
    file: Annotated[UploadFile, File(description="The photo or video itself.")],
) -> ApiResponse[UploadedFileResponse]:
    """Upload one complaint evidence attachment.

    The declared kind must match the file's MIME type: a video filed as a photo
    is refused, because the ministry's evidence viewer renders by declared type
    and a mismatch would show a broken frame instead of the evidence.
    """
    content = await file.read()
    stored = storage_service.store_evidence(
        content=content,
        content_type=_require_content_type(file),
        evidence_type=evidence_type,
        settings=settings,
    )
    return ApiResponse.ok(UploadedFileResponse.model_validate(stored, from_attributes=True))


@router.post(
    "/documents",
    response_model=ApiResponse[UploadedFileResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    _actor: HospitalActor,
    settings: SettingsDep,
    file: Annotated[UploadFile, File(description="A PDF or scanned image.")],
) -> ApiResponse[UploadedFileResponse]:
    """Upload one patient medical history document."""
    content = await file.read()
    stored = storage_service.store_document(
        content=content,
        content_type=_require_content_type(file),
        settings=settings,
    )
    return ApiResponse.ok(UploadedFileResponse.model_validate(stored, from_attributes=True))


def _require_content_type(file: UploadFile) -> str:
    """Return the declared MIME type, refusing an upload that omits it.

    Guessing from the extension would let a client rename an executable to
    ``.jpg`` and have the server agree with it.
    """
    if not file.content_type:
        msg = "the upload declared no content type; the file cannot be validated"
        raise UnprocessableError(msg)
    return file.content_type
