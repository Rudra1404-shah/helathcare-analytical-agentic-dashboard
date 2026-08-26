"""Billing Form schemas.

The create request accepts line items *without* their computed totals and
derives subtotal and grand total server-side. Letting a client supply the totals
would make an overcharging complaint indistinguishable from a rounding bug.
"""

from datetime import datetime
from decimal import Decimal
from typing import Self

from beanie import PydanticObjectId
from pydantic import Field, model_validator

from src.domain.enums import PaymentMode, PaymentStatus
from src.domain.models.bill import MAX_MONEY_DIGITS, BillLineItem, money
from src.domain.schemas.common import IdentifiedResponse, RequestSchema
from src.domain.types import ShortText

__all__ = [
    "BillCreateRequest",
    "BillLineItemRequest",
    "BillResponse",
    "PaymentRecordRequest",
]


class BillLineItemRequest(RequestSchema):
    """One charge on an invoice. The total is computed, never supplied."""

    description: ShortText
    rate: Decimal = Field(ge=Decimal("0"), max_digits=MAX_MONEY_DIGITS, decimal_places=2)
    quantity: Decimal = Field(gt=Decimal("0"), max_digits=MAX_MONEY_DIGITS, decimal_places=3)

    def to_line_item(self) -> BillLineItem:
        """Build the stored line item with its total computed."""
        return BillLineItem.build(
            description=self.description, rate=self.rate, quantity=self.quantity
        )

    @property
    def computed_total(self) -> Decimal:
        """Return rate multiplied by quantity, rounded to two places."""
        return money(self.rate * self.quantity)


class BillCreateRequest(RequestSchema):
    """Billing Form."""

    invoice_no: str = Field(min_length=3, max_length=40)
    case_id: PydanticObjectId
    patient_id: PydanticObjectId
    line_items: list[BillLineItemRequest] = Field(
        min_length=1, description="An invoice must charge for at least one thing."
    )
    tax_amount: Decimal = Field(
        default=Decimal("0.00"), ge=Decimal("0"), max_digits=MAX_MONEY_DIGITS, decimal_places=2
    )
    discount_amount: Decimal = Field(
        default=Decimal("0.00"), ge=Decimal("0"), max_digits=MAX_MONEY_DIGITS, decimal_places=2
    )
    payment_mode: PaymentMode | None = Field(default=None)

    @property
    def computed_subtotal(self) -> Decimal:
        """Return the sum of the line item totals."""
        return money(sum((item.computed_total for item in self.line_items), Decimal("0")))

    @property
    def computed_grand_total(self) -> Decimal:
        """Return subtotal plus tax minus discount."""
        return money(self.computed_subtotal + self.tax_amount - self.discount_amount)

    @model_validator(mode="after")
    def _validate_discount_within_subtotal(self) -> Self:
        """A discount cannot exceed what is being charged."""
        subtotal = self.computed_subtotal
        if self.discount_amount > subtotal:
            msg = f"discount_amount ({self.discount_amount}) cannot exceed subtotal ({subtotal})"
            raise ValueError(msg)
        return self


class PaymentRecordRequest(RequestSchema):
    """Record a payment against an existing invoice."""

    amount: Decimal = Field(gt=Decimal("0"), max_digits=MAX_MONEY_DIGITS, decimal_places=2)
    payment_mode: PaymentMode
    paid_at: datetime | None = Field(default=None)
    reference: str | None = Field(default=None, max_length=100)


class BillResponse(IdentifiedResponse):
    """An invoice as returned by the API."""

    invoice_no: str
    hospital_id: PydanticObjectId
    case_id: PydanticObjectId
    patient_id: PydanticObjectId
    line_items: list[BillLineItem]
    subtotal: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    grand_total: Decimal
    amount_paid: Decimal
    payment_status: PaymentStatus
    payment_mode: PaymentMode | None = None
    issued_at: datetime
    settled_at: datetime | None = None
