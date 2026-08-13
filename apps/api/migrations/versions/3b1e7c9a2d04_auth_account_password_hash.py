"""auth_account password_hash

Revision ID: 3b1e7c9a2d04
Revises: 0cfcd81ee3fa
Create Date: 2026-07-22 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '3b1e7c9a2d04'
down_revision: str | None = '0cfcd81ee3fa'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'auth_account',
        sa.Column('password_hash', sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('auth_account', 'password_hash')
