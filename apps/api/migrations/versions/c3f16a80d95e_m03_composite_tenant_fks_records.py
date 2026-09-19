"""M03 composite tenant foreign keys for the records cluster

M03 §7.2–7.3, the third and last F-26 slice.

The first two slices closed the fifteen references into the structure domain
and into `group`/`session`/`session_series`. These are the remaining eight —
the records a school accumulates rather than the things it schedules:

* `announcement_recipient.announcement_id`
* `event_registration.event_id`
* `charge.billing_run_id`, `payment_record.charge_id`
* `import_row.batch_id`
* `school_locator.replaced_by_locator_id` (self-referential)
* `school_primary_owner_term.source_nomination_id`
* `outbox_dead_letter_review.message_id`

Seven of them follow the pattern of the first two slices exactly: the parent
gains `UNIQUE(school_id, id)`, and the single-column key is replaced by
`(school_id, child_column) → (school_id, id)`.

**The outbox one does not, and that is deliberate.** `school_id` is nullable on
both `outbox_message` and `outbox_dead_letter_review`, because the outbox also
carries platform-level messages belonging to no school. Postgres's MATCH SIMPLE
does not check a composite foreign key at all when any of its columns is NULL,
so replacing the single-column key there would stop checking exactly those rows
— weaker than what exists today, not stronger. So the composite key is **added
alongside** the existing one: the single-column key still guarantees the message
exists, and the composite one additionally refuses a school-scoped review of a
different school's message.

`school_locator.replaced_by_locator_id` is self-referential: the table is both
child and parent. The class already carried the comment "Same school"; this
makes the database say it.

Like the earlier slices, this refuses to run on data that already crosses a
tenant rather than repairing it (§7.10).

Revision ID: c3f16a80d95e
Revises: b2e59c14d7a3
Create Date: 2026-09-19 17:40:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c3f16a80d95e'
down_revision: str | None = 'b2e59c14d7a3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (child table, child column, parent table, new constraint name, on-delete)
_RELATIONS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "announcement_recipient", "announcement_id", "announcement",
        "fk_announcement_recipient_announcement_tenant", "CASCADE",
    ),
    (
        "event_registration", "event_id", "event",
        "fk_event_registration_event_tenant", "CASCADE",
    ),
    (
        "charge", "billing_run_id", "billing_run",
        "fk_charge_billing_run_tenant", "SET NULL (billing_run_id)",
    ),
    (
        "payment_record", "charge_id", "charge",
        "fk_payment_record_charge_tenant", "CASCADE",
    ),
    (
        "import_row", "batch_id", "import_batch",
        "fk_import_row_batch_tenant", "CASCADE",
    ),
    (
        "school_locator", "replaced_by_locator_id", "school_locator",
        "fk_school_locator_replaced_by_tenant", "SET NULL (replaced_by_locator_id)",
    ),
    (
        "school_primary_owner_term", "source_nomination_id", "school_owner_nomination",
        "fk_primary_owner_term_nomination_tenant", "SET NULL (source_nomination_id)",
    ),
    (
        "outbox_dead_letter_review", "message_id", "outbox_message",
        "fk_dead_letter_review_message_tenant", "CASCADE",
    ),
)

_PARENTS: tuple[tuple[str, str], ...] = (
    ("announcement", "uq_announcement_tenant"),
    ("event", "uq_event_tenant"),
    ("billing_run", "uq_billing_run_tenant"),
    ("charge", "uq_charge_tenant"),
    ("import_batch", "uq_import_batch_tenant"),
    ("school_locator", "uq_school_locator_tenant"),
    ("school_owner_nomination", "uq_owner_nomination_tenant"),
    ("outbox_message", "uq_outbox_message_tenant"),
)

#: The single-column constraints being *replaced*, under the names the database
#: actually holds them by. `outbox_dead_letter_review` is deliberately absent:
#: see the module docstring — its single-column key is kept, and the composite
#: one is added next to it.
_OLD_FK_NAMES: dict[tuple[str, str], str] = {
    ("announcement_recipient", "announcement_id"):
        "announcement_recipient_announcement_id_fkey",
    ("event_registration", "event_id"): "event_registration_event_id_fkey",
    ("charge", "billing_run_id"): "charge_billing_run_id_fkey",
    ("payment_record", "charge_id"): "payment_record_charge_id_fkey",
    ("import_row", "batch_id"): "import_row_batch_id_fkey",
    ("school_locator", "replaced_by_locator_id"):
        "school_locator_replaced_by_locator_id_fkey",
    ("school_primary_owner_term", "source_nomination_id"):
        "school_primary_owner_term_source_nomination_id_fkey",
}


def _refuse_on_existing_cross_tenant_rows() -> None:
    """§7.10: report, never repair."""
    bind = op.get_bind()
    offenders = []
    for child, column, parent, _, _ in _RELATIONS:
        count = bind.execute(
            sa.text(
                f'SELECT count(*) FROM "{child}" c '
                f'JOIN "{parent}" p ON p.id = c."{column}" '
                f'WHERE c."{column}" IS NOT NULL '
                f'AND c.school_id IS NOT NULL AND p.school_id IS NOT NULL '
                f'AND p.school_id <> c.school_id'
            )
        ).scalar_one()
        if count:
            offenders.append(f"{child}.{column} -> {parent}: {count}")
    if offenders:
        raise RuntimeError(
            "Cross-tenant references already exist and must be resolved by an "
            "operator before this migration can run (M03 §7.10 forbids "
            "reassigning them automatically):\n  " + "\n  ".join(offenders)
        )


def upgrade() -> None:
    _refuse_on_existing_cross_tenant_rows()

    for table, name in _PARENTS:
        op.create_unique_constraint(name, table, ["school_id", "id"])

    for child, column, _, _, _ in _RELATIONS:
        old = _OLD_FK_NAMES.get((child, column))
        if old is not None:
            op.drop_constraint(old, child, type_="foreignkey")

    for child, column, parent, name, ondelete in _RELATIONS:
        # `create_foreign_key` does not take the `SET NULL (col)` column list,
        # so the composite constraints go in as explicit DDL.
        op.execute(
            f'ALTER TABLE "{child}" ADD CONSTRAINT {name} '
            f'FOREIGN KEY (school_id, "{column}") '
            f'REFERENCES "{parent}" (school_id, id) ON DELETE {ondelete}'
        )


def downgrade() -> None:
    for child, _, _, name, _ in _RELATIONS:
        op.drop_constraint(name, child, type_="foreignkey")

    for child, column, parent, _, ondelete in _RELATIONS:
        old_name = _OLD_FK_NAMES.get((child, column))
        if old_name is None:
            # The outbox one was added, not swapped, so there is nothing to
            # restore — its original key was never dropped.
            continue
        action = "CASCADE" if ondelete == "CASCADE" else "SET NULL"
        op.execute(
            f'ALTER TABLE "{child}" ADD CONSTRAINT {old_name} '
            f'FOREIGN KEY ("{column}") REFERENCES "{parent}" (id) '
            f"ON DELETE {action}"
        )

    for table, name in _PARENTS:
        op.drop_constraint(name, table, type_="unique")
