"""The ``bills`` collection: itemised invoices for a patient case.

Backs the Hospital Billing Form. Monetary amounts use :class:`~decimal.Decimal`
rather than ``float`` so that totals are exact -- a rounding drift here would
surface directly as an Overcharging or False Billing complaint.
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import ClassVar, Self

import pymongo
from beanie import PydanticObjectId
from pydantic import Field, model_validator
from pymongo import IndexModel

from src.domain.enums import PaymentMode, PaymentStatus
from src.domain.models.base import TimestampedDocument, ValueObject, utcnow
from src.domain.types import Money, ShortText

__all__ = ["Bill", "BillLineItem", "money"]

MONEY_QUANTUM = Decimal("0.01")
MAX_MONEY_DIGITS = 14


def money(value: Decimal | int | str) -> Decimal:
    """Round a monetary value to two decimal places, half-up."""
    return Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


class BillLineItem(ValueObject):
    """A single charge on an invoice."""

    description: ShortText
    rate: Money = Field(ge=Decimal("0"), max_digits=MAX_MONEY_DIGITS, decimal_places=2)
    quantity: Money = Field(gt=Decimal("0"), max_digits=MAX_MONEY_DIGITS, decimal_places=3)
    total: Money = Field(ge=Decimal("0"), max_digits=MAX_MONEY_DIGITS, decimal_places=2)

    @model_validator(mode="after")
    def _validate_line_total(self) -> Self:
        """The line total must equal rate multiplied by quantity."""
        expected = money(self.rate * self.quantity)
        if money(self.total) != expected:
            msg = (
                f"line total {self.total} does not equal rate x quantity "
                f"({self.rate} x {self.quantity} = {expected})"
            )
            raise ValueError(msg)
        return self

    @classmethod
    def build(cls, description: str, rate: Decimal | str, quantity: Decimal | str) -> Self:
        """Create a line item with its total computed rather than supplied."""
        rate_value = Decimal(rate)
        quantity_value = Decimal(quantity)
        return cls(
            description=description,
            rate=rate_value,
            quantity=quantity_value,
            total=money(rate_value * quantity_value),
        )


class Bill(TimestampedDocument):
    """An invoice raised against a patient case."""

    invoice_no: str = Field(
        min_length=3,
        max_length=40,
        description="Human-facing invoice number, unique within the hospital.",
    )
    hospital_id: PydanticObjectId
    case_id: PydanticObjectId
    patient_id: PydanticObjectId

    line_items: list[BillLineItem] = Field(
        min_length=1, description="An invoice must charge for at least one thing."
    )

    subtotal: Money = Field(ge=Decimal("0"), max_digits=MAX_MONEY_DIGITS, decimal_places=2)
    tax_amount: Money = Field(
        default=Decimal("0.00"), ge=Decimal("0"), max_digits=MAX_MONEY_DIGITS, decimal_places=2
    )
    discount_amount: Money = Field(
        default=Decimal("0.00"), ge=Decimal("0"), max_digits=MAX_MONEY_DIGITS, decimal_places=2
    )
    grand_total: Money = Field(ge=Decimal("0"), max_digits=MAX_MONEY_DIGITS, decimal_places=2)

    payment_status: PaymentStatus = Field(default=PaymentStatus.PENDING)
    payment_mode: PaymentMode | None = Field(default=None)
    amount_paid: Money = Field(
        default=Decimal("0.00"), ge=Decimal("0"), max_digits=MAX_MONEY_DIGITS, decimal_places=2
    )
    issued_at: datetime = Field(default_factory=utcnow)
    settled_at: datetime | None = Field(default=None)

    class Settings:
        """Beanie collection configuration."""

        name = "bills"
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel(
                [("hospital_id", pymongo.ASCENDING), ("invoice_no", pymongo.ASCENDING)],
                unique=True,
                name="uq_bills_hospital_invoice",
            ),
            IndexModel([("case_id", pymongo.ASCENDING)], name="ix_bills_case"),
            IndexModel([("patient_id", pymongo.ASCENDING)], name="ix_bills_patient"),
            IndexModel([("payment_status", pymongo.ASCENDING)], name="ix_bills_payment_status"),
        ]

    @model_validator(mode="after")
    def _validate_subtotal_matches_line_items(self) -> Self:
        """The subtotal must be the exact sum of the line item totals."""
        expected = money(sum((item.total for item in self.line_items), Decimal("0")))
        if money(self.subtotal) != expected:
            msg = f"subtotal {self.subtotal} does not equal the sum of line items ({expected})"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_grand_total(self) -> Self:
        """Grand total must equal subtotal plus tax minus discount."""
        if self.discount_amount > self.subtotal:
            msg = (
                f"discount_amount ({self.discount_amount}) cannot exceed subtotal ({self.subtotal})"
            )
            raise ValueError(msg)

        expected = money(self.subtotal + self.tax_amount - self.discount_amount)
        if money(self.grand_total) != expected:
            msg = (
                f"grand_total {self.grand_total} does not equal subtotal + tax - discount "
                f"({self.subtotal} + {self.tax_amount} - {self.discount_amount} = {expected})"
            )
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _validate_payment_consistency(self) -> Self:
        """Keep the payment status consistent with the amount actually paid."""
        if self.amount_paid > self.grand_total:
            msg = f"amount_paid ({self.amount_paid}) cannot exceed grand_total ({self.grand_total})"
            raise ValueError(msg)
        if self.payment_status is PaymentStatus.PAID and self.amount_paid != self.grand_total:
            msg = "payment_status PAID requires amount_paid to equal grand_total"
            raise ValueError(msg)
        return self

    @property
    def balance_due(self) -> Decimal:
        """Return the amount still outstanding on this invoice."""
        return money(self.grand_total - self.amount_paid)
