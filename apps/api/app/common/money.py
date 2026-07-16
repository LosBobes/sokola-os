"""Money as integer minor units. No floating point, ever.

An amount is an ``int`` count of the currency's minor unit (para for RSD, cents
for EUR). Rendering to a human string happens at the edge only.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings

_MINOR_UNITS_PER_MAJOR = 100  # RSD and EUR both use 2 decimal places at P0.


@dataclass(frozen=True, slots=True)
class Money:
    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount_minor, int) or isinstance(self.amount_minor, bool):
            raise ValueError("amount_minor must be an int of minor units")
        if len(self.currency) != 3 or not self.currency.isupper():
            raise ValueError("currency must be a 3-letter uppercase ISO code")

    @classmethod
    def zero(cls, currency: str | None = None) -> Money:
        return cls(0, currency or get_settings().default_currency)

    def add(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def subtract(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def _assert_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError("cannot combine amounts of different currencies")

    def format(self) -> str:
        major, minor = divmod(abs(self.amount_minor), _MINOR_UNITS_PER_MAJOR)
        sign = "-" if self.amount_minor < 0 else ""
        return f"{sign}{major},{minor:02d} {self.currency}"
