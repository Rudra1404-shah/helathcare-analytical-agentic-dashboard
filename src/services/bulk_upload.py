"""Excel and CSV parsing for the patient bulk-upload form.

Every cell is read as **raw text**. Spreadsheet readers that infer types turn a
Medical Record Number of ``0012`` into the integer ``12``, a twelve-digit
National ID into ``1.23457e+11``, and a phone number with a leading zero into
something that no longer dials. For identity columns that is silent data
corruption, so the reader here coerces nothing and leaves every value as the
string the operator typed. :class:`PatientBulkUploadRow` then does the real
validation.

Rows are validated independently: a malformed row is reported and skipped
rather than failing the whole file, so a thousand-row upload with two bad rows
still imports nine hundred and ninety-eight patients.
"""

import csv
import io
from datetime import date, datetime
from typing import Any

from openpyxl import load_workbook
from pydantic import ValidationError

from src.core.errors import UnprocessableError
from src.domain.schemas.patient import BulkUploadRowError, PatientBulkUploadRow

__all__ = [
    "CSV_EXTENSIONS",
    "EXCEL_EXTENSIONS",
    "REQUIRED_COLUMNS",
    "ParsedRows",
    "parse_upload",
]

EXCEL_EXTENSIONS = (".xlsx", ".xlsm")
CSV_EXTENSIONS = (".csv", ".txt")

REQUIRED_COLUMNS = ("mrn", "full_name", "gender")
"""Columns without which a row cannot identify a patient at all."""

_HEADER_ALIASES: dict[str, str] = {
    "medical_record_number": "mrn",
    "medical record number": "mrn",
    "patient_name": "full_name",
    "name": "full_name",
    "dob": "date_of_birth",
    "date of birth": "date_of_birth",
    "age": "age_years",
    "mobile": "phone",
    "contact": "phone",
    "blood group": "blood_group",
    "national id": "national_id",
    "aadhaar": "national_id",
    "allergies": "allergies_csv",
    "conditions": "conditions_csv",
    "pre_existing_conditions": "conditions_csv",
    "emergency_contact": "emergency_contact_name",
    "emergency_name": "emergency_contact_name",
    "emergency_phone": "emergency_contact_phone",
    "emergency_relationship": "emergency_contact_relationship",
}
"""Spreadsheet headers seen in the wild, mapped onto schema field names."""

_ROW_FIELDS = frozenset(PatientBulkUploadRow.model_fields) - {"row_number"}


class ParsedRows:
    """The outcome of reading a file: valid rows plus per-row rejections."""

    def __init__(
        self,
        rows: list[PatientBulkUploadRow],
        errors: list[BulkUploadRowError],
        total_rows: int,
    ) -> None:
        self.rows = rows
        self.errors = errors
        self.total_rows = total_rows


def parse_upload(content: bytes, filename: str) -> ParsedRows:
    """Parse an uploaded patient file into validated rows.

    Args:
        content: The raw uploaded bytes.
        filename: Original filename, used only to pick a reader.

    Returns:
        Valid rows and a rejection for every row that failed.

    Raises:
        UnprocessableError: If the file type is unsupported, unreadable, or
            missing a column a patient cannot be identified without.
    """
    lowered = filename.lower()
    if lowered.endswith(EXCEL_EXTENSIONS):
        raw_rows = _read_excel(content)
    elif lowered.endswith(CSV_EXTENSIONS):
        raw_rows = _read_csv(content)
    else:
        supported = ", ".join((*EXCEL_EXTENSIONS, *CSV_EXTENSIONS))
        msg = f"unsupported file type '{filename}'; upload one of: {supported}"
        raise UnprocessableError(msg)

    if not raw_rows:
        msg = "the uploaded file has a header row but no patient rows"
        raise UnprocessableError(msg)

    _require_identifying_columns(raw_rows[0])
    return _validate_rows(raw_rows)


# --------------------------------------------------------------------------- #
# Readers
# --------------------------------------------------------------------------- #
def _read_excel(content: bytes) -> list[dict[str, str]]:
    """Read the first worksheet, coercing every cell to text."""
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises a wide family of parse errors
        msg = "the uploaded workbook could not be read; is it a valid .xlsx file?"
        raise UnprocessableError(msg) from exc

    try:
        sheet = workbook.worksheets[0]
        rows = sheet.iter_rows(values_only=True)
        header = next(rows, None)
        if header is None:
            msg = "the uploaded workbook is empty"
            raise UnprocessableError(msg)

        columns = _normalise_header([_stringify(cell) for cell in header])
        return [
            record
            for values in rows
            if (record := _zip_row(columns, [_stringify(cell) for cell in values]))
        ]
    finally:
        workbook.close()


def _read_csv(content: bytes) -> list[dict[str, str]]:
    """Read a delimited text file, leaving every value as text."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        msg = "the uploaded file is not valid UTF-8 text; re-export it as UTF-8 CSV"
        raise UnprocessableError(msg) from exc

    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if header is None:
        msg = "the uploaded file is empty"
        raise UnprocessableError(msg)

    columns = _normalise_header(header)
    return [record for values in reader if (record := _zip_row(columns, values))]


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
def _stringify(cell: Any) -> str:
    """Render one spreadsheet cell as the text an operator would have typed.

    ``openpyxl`` hands back real ``datetime`` objects for date-formatted cells
    and ``int``/``float`` for numeric ones. Dates become ISO strings; a numeric
    cell that is a whole number drops its ``.0`` so ``42.0`` does not reach the
    age field as ``"42.0"``.
    """
    if cell is None:
        return ""
    if isinstance(cell, datetime):
        return cell.date().isoformat()
    if isinstance(cell, date):
        return cell.isoformat()
    if isinstance(cell, float) and cell.is_integer():
        return str(int(cell))
    return str(cell).strip()


def _normalise_header(header: list[str]) -> list[str]:
    """Lower-case, underscore, and alias each column name."""
    columns: list[str] = []
    for raw in header:
        key = raw.strip().lower().replace(" ", "_")
        columns.append(_HEADER_ALIASES.get(key, _HEADER_ALIASES.get(raw.strip().lower(), key)))
    return columns


def _zip_row(columns: list[str], values: list[str]) -> dict[str, str]:
    """Pair a row's values with their column names, dropping blank rows."""
    record = {
        column: str(value).strip()
        for column, value in zip(columns, values, strict=False)
        if column in _ROW_FIELDS and str(value).strip()
    }
    return record


def _require_identifying_columns(sample: dict[str, str]) -> None:
    """Fail the whole file when a column no row can do without is absent.

    A missing ``mrn`` column would reject every row individually with the same
    message; saying it once, about the file, is more useful.
    """
    missing = [column for column in REQUIRED_COLUMNS if column not in sample]
    if missing:
        msg = (
            f"the uploaded file is missing required column(s): {', '.join(missing)}. "
            f"Expected headers include: {', '.join(REQUIRED_COLUMNS)}"
        )
        raise UnprocessableError(msg)


def _validate_rows(raw_rows: list[dict[str, str]]) -> ParsedRows:
    """Validate every row independently, collecting failures rather than raising."""
    rows: list[PatientBulkUploadRow] = []
    errors: list[BulkUploadRowError] = []

    for offset, record in enumerate(raw_rows):
        row_number = offset + 2  # +1 for the header, +1 because files are 1-indexed
        try:
            # Validated from a mapping rather than splatted keywords: every
            # value here is raw text, and Pydantic is what coerces it into the
            # declared types.
            rows.append(PatientBulkUploadRow.model_validate({"row_number": row_number, **record}))
        except ValidationError as exc:
            errors.extend(_row_errors(row_number, exc))

    return ParsedRows(rows=rows, errors=errors, total_rows=len(raw_rows))


def _row_errors(row_number: int, exc: ValidationError) -> list[BulkUploadRowError]:
    """Convert one row's validation failure into reportable errors.

    Only the first problem per row is reported. An operator fixes a spreadsheet
    row by row, and five cascading messages about the same cell is noise.
    """
    first = exc.errors()[0]
    field = ".".join(str(part) for part in first["loc"]) or None
    return [BulkUploadRowError(row_number=row_number, field=field, message=first["msg"])]
