"""Excel and CSV patient bulk upload.

The type-preservation tests matter most. A spreadsheet reader that infers types
turns an MRN of ``0012`` into ``12`` and a twelve-digit National ID into
``1.23457e+11``. For identity columns that is silent corruption -- the patient
is still imported, but under the wrong key, and their cross-hospital history
never resolves.
"""

import io
from typing import Any

import pytest
from httpx import AsyncClient
from openpyxl import Workbook

from tests.integration.conftest import auth
from tests.integration.world import World, payload

pytestmark = pytest.mark.integration

CSV_HEADER = "mrn,full_name,gender,age_years,phone,blood_group,allergies_csv\n"


def workbook_bytes(rows: list[list[Any]], header: list[str]) -> bytes:
    """Build an in-memory .xlsx file from a header and rows."""
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


async def upload(client: AsyncClient, world: World, name: str, content: bytes) -> Any:
    """Post a file to the bulk endpoint and return the report."""
    return payload(
        await client.post(
            f"/api/v1/hospitals/{world.hospital_id}/patients/bulk",
            headers=auth(world.admin_token),
            files={"file": (name, content, "application/octet-stream")},
        )
    )


class TestCsvUpload:
    """Delimited text files."""

    async def test_valid_rows_are_imported(self, client: AsyncClient, world: World) -> None:
        """A clean file imports every row and reports no errors."""
        # Arrange
        content = (
            CSV_HEADER
            + "MRN-BULK-1,Rohan Mehta,MALE,34,+919820100001,A+,Peanuts;Dust\n"
            + "MRN-BULK-2,Priya Nair,FEMALE,28,+919820100002,O-,\n"
        ).encode("utf-8")

        # Act
        report = await upload(client, world, "patients.csv", content)

        # Assert
        assert report == {"total_rows": 2, "accepted": 2, "rejected": 0, "errors": []}

    async def test_semicolon_separated_allergies_are_split(
        self, client: AsyncClient, world: World
    ) -> None:
        """A single spreadsheet cell becomes a list."""
        # Act
        patients = payload(
            await client.get(
                f"/api/v1/hospitals/{world.hospital_id}/patients",
                headers=auth(world.admin_token),
                params={"search": "MRN-BULK-1"},
            )
        )

        # Assert
        assert patients["items"][0]["allergies"] == ["Peanuts", "Dust"]

    async def test_a_bad_row_is_reported_and_the_rest_still_import(
        self, client: AsyncClient, world: World
    ) -> None:
        """One malformed row must not cost a thousand good ones."""
        # Arrange
        content = (
            CSV_HEADER
            + "MRN-BULK-3,Anil Kapoor,MALE,45,+919820100003,B+,\n"
            + "MRN-BULK-4,Bad Gender Person,NOTAGENDER,30,+919820100004,A+,\n"
            + "MRN-BULK-5,Kavita Rao,FEMALE,52,+919820100005,AB+,\n"
        ).encode("utf-8")

        # Act
        report = await upload(client, world, "patients.csv", content)

        # Assert
        assert report["total_rows"] == 3
        assert report["accepted"] == 2
        assert report["rejected"] == 1
        assert report["errors"][0]["row_number"] == 3
        assert report["errors"][0]["field"] == "gender"

    async def test_duplicate_mrn_is_reported_as_a_row_error(
        self, client: AsyncClient, world: World
    ) -> None:
        """Re-uploading a file adds the new rows and reports the old ones."""
        # Arrange
        content = (
            CSV_HEADER
            + "MRN-BULK-1,Rohan Mehta,MALE,34,+919820100001,A+,\n"
            + "MRN-BULK-6,Nikhil Sharma,MALE,61,+919820100006,O+,\n"
        ).encode("utf-8")

        # Act
        report = await upload(client, world, "patients.csv", content)

        # Assert
        assert report["accepted"] == 1
        assert report["rejected"] == 1
        assert "already registered" in report["errors"][0]["message"]

    async def test_a_file_missing_an_identifying_column_is_refused_whole(
        self, client: AsyncClient, world: World
    ) -> None:
        """Saying it once about the file beats saying it on every row."""
        # Arrange
        content = b"full_name,gender,age_years\nNo MRN Person,MALE,20\n"

        # Act
        response = await client.post(
            f"/api/v1/hospitals/{world.hospital_id}/patients/bulk",
            headers=auth(world.admin_token),
            files={"file": ("patients.csv", content, "text/csv")},
        )

        # Assert
        assert response.status_code == 422
        assert "mrn" in response.json()["error"]

    async def test_an_unsupported_file_type_is_refused(
        self, client: AsyncClient, world: World
    ) -> None:
        """A PDF is not a patient list."""
        # Act
        response = await client.post(
            f"/api/v1/hospitals/{world.hospital_id}/patients/bulk",
            headers=auth(world.admin_token),
            files={"file": ("patients.pdf", b"%PDF-1.4", "application/pdf")},
        )

        # Assert
        assert response.status_code == 422
        assert "unsupported file type" in response.json()["error"]

    async def test_header_aliases_are_accepted(self, client: AsyncClient, world: World) -> None:
        """Real hospital exports do not use the schema's field names."""
        # Arrange
        content = (
            b"Medical Record Number,Patient Name,gender,Age,Mobile\n"
            b"MRN-ALIAS-1,Sneha Pillai,FEMALE,37,+919820100007\n"
        )

        # Act
        report = await upload(client, world, "export.csv", content)

        # Assert
        assert report["accepted"] == 1


class TestExcelUpload:
    """Workbook files, where type coercion does the real damage."""

    async def test_xlsx_rows_are_imported(self, client: AsyncClient, world: World) -> None:
        """The .xlsx reader produces the same result as the CSV one."""
        # Arrange
        content = workbook_bytes(
            [["MRN-XL-1", "Farah Khan", "FEMALE", 39, "+919820100010", "A-"]],
            ["mrn", "full_name", "gender", "age_years", "phone", "blood_group"],
        )

        # Act
        report = await upload(client, world, "patients.xlsx", content)

        # Assert
        assert report["accepted"] == 1

    async def test_a_leading_zero_mrn_survives_the_import(
        self, client: AsyncClient, world: World
    ) -> None:
        """This is the whole reason the reader coerces nothing.

        A type-inferring reader stores ``0012`` as the integer ``12``, and the
        patient's records are then filed under an MRN that does not exist.
        """
        # Arrange
        content = workbook_bytes(
            [["0012", "Zero Prefix Patient", "MALE", 50, "+919820100011", "O+"]],
            ["mrn", "full_name", "gender", "age_years", "phone", "blood_group"],
        )

        # Act
        report = await upload(client, world, "leading_zero.xlsx", content)
        patients = payload(
            await client.get(
                f"/api/v1/hospitals/{world.hospital_id}/patients",
                headers=auth(world.admin_token),
                params={"search": "0012"},
            )
        )

        # Assert
        assert report["accepted"] == 1
        assert patients["items"][0]["mrn"] == "0012"

    async def test_a_numeric_age_cell_does_not_arrive_as_a_float(
        self, client: AsyncClient, world: World
    ) -> None:
        """A whole-number cell must not reach the age field as ``42.0``."""
        # Arrange
        content = workbook_bytes(
            [["MRN-XL-AGE", "Float Age Patient", "FEMALE", 42.0, "+919820100012", "B-"]],
            ["mrn", "full_name", "gender", "age_years", "phone", "blood_group"],
        )

        # Act
        report = await upload(client, world, "float_age.xlsx", content)
        patients = payload(
            await client.get(
                f"/api/v1/hospitals/{world.hospital_id}/patients",
                headers=auth(world.admin_token),
                params={"search": "MRN-XL-AGE"},
            )
        )

        # Assert
        assert report["accepted"] == 1
        assert patients["items"][0]["age_years"] == 42

    async def test_a_national_id_column_links_to_the_citizen_account(
        self, client: AsyncClient, world: World, citizen: dict[str, Any]
    ) -> None:
        """A bulk-imported patient joins the citizen's unified record."""
        # Arrange
        content = workbook_bytes(
            [["MRN-XL-NID", "Asha Kulkarni", "FEMALE", 41, citizen["national_id"]]],
            ["mrn", "full_name", "gender", "age_years", "national_id"],
        )

        # Act
        report = await upload(client, world, "with_ids.xlsx", content)
        patients = payload(
            await client.get(
                f"/api/v1/hospitals/{world.hospital_id}/patients",
                headers=auth(world.admin_token),
                params={"search": "MRN-XL-NID"},
            )
        )

        # Assert
        assert report["accepted"] == 1
        assert patients["items"][0]["citizen_user_id"] == citizen["id"]

    async def test_an_empty_workbook_is_refused(self, client: AsyncClient, world: World) -> None:
        """A header with no rows is a mistake worth naming."""
        # Arrange
        content = workbook_bytes([], ["mrn", "full_name", "gender"])

        # Act
        response = await client.post(
            f"/api/v1/hospitals/{world.hospital_id}/patients/bulk",
            headers=auth(world.admin_token),
            files={"file": ("empty.xlsx", content, "application/octet-stream")},
        )

        # Assert
        assert response.status_code == 422
        assert "no patient rows" in response.json()["error"]

    async def test_a_corrupt_workbook_is_refused_clearly(
        self, client: AsyncClient, world: World
    ) -> None:
        """A truncated upload should not surface as a 500."""
        # Act
        response = await client.post(
            f"/api/v1/hospitals/{world.hospital_id}/patients/bulk",
            headers=auth(world.admin_token),
            files={
                "file": (
                    "broken.xlsx",
                    b"PK\x03\x04 not really a workbook",
                    "application/octet-stream",
                )
            },
        )

        # Assert
        assert response.status_code == 422
        assert "could not be read" in response.json()["error"]
