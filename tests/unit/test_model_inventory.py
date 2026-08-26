"""Inventory rules: stock invariants and alert thresholds."""

import pytest
from pydantic import ValidationError

from src.domain.enums import InventoryCategory
from tests import factories


class TestStockInvariant:
    """Available stock can never exceed total stock."""

    def test_valid_stock_is_accepted(self) -> None:
        """The default inventory line is consistent."""
        item = factories.build_inventory_item()
        assert item.available_stock <= item.total_stock

    def test_available_exceeding_total_is_rejected(self) -> None:
        """Otherwise a hospital could advertise ICU beds it does not have.

        This is precisely the fragmentation the platform exists to eliminate.
        """
        with pytest.raises(ValidationError, match="cannot exceed"):
            factories.build_inventory_item(total_stock=10.0, available_stock=15.0)

    def test_available_equal_to_total_is_accepted(self) -> None:
        """A fully free resource is valid."""
        item = factories.build_inventory_item(total_stock=10.0, available_stock=10.0)
        assert item.in_use == 0.0

    def test_zero_available_is_accepted(self) -> None:
        """A fully occupied resource is valid."""
        item = factories.build_inventory_item(total_stock=10.0, available_stock=0.0)
        assert item.in_use == 10.0

    def test_negative_stock_is_rejected(self) -> None:
        """Negative stock is impossible."""
        with pytest.raises(ValidationError):
            factories.build_inventory_item(available_stock=-1.0)

    def test_invariant_holds_on_assignment(self) -> None:
        """Mutation must not be able to break the invariant."""
        # Arrange
        item = factories.build_inventory_item(total_stock=10.0, available_stock=5.0)

        # Act / Assert
        with pytest.raises(ValidationError):
            item.available_stock = 50.0


class TestSafetyThreshold:
    """The threshold that drives the Smart Alerts module."""

    def test_stock_above_threshold_raises_no_alert(self) -> None:
        """Comfortable stock is not an alert condition."""
        item = factories.build_inventory_item(available_stock=12.0, min_safety_threshold=5.0)
        assert item.is_below_threshold is False

    def test_stock_equal_to_threshold_raises_an_alert(self) -> None:
        """The boundary is inclusive; hitting the threshold must alert."""
        item = factories.build_inventory_item(available_stock=5.0, min_safety_threshold=5.0)
        assert item.is_below_threshold is True

    def test_stock_below_threshold_raises_an_alert(self) -> None:
        """Falling under the threshold must alert."""
        item = factories.build_inventory_item(available_stock=2.0, min_safety_threshold=5.0)
        assert item.is_below_threshold is True

    def test_negative_threshold_is_rejected(self) -> None:
        """A negative threshold could never trigger."""
        with pytest.raises(ValidationError):
            factories.build_inventory_item(min_safety_threshold=-1.0)


class TestUtilisation:
    """Derived figures the resource-prediction module reads."""

    def test_utilisation_is_computed(self) -> None:
        """Utilisation is the in-use fraction of total stock."""
        item = factories.build_inventory_item(total_stock=40.0, available_stock=10.0)
        assert item.utilisation_ratio == pytest.approx(0.75)

    def test_utilisation_of_empty_inventory_is_zero(self) -> None:
        """A zero-stock line must not divide by zero."""
        item = factories.build_inventory_item(total_stock=0.0, available_stock=0.0)
        assert item.utilisation_ratio == 0.0

    def test_fully_available_stock_has_zero_utilisation(self) -> None:
        """Nothing in use means zero utilisation."""
        item = factories.build_inventory_item(total_stock=10.0, available_stock=10.0)
        assert item.utilisation_ratio == 0.0


class TestInventoryCategories:
    """Every declared resource class must be usable."""

    @pytest.mark.parametrize("category", list(InventoryCategory))
    def test_all_categories_are_accepted(self, category: InventoryCategory) -> None:
        """Beds, oxygen, ventilators, medicines, and consumables all track here."""
        item = factories.build_inventory_item(category=category)
        assert item.category is category

    def test_fractional_oxygen_quantity_is_accepted(self) -> None:
        """Bulk oxygen is continuous, not countable, so fractions must work."""
        item = factories.build_inventory_item(
            category=InventoryCategory.OXYGEN_LITERS,
            total_stock=1000.5,
            available_stock=250.25,
        )
        assert item.available_stock == 250.25
