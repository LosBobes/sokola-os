"""Money as exact decimal. No floating point, ever, and no minor-unit master.

Amounts are :class:`decimal.Decimal` with a scale of 2, stored as
``NUMERIC(18,2)`` and carried across the API, imports, exports and events as a
*decimal string* alongside an ISO 4217 code (execution contract §3).

The previous model stored integer minor units. That is exact, and nothing was
losing precision, but it is the "parallel minor-unit master" §3 forbids: every
boundary had to remember the scaling, every reader had to know that 12500 means
125,00, and any place that forgot produced an amount a hundred times wrong that
still looked plausible. Decimal removes the encoding rather than documenting it.

Floats are rejected outright rather than converted: ``Decimal(0.1)`` is
0.1000000000000000055511151231257827, and accepting one would put that in a
ledger.
"""

from __future__ import annotations

import decimal
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BeforeValidator, PlainSerializer

from app.config import get_settings

# Two decimal places, matching NUMERIC(18,2). RSD and EUR both use two.
SCALE = Decimal("0.01")
MAX_DIGITS = 18


def parse_amount(value: Any) -> Decimal:
    """Coerce an API/import value to an exact amount, or raise ``ValueError``.

    Accepts a decimal string (the wire format), an ``int``, or a ``Decimal``.
    Rejects ``float`` and rejects more precision than the scale allows, so a
    request asking to charge 10.005 is refused rather than silently rounded.
    """
    if isinstance(value, bool):  # bool is an int subclass; never an amount
        raise ValueError("amount must be a decimal string, not a boolean")
    if isinstance(value, float):
        raise ValueError("amount must be a decimal string, not a float")
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, int):
        amount = Decimal(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("amount must not be empty")
        try:
            amount = Decimal(text)
        except decimal.InvalidOperation as exc:
            raise ValueError(f"{value!r} is not a decimal amount") from exc
    else:
        raise ValueError(f"amount must be a decimal string, got {type(value).__name__}")

    if not amount.is_finite():
        raise ValueError("amount must be finite")
    if -amount.as_tuple().exponent > 2:  # type: ignore[operator]
        raise ValueError("amount must not have more than two decimal places")
    if len(amount.as_tuple().digits) > MAX_DIGITS:
        raise ValueError("amount is out of range")
    return amount.quantize(SCALE)


def format_amount(value: Decimal) -> str:
    """The wire format: a plain decimal string, always two places, never
    scientific notation."""
    return f"{value.quantize(SCALE):f}"


def zero() -> Decimal:
    return Decimal("0.00")


# The API type. Validation accepts the wire format and normalises it;
# serialisation always emits two places, so "125" never reaches a client as an
# amount that could be read as 1,25.
MoneyAmount = Annotated[
    Decimal,
    BeforeValidator(parse_amount),
    PlainSerializer(format_amount, return_type=str, when_used="json"),
]


@dataclass(frozen=True, slots=True)
class Money:
    """An amount and its currency, for arithmetic that must not mix the two."""

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", parse_amount(self.amount))
        if len(self.currency) != 3 or not self.currency.isupper():
            raise ValueError("currency must be a 3-letter uppercase ISO 4217 code")

    @classmethod
    def zero(cls, currency: str | None = None) -> Money:
        return cls(Decimal("0.00"), currency or get_settings().default_currency)

    def add(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def subtract(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def _assert_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError("cannot combine amounts of different currencies")

    def format(self) -> str:
        """For display, in the local convention: a comma decimal separator."""
        return f"{format_amount(self.amount).replace('.', ',')} {self.currency}"
