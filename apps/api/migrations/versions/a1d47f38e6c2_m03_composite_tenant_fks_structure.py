"""M03 composite tenant foreign keys for the structure cluster

M03 §7.2–7.3.

Before this, eight references between tenant tables named only the target's
`id`. Nothing in the database stopped a group in school A pointing at school
B's location — the only thing standing there was an application check, and a
check someone forgets once leaves no trace.

§7.3 asks for the tenant to travel *inside* the reference:
`(school_id, related_id) → (school_id, id)`. The parent's `UNIQUE(school_id,
id)` adds no uniqueness — `id` is already the primary key — it exists so the
child's foreign key can name the tenant as part of what it points at. After
this a cross-tenant link is impossible rather than merely incorrect.

Eight relations, three parents:

* `structure_program.category_id`, `structure_room.location_id`
* `group.program_id`, `group.location_id`, `group.default_location_id`
* `session.location_id`, `session_series.location_id`, `event.location_id`

`ON DELETE SET NULL (column)` names the column on the seven nullable ones,
because the plain form would try to null `school_id` too and that column is
NOT NULL. Postgres 15+ accepts the column list; this repo runs 16.
`structure_room` keeps CASCADE — deleting a location still takes its rooms,
which is both the existing behaviour and the sensible one.

**This migration refuses to run on data that already crosses a tenant.** §7.10
forbids quietly reassigning an ambiguous legacy row to the first or only
school, so rather than repair anything it counts the offenders per relation
and aborts with the counts. A cross-tenant reference is a real incident, and
the operator wants to see it, not have it silently corrected underneath them.

Revision ID: a1d47f38e6c2
Revises: f8c21e64b0a7
Create Date: 2026-09-19 18:40:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a1d47f38e6c2'
down_revision: str | None = 'f8c21e64b0a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (child table, child column, parent table, constraint name, on-delete action)
_RELATIONS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "structure_program", "category_id", "structure_category",
        "fk_structure_program_category_tenant", "SET NULL (category_id)",
    ),
    (
        "structure_room", "location_id", "structure_location",
        "fk_structure_room_location_tenant", "CASCADE",
    ),
    (
        "group", "program_id", "structure_program",
        "fk_group_program_tenant", "SET NULL (program_id)",
    ),
    (
        "group", "location_id", "structure_location",
        "fk_group_location_tenant", "SET NULL (location_id)",
    ),
    (
        "group", "default_location_id", "structure_location",
        "fk_group_default_location_tenant", "SET NULL (default_location_id)",
    ),
    (
        "session", "location_id", "structure_location",
        "fk_session_location_tenant", "SET NULL (location_id)",
    ),
    (
        "session_series", "location_id", "structure_location",
        "fk_session_series_location_tenant", "SET NULL (location_id)",
    ),
    (
        "event", "location_id", "structure_location",
        "fk_event_location_tenant", "SET NULL (location_id)",
    ),
)

_PARENTS: tuple[tuple[str, str], ...] = (
    ("structure_category", "uq_structure_category_tenant"),
    ("structure_program", "uq_structure_program_tenant"),
    ("structure_location", "uq_structure_location_tenant"),
)

#: The single-column constraints being replaced, under the names the database
#: actually holds them by — six were named explicitly when the tables were
#: created, two fell back to PostgreSQL's default. Read from `pg_constraint`
#: rather than derived from a naming rule, because the rule is not one.
_OLD_FKS: tuple[tuple[str, str], ...] = (
    ("structure_program", "structure_program_category_id_fkey"),
    ("structure_room", "structure_room_location_id_fkey"),
    ("group", "fk_group_program"),
    ("group", "fk_group_location"),
    ("group", "fk_group_default_location"),
    ("session", "fk_session_location"),
    ("session_series", "fk_session_series_location"),
    ("event", "fk_event_location"),
)

#: The same names again, keyed by relation, so `downgrade` puts each one back
#: as it was rather than under a name this migration invented.
_OLD_FK_NAMES: dict[tuple[str, str], str] = {
    ("structure_program", "category_id"): "structure_program_category_id_fkey",
    ("structure_room", "location_id"): "structure_room_location_id_fkey",
    ("group", "program_id"): "fk_group_program",
    ("group", "location_id"): "fk_group_location",
    ("group", "default_location_id"): "fk_group_default_location",
    ("session", "location_id"): "fk_session_location",
    ("session_series", "location_id"): "fk_session_series_location",
    ("event", "location_id"): "fk_event_location",
}


def _refuse_on_existing_cross_tenant_rows() -> None:
    """§7.10: report, never repair.

    Reassigning an ambiguous row to the first or only school is exactly what
    the contract forbids, and a cross-tenant reference is an incident an
    operator should see rather than have corrected underneath them.
    """
    bind = op.get_bind()
    offenders = []
    for child, column, parent, _, _ in _RELATIONS:
        count = bind.execute(
            sa.text(
                f'SELECT count(*) FROM "{child}" c '
                f'JOIN "{parent}" p ON p.id = c."{column}" '
                f'WHERE c."{column}" IS NOT NULL AND p.school_id <> c.school_id'
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

    for table, name in _OLD_FKS:
        op.drop_constraint(name, table, type_="foreignkey")

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
        action = "CASCADE" if ondelete == "CASCADE" else "SET NULL"
        old_name = _OLD_FK_NAMES[(child, column)]
        op.execute(
            f'ALTER TABLE "{child}" ADD CONSTRAINT {old_name} '
            f'FOREIGN KEY ("{column}") REFERENCES "{parent}" (id) '
            f"ON DELETE {action}"
        )

    for table, name in _PARENTS:
        op.drop_constraint(name, table, type_="unique")
