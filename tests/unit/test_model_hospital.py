"""Hospital, zone, and department rules, plus GeoJSON handling."""

from datetime import date

import pytest
from pydantic import ValidationError

from src.domain.enums import AccreditationStatus
from src.domain.models.base import GeoLocation
from tests import factories


class TestGeoLocation:
    """GeoJSON points must be valid and correctly ordered."""

    def test_from_lat_lon_flips_into_geojson_order(self) -> None:
        """MongoDB expects [longitude, latitude]; humans quote the reverse."""
        # Act
        point = GeoLocation.from_lat_lon(latitude=19.0760, longitude=72.8777)

        # Assert
        assert point.coordinates == (72.8777, 19.0760)
        assert point.latitude == 19.0760
        assert point.longitude == 72.8777
        assert point.type == "Point"

    @pytest.mark.parametrize("latitude", [-90.0, 0.0, 90.0])
    def test_latitude_bounds_are_inclusive(self, latitude: float) -> None:
        """The poles are valid latitudes."""
        assert GeoLocation.from_lat_lon(latitude=latitude, longitude=0.0) is not None

    @pytest.mark.parametrize("latitude", [-90.1, 90.1, 1000.0])
    def test_out_of_range_latitude_is_rejected(self, latitude: float) -> None:
        """An impossible latitude would break geospatial queries."""
        with pytest.raises(ValidationError, match="latitude"):
            GeoLocation.from_lat_lon(latitude=latitude, longitude=0.0)

    @pytest.mark.parametrize("longitude", [-180.1, 180.1])
    def test_out_of_range_longitude_is_rejected(self, longitude: float) -> None:
        """An impossible longitude would break geospatial queries."""
        with pytest.raises(ValidationError, match="longitude"):
            GeoLocation.from_lat_lon(latitude=0.0, longitude=longitude)


class TestHospitalCapacity:
    """Specialised beds are a subset of the sanctioned total."""

    def test_valid_capacity_is_accepted(self) -> None:
        """The default factory capacity is internally consistent."""
        capacity = factories.build_capacity()
        assert capacity.icu_beds + capacity.emergency_beds <= capacity.total_sanctioned_beds

    def test_icu_plus_emergency_exceeding_total_is_rejected(self) -> None:
        """Otherwise a hospital could advertise beds it was never sanctioned."""
        with pytest.raises(ValidationError, match="cannot exceed"):
            factories.build_capacity(total_sanctioned_beds=50, icu_beds=40, emergency_beds=20)

    def test_icu_equal_to_total_is_accepted(self) -> None:
        """A fully-ICU facility is legitimate."""
        capacity = factories.build_capacity(total_sanctioned_beds=30, icu_beds=30, emergency_beds=0)
        assert capacity.icu_beds == 30

    def test_negative_bed_count_is_rejected(self) -> None:
        """Negative capacity is impossible."""
        with pytest.raises(ValidationError):
            factories.build_capacity(icu_beds=-1)

    def test_negative_oxygen_capacity_is_rejected(self) -> None:
        """Negative oxygen storage is impossible."""
        with pytest.raises(ValidationError):
            factories.build_capacity(oxygen_bulk_capacity_liters=-5.0)


class TestHospitalAccreditation:
    """Accreditation state and its supporting dates."""

    def test_pending_hospital_needs_no_accreditation_date(self) -> None:
        """A hospital awaiting accreditation has no grant date yet."""
        hospital = factories.build_hospital()
        assert hospital.accreditation_status is AccreditationStatus.PENDING
        assert hospital.accredited_on is None

    @pytest.mark.parametrize(
        "status", [AccreditationStatus.NABH, AccreditationStatus.STATE_LICENSED]
    )
    def test_granted_accreditation_requires_a_date(self, status: AccreditationStatus) -> None:
        """An accredited hospital must record when accreditation was granted."""
        with pytest.raises(ValidationError, match="accredited_on is required"):
            factories.build_hospital(accreditation_status=status)

    def test_licence_expiry_before_grant_is_rejected(self) -> None:
        """A licence cannot expire before it was issued."""
        with pytest.raises(ValidationError, match="cannot precede"):
            factories.build_hospital(
                accreditation_status=AccreditationStatus.NABH,
                accredited_on=date(2024, 6, 1),
                license_valid_until=date(2023, 6, 1),
            )

    def test_valid_accredited_hospital_is_accepted(self) -> None:
        """A properly accredited hospital passes."""
        hospital = factories.build_hospital(
            accreditation_status=AccreditationStatus.NABH,
            accredited_on=date(2024, 6, 1),
            license_valid_until=date(2027, 6, 1),
        )
        assert hospital.is_blacklisted is False

    def test_blacklisted_hospital_reports_itself(self) -> None:
        """The blacklist flag drives enforcement elsewhere."""
        hospital = factories.build_hospital(accreditation_status=AccreditationStatus.BLACKLISTED)
        assert hospital.is_blacklisted is True

    def test_licence_number_is_upper_cased(self) -> None:
        """Licence numbers normalise so lookups are case-insensitive."""
        hospital = factories.build_hospital(license_no="mh-lic-999")
        assert hospital.license_no == "MH-LIC-999"


class TestZone:
    """Zone rules."""

    def test_valid_zone_is_accepted(self) -> None:
        """The default zone is valid."""
        zone = factories.build_zone()
        assert zone.population_covered == 250_000
        assert zone.is_active is True

    def test_negative_population_is_rejected(self) -> None:
        """A negative denominator would corrupt per-capita analytics."""
        with pytest.raises(ValidationError):
            factories.build_zone(population_covered=-1)

    def test_zero_population_is_accepted(self) -> None:
        """A newly created zone may not have census data yet."""
        assert factories.build_zone(population_covered=0).population_covered == 0

    def test_short_zone_code_is_rejected(self) -> None:
        """A one-character zone code is not a usable identifier."""
        with pytest.raises(ValidationError):
            factories.build_zone(zone_code="X")


class TestDepartment:
    """Department rules."""

    def test_valid_department_is_accepted(self) -> None:
        """The default department is valid."""
        department = factories.build_department()
        assert department.code == "CARD"
        assert department.bed_count == 30

    def test_negative_bed_count_is_rejected(self) -> None:
        """Negative bed allocation is impossible."""
        with pytest.raises(ValidationError):
            factories.build_department(bed_count=-5)

    def test_department_without_hod_is_accepted(self) -> None:
        """A department may be registered before its head is appointed."""
        assert factories.build_department().hod_doctor_id is None

    def test_short_code_is_rejected(self) -> None:
        """A single-character department code is not usable."""
        with pytest.raises(ValidationError):
            factories.build_department(code="C")
