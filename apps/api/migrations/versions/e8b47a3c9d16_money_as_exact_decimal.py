"""money as exact decimal: integer minor units become NUMERIC(18,2)

Execution contract §3: money is NUMERIC(18,2) (or a provably equivalent exact
decimal), carried across the API as a decimal string with an ISO 4217 code, and
there is no parallel minor-unit master. Integer minor units were exact, so
nothing here recovers lost precision; what it removes is the encoding. Every
boundary had to remember that 12500 meant 125,00, and any reader that forgot
produced an amount a hundred times wrong that still looked plausible.

The conversion divides by 100 exactly, in NUMERIC arithmetic, never through a
float. Each column is rewritten in place with USING, so the values move with
the type and there is no window where a column holds both encodings.

Revision ID: e8b47a3c9d16
Revises: d5a92c74e8b1
Create Date: 2026-09-18 18:05:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = 'e8b47a3c9d16'
down_revision: str | None = 'd5a92c74e8b1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, old column, new column, nullable)
_COLUMNS = [
    ("billing_run", "total_minor", "total", False),
    ("charge", "amount_due_minor", "amount_due", False),
    ("charge", "amount_paid_minor", "amount_paid", False),
    ("group", "base_monthly_price_minor", "base_monthly_price", True),
    ("group_membership", "discount_minor", "discount", False),
    ("payment_record", "amount_minor", "amount", False),
]


def upgrade() -> None:
    for table, old, new, _nullable in _COLUMNS:
        op.execute(f'ALTER TABLE "{table}" RENAME COLUMN {old} TO {new}')
        # ::numeric first, so the division is exact decimal arithmetic rather
        # than integer division truncating 12500/100 the wrong way.
        op.execute(
            f'ALTER TABLE "{table}" ALTER COLUMN {new} '
            f"TYPE NUMERIC(18,2) USING ({new}::numeric / 100)"
        )


def downgrade() -> None:
    for table, old, new, _nullable in _COLUMNS:
        # Back to minor units. Amounts carrying more than two decimal places
        # cannot exist: the column's scale is 2.
        op.execute(
            f'ALTER TABLE "{table}" ALTER COLUMN {new} '
            f"TYPE INTEGER USING (round({new} * 100))"
        )
        op.execute(f'ALTER TABLE "{table}" RENAME COLUMN {new} TO {old}')
