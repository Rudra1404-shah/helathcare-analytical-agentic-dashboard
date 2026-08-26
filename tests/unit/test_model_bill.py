"""Billing arithmetic.

Every rule here exists because a mismatch would surface as an Overcharging or
False Billing complaint, which is one of the categories the platform's grievance
mechanism exists to handle.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from src.domain.enums import PaymentStatus
from src.domain.models.bill import BillLineItem, money
from tests import factories


class TestMoneyRounding:
    """Monetary values are exact to two decimal places."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("10.005", "10.01"),
            ("10.004", "10.00"),
            ("0.125", "0.13"),
            ("100", "100.00"),
        ],
    )
    def test_half_up_rounding(self, raw: str, expected: str) -> None:
        """Half-up rounding is what invoices conventionally use."""
        assert money(Decimal(raw)) == Decimal(expected)


class TestLineItemTotals:
    """A line total must equal rate multiplied by quantity."""

    def test_computed_line_item_is_consistent(self) -> None:
        """The build helper computes the total rather than trusting a caller."""
        line = BillLineItem.build(description="X-Ray", rate="750.00", quantity="2")
        assert line.total == Decimal("1500.00")

    def test_incorrect_line_total_is_rejected(self) -> None:
        """A supplied total that does not reconcile must fail."""
        with pytest.raises(ValidationError, match="does not equal rate"):
            BillLineItem(
                description="X-Ray",
                rate=Decimal("750.00"),
                quantity=Decimal("2"),
                total=Decimal("1000.00"),
            )

    def test_fractional_quantity_is_supported(self) -> None:
        """Consumables are sometimes billed in fractional units."""
        line = BillLineItem.build(description="Oxygen", rate="10.00", quantity="2.5")
        assert line.total == Decimal("25.00")

    def test_zero_quantity_is_rejected(self) -> None:
        """A zero-quantity charge is meaningless."""
        with pytest.raises(ValidationError):
            BillLineItem.build(description="X", rate="10.00", quantity="0")

    def test_negative_rate_is_rejected(self) -> None:
        """Negative rates would be a refund, which is modelled separately."""
        with pytest.raises(ValidationError):
            BillLineItem.build(description="X", rate="-10.00", quantity="1")


class TestBillTotals:
    """Subtotal and grand total must reconcile exactly."""

    def test_valid_bill_is_accepted(self) -> None:
        """The default bill reconciles: 1000 + 180 - 100 = 1080."""
        bill = factories.build_bill()
        assert bill.grand_total == Decimal("1080.00")

    def test_subtotal_not_matching_line_items_is_rejected(self) -> None:
        """A subtotal that ignores the line items is a billing error."""
        with pytest.raises(ValidationError, match="does not equal the sum"):
            factories.build_bill(subtotal=Decimal("999.00"), grand_total=Decimal("1079.00"))

    def test_grand_total_not_matching_formula_is_rejected(self) -> None:
        """Grand total must be subtotal plus tax minus discount."""
        with pytest.raises(ValidationError, match="does not equal subtotal"):
            factories.build_bill(grand_total=Decimal("2000.00"))

    def test_discount_exceeding_subtotal_is_rejected(self) -> None:
        """A discount larger than the charge would produce a negative invoice."""
        with pytest.raises(ValidationError, match="cannot exceed"):
            factories.build_bill(discount_amount=Decimal("5000.00"), grand_total=Decimal("0.00"))

    def test_zero_tax_and_discount_is_accepted(self) -> None:
        """A plain invoice with no tax or discount reconciles."""
        bill = factories.build_bill(
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            grand_total=Decimal("1000.00"),
        )
        assert bill.grand_total == Decimal("1000.00")

    def test_bill_without_line_items_is_rejected(self) -> None:
        """An invoice must charge for at least one thing."""
        with pytest.raises(ValidationError):
            factories.build_bill(line_items=[])

    def test_multiple_line_items_reconcile(self) -> None:
        """Several charges sum into the subtotal."""
        # Arrange
        lines = [
            factories.build_line_item("Consultation", "500.00", "1"),
            factories.build_line_item("X-Ray", "750.00", "2"),
        ]

        # Act
        bill = factories.build_bill(
            line_items=lines,
            subtotal=Decimal("2000.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            grand_total=Decimal("2000.00"),
        )

        # Assert
        assert bill.subtotal == Decimal("2000.00")


class TestPaymentConsistency:
    """Payment status must agree with the amount actually paid."""

    def test_unpaid_bill_defaults_to_pending(self) -> None:
        """A new invoice is pending with nothing paid."""
        bill = factories.build_bill()
        assert bill.payment_status is PaymentStatus.PENDING
        assert bill.amount_paid == Decimal("0.00")

    def test_balance_due_is_computed(self) -> None:
        """Outstanding balance is grand total less what was paid."""
        bill = factories.build_bill(amount_paid=Decimal("80.00"))
        assert bill.balance_due == Decimal("1000.00")

    def test_overpayment_is_rejected(self) -> None:
        """Paying more than the invoice total indicates a reconciliation bug."""
        with pytest.raises(ValidationError, match="cannot exceed"):
            factories.build_bill(amount_paid=Decimal("99999.00"))

    def test_paid_status_requires_full_payment(self) -> None:
        """Marking an invoice PAID while money is outstanding hides debt."""
        with pytest.raises(ValidationError, match="requires amount_paid"):
            factories.build_bill(payment_status=PaymentStatus.PAID, amount_paid=Decimal("500.00"))

    def test_fully_paid_bill_is_accepted(self) -> None:
        """A settled invoice reconciles to a zero balance."""
        bill = factories.build_bill(
            payment_status=PaymentStatus.PAID, amount_paid=Decimal("1080.00")
        )
        assert bill.balance_due == Decimal("0.00")

    def test_partial_payment_is_accepted(self) -> None:
        """Partial settlement is a valid intermediate state."""
        bill = factories.build_bill(
            payment_status=PaymentStatus.PARTIALLY_PAID,
            amount_paid=Decimal("500.00"),
        )
        assert bill.balance_due == Decimal("580.00")
