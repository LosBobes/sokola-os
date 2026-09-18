"""audit seal: per-tenant hash chain and database-enforced append-only

Seals the audit trail (M21). Each entry gains a sequence number within its
chain, its own SHA-256 digest and its predecessor's, and a trigger refuses
UPDATE and DELETE so append-only stops being a convention.

Order matters here. Existing rows are backfilled into chains *before* the
trigger exists, because the backfill writes to rows the trigger would then
refuse. The backfill invents nothing: it seals the entries already recorded,
in their existing (chain, created_at, id) order.

Revision ID: b7e2a4c91f08
Revises: a1c4f2d80b37
Create Date: 2026-09-18 17:05:00.000000
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.platform.audit.service import compute_digest

revision: str = 'b7e2a4c91f08'
down_revision: str | None = 'a1c4f2d80b37'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SYSTEM_CHAIN_KEY = "__system__"

# Refusing the write outright is the point: a caller that wants to "correct" an
# entry appends a new one, which is what an audit trail is for.
_GUARD_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % is not permitted', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""

_GUARD_TRIGGER = """
CREATE TRIGGER audit_log_append_only_guard
BEFORE UPDATE OR DELETE ON audit_log
FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();
"""


def upgrade() -> None:
    op.create_table(
        'audit_chain_head',
        sa.Column('chain_key', sa.String(length=64), nullable=False),
        sa.Column('last_sequence_no', sa.BigInteger(), nullable=False),
        sa.Column('last_hash', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('chain_key'),
    )

    op.add_column('audit_log', sa.Column('chain_key', sa.String(length=64), nullable=True))
    op.add_column('audit_log', sa.Column('sequence_no', sa.BigInteger(), nullable=True))
    op.add_column('audit_log', sa.Column('prev_hash', sa.String(length=64), nullable=True))
    op.add_column('audit_log', sa.Column('row_hash', sa.String(length=64), nullable=True))

    _backfill_chains()

    op.alter_column('audit_log', 'chain_key', nullable=False)
    op.alter_column('audit_log', 'sequence_no', nullable=False)
    op.alter_column('audit_log', 'row_hash', nullable=False)
    # created_at is written by the application from now on: the digest covers it,
    # so the value has to be the one that was hashed, not one the database picks.
    op.alter_column('audit_log', 'created_at', server_default=None)
    op.create_unique_constraint(
        'uq_audit_chain_sequence', 'audit_log', ['chain_key', 'sequence_no']
    )

    op.execute(_GUARD_FUNCTION)
    op.execute(_GUARD_TRIGGER)


def _backfill_chains() -> None:
    """Seal the entries already in the table, oldest first within each chain."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, organization_id, actor_person_id, data_class, action,"
            "       entity_type, entity_id, summary, context, created_at "
            "FROM audit_log "
            "ORDER BY COALESCE(organization_id, :system), created_at, id"
        ),
        {"system": SYSTEM_CHAIN_KEY},
    ).mappings().all()

    heads: dict[str, tuple[int, str | None]] = {}
    for row in rows:
        chain_key = row["organization_id"] or SYSTEM_CHAIN_KEY
        last_sequence_no, last_hash = heads.get(chain_key, (0, None))
        sequence_no = last_sequence_no + 1

        created_at = row["created_at"]
        if created_at.tzinfo is None:  # a TIMESTAMPTZ always comes back aware, but be explicit
            created_at = created_at.replace(tzinfo=dt.UTC)

        row_hash = compute_digest(
            chain_key=chain_key,
            sequence_no=sequence_no,
            prev_hash=last_hash,
            organization_id=row["organization_id"],
            actor_person_id=row["actor_person_id"],
            data_class=row["data_class"],
            action=row["action"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            summary=row["summary"],
            context=row["context"],
            created_at=created_at,
        )
        bind.execute(
            sa.text(
                "UPDATE audit_log SET chain_key = :chain_key, sequence_no = :sequence_no,"
                "                     prev_hash = :prev_hash, row_hash = :row_hash "
                "WHERE id = :id"
            ),
            {
                "chain_key": chain_key,
                "sequence_no": sequence_no,
                "prev_hash": last_hash,
                "row_hash": row_hash,
                "id": row["id"],
            },
        )
        heads[chain_key] = (sequence_no, row_hash)

    for chain_key, (last_sequence_no, last_hash) in heads.items():
        bind.execute(
            sa.text(
                "INSERT INTO audit_chain_head (chain_key, last_sequence_no, last_hash,"
                "                              created_at, updated_at) "
                "VALUES (:chain_key, :last_sequence_no, :last_hash, now(), now())"
            ),
            {
                "chain_key": chain_key,
                "last_sequence_no": last_sequence_no,
                "last_hash": last_hash,
            },
        )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_append_only_guard ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_append_only()")
    op.drop_constraint('uq_audit_chain_sequence', 'audit_log', type_='unique')
    op.alter_column('audit_log', 'created_at', server_default=sa.text('now()'))
    op.drop_column('audit_log', 'row_hash')
    op.drop_column('audit_log', 'prev_hash')
    op.drop_column('audit_log', 'sequence_no')
    op.drop_column('audit_log', 'chain_key')
    op.drop_table('audit_chain_head')
