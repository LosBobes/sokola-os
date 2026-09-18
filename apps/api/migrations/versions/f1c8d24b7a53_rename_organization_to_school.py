"""rename organization to school, the H0 security tenant

Decision O-01. In v5.7 a *school* is the H0 security tenant, and "Organization"
is reserved for a grouping above it that is explicitly NOT an authorization
domain. This repository used Organization for the tenant, so once M04 introduces
the real Organization layer the same word would mean both things in the same
code. That is the shape of mistake that produces a guard written against the
wrong concept, and it reads correct.

DCR-20260903-07 §3 forbids renaming functional code merely to match the
documentation; the product owner accepted that deviation deliberately, to remove
the ambiguity before M04 rather than after.

Nothing here changes behaviour. Tables, columns, constraints and indexes are
renamed in place, and the three stored enum values that said ORGANIZATION are
rewritten to SCHOOL. Renames keep the data; there is no copy and no window where
a row exists under both names.

Revision ID: f1c8d24b7a53
Revises: e8b47a3c9d16
Create Date: 2026-09-18 18:40:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f1c8d24b7a53'
down_revision: str | None = 'e8b47a3c9d16'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = [
    ("organization", "school"),
    ("organization_membership", "school_membership"),
    ("guardian_organization_access", "guardian_school_access"),
]

# Model-declared names. Auto-generated ones (*_organization_id_fkey and the like)
# are handled generically below, since there are 39 of them.
_NAMED_OBJECTS = [
    ("ix_audit_org_created", "ix_audit_school_created"),
    ("ix_document_org_subject", "ix_document_school_subject"),
    ("ix_privacy_consent_record_org_person", "ix_privacy_consent_record_school_person"),
    ("ix_privacy_dsar_org_person", "ix_privacy_dsar_school_person"),
    ("ix_privacy_retention_period_org", "ix_privacy_retention_period_school"),
    ("ix_progress_note_org_person", "ix_progress_note_school_person"),
    ("ix_structure_category_org", "ix_structure_category_school"),
    ("ix_structure_location_org", "ix_structure_location_school"),
    ("ix_structure_location_org_code", "ix_structure_location_school_code"),
    ("ix_structure_program_org", "ix_structure_program_school"),
    ("ix_structure_program_org_code", "ix_structure_program_school_code"),
    ("ix_structure_room_org", "ix_structure_room_school"),
    ("ix_structure_room_org_code", "ix_structure_room_school_code"),
    # A partial unique index, not a constraint, so it is renamed as an index.
    ("uq_org_local_member_code", "uq_school_local_member_code"),
]
_NAMED_CONSTRAINTS = [
    ("organization_membership", "uq_org_membership", "uq_school_membership"),
    ("guardian_organization_access", "uq_guardian_org_access", "uq_guardian_school_access"),
]

# 'ORGANIZATION' is stored, not just declared: role scope, invitation scope, and
# the announcement target. granted_areas is a text ARRAY, so it needs an element
# rewrite rather than a column-wide one.
_SCALAR_ENUMS = [
    ("role_assignment", "scope_type"),
    ("invitation", "scope_type"),
    ("announcement", "target_type"),
]
_ARRAY_ENUMS = [
    ("role_assignment", "granted_areas"),
    ("invitation", "granted_areas"),
]


def _rename_columns(bind: sa.engine.Connection, old: str, new: str) -> None:
    """Rename every occurrence of a tenant column, whatever table it sits in."""
    rows = bind.execute(
        sa.text(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = :old ORDER BY table_name"
        ),
        {"old": old},
    ).scalars().all()
    for table in rows:
        op.execute(f'ALTER TABLE "{table}" RENAME COLUMN {old} TO {new}')


def _rename_generated_objects(bind: sa.engine.Connection, old: str, new: str) -> None:
    """Rename constraints and indexes whose auto-generated name carries the old word.

    Left alone they would read `announcement_organization_id_fkey` on a column
    called school_id, which is the ambiguity this migration exists to remove.
    """
    constraints = bind.execute(
        sa.text(
            "SELECT c.conname, t.relname FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_namespace n ON n.oid = t.relnamespace "
            "WHERE n.nspname = 'public' AND c.conname LIKE :pattern ORDER BY c.conname"
        ),
        {"pattern": f"%{old}%"},
    ).all()
    for conname, relname in constraints:
        op.execute(f'ALTER TABLE "{relname}" RENAME CONSTRAINT "{conname}" TO "{conname.replace(old, new)}"')

    indexes = bind.execute(
        sa.text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'public' AND indexname LIKE :pattern ORDER BY indexname"
        ),
        {"pattern": f"%{old}%"},
    ).scalars().all()
    for index in indexes:
        op.execute(f'ALTER INDEX "{index}" RENAME TO "{index.replace(old, new)}"')


def _rewrite_enum_values(old: str, new: str) -> None:
    for table, column in _SCALAR_ENUMS:
        op.execute(f"UPDATE \"{table}\" SET {column} = '{new}' WHERE {column} = '{old}'")
    for table, column in _ARRAY_ENUMS:
        op.execute(
            f'UPDATE "{table}" SET {column} = array_replace({column}, \'{old}\', \'{new}\') '
            f"WHERE {column} IS NOT NULL AND '{old}' = ANY({column})"
        )


def _apply(old_word: str, new_word: str, tables: list[tuple[str, str]]) -> None:
    bind = op.get_bind()
    _rename_columns(bind, f"{old_word}_id", f"{new_word}_id")
    for old_name, new_name in _NAMED_OBJECTS:
        op.execute(f'ALTER INDEX IF EXISTS "{old_name}" RENAME TO "{new_name}"')
    for table, old_name, new_name in _NAMED_CONSTRAINTS:
        op.execute(f'ALTER TABLE "{table}" RENAME CONSTRAINT "{old_name}" TO "{new_name}"')
    for old_table, new_table in tables:
        op.execute(f'ALTER TABLE "{old_table}" RENAME TO "{new_table}"')
    # After the table rename, so the generated names pick up their final form.
    _rename_generated_objects(bind, old_word, new_word)
    _rewrite_enum_values(old_word.upper(), new_word.upper())


def upgrade() -> None:
    _apply("organization", "school", _TABLES)


def downgrade() -> None:
    bind = op.get_bind()
    _rename_columns(bind, "school_id", "organization_id")
    for old_name, new_name in _NAMED_OBJECTS:
        op.execute(f'ALTER INDEX IF EXISTS "{new_name}" RENAME TO "{old_name}"')
    for table, old_name, new_name in _NAMED_CONSTRAINTS:
        new_table = dict(_TABLES).get(table, table)
        op.execute(f'ALTER TABLE "{new_table}" RENAME CONSTRAINT "{new_name}" TO "{old_name}"')
    for old_table, new_table in _TABLES:
        op.execute(f'ALTER TABLE "{new_table}" RENAME TO "{old_table}"')
    _rename_generated_objects(bind, "school", "organization")
    _rewrite_enum_values("SCHOOL", "ORGANIZATION")
