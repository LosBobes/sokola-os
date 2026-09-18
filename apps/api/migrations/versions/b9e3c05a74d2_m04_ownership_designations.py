"""M04 ownership: owner nominations and the primary-owner term

M04 §2.6–2.7. Two tables, plus the two composite unique keys that let them prove
tenancy through a foreign key rather than through a column a query has to
remember to filter on.

`school_membership` gains UNIQUE(school_id, id, person_id) and `role_assignment`
gains UNIQUE(school_id, id, person_id, role_code). Neither adds a uniqueness
guarantee — `id` is already the primary key in both — and that is the point:
they exist so another table's FK can name the tenant, the person and (for the
role) the role code as part of the reference. A nomination then *cannot* be
written against another school's membership, and a primary-owner term cannot be
written against the same person's TRAINER assignment. This is the composite
tenant FK shape M03 §7 asks for, applied where M04 needs it first.

Backfill: none. Both tables are new, and §9.4 is explicit that existing owner
roles are not all declared primary — exactly one *proven* primary gets a term,
and where no proof exists the school goes to a controlled exception rather than
to a guess. This repository has no such proof for any existing school (the
self-service creator is an OWNER, but so is any co-owner they invited), so no
term is created here. Ownership mutation stays fail-closed until M02/M05 supply
the acceptance path that creates the first term.

Revision ID: b9e3c05a74d2
Revises: a4d76f2b91c0
Create Date: 2026-09-18 20:35:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b9e3c05a74d2'
down_revision: str | None = 'a4d76f2b91c0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOMINATION_KINDS = "('INITIAL_PRIMARY_OWNER', 'ADDITIONAL_OWNER')"
_NOMINATION_STATUSES = "('PENDING', 'FULFILLED', 'CANCELLED')"
_CANCEL_REASONS = "('WRONG_PERSON', 'REQUEST_WITHDRAWN', 'SCHOOL_PROVISIONING_CANCELLED')"
_TERM_REASONS = "('INITIAL_OWNER_ACCEPTED', 'OWNER_TRANSFER', 'PLATFORM_LEGAL_OVERRIDE')"


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_school_membership_tenant_person",
        "school_membership",
        ["school_id", "id", "person_id"],
    )
    op.create_unique_constraint(
        "uq_role_assignment_tenant_person_role",
        "role_assignment",
        ["school_id", "id", "person_id", "role_code"],
    )

    op.create_table(
        "school_owner_nomination",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("school_id", sa.String(64), sa.ForeignKey("school.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_person_id", sa.String(64), nullable=False),
        sa.Column("target_membership_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("latest_invitation_id", sa.String(64), nullable=True),
        sa.Column("fulfilled_role_assignment_id", sa.String(64), nullable=True),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason_code", sa.String(40), nullable=True),
        sa.Column("created_by_actor_ref", sa.String(64), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["school_id", "target_membership_id", "target_person_id"],
            ["school_membership.school_id", "school_membership.id", "school_membership.person_id"],
            name="fk_owner_nomination_membership",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(f"kind IN {_NOMINATION_KINDS}", name="ck_owner_nomination_kind"),
        sa.CheckConstraint(f"status IN {_NOMINATION_STATUSES}", name="ck_owner_nomination_status"),
        sa.CheckConstraint(
            f"cancellation_reason_code IS NULL OR cancellation_reason_code IN {_CANCEL_REASONS}",
            name="ck_owner_nomination_cancel_reason_value",
        ),
        sa.CheckConstraint("(status = 'FULFILLED') = (fulfilled_at IS NOT NULL)", name="ck_owner_nomination_fulfilled_at"),
        sa.CheckConstraint("(status = 'FULFILLED') = (fulfilled_role_assignment_id IS NOT NULL)", name="ck_owner_nomination_fulfilled_role"),
        sa.CheckConstraint("(status = 'CANCELLED') = (cancelled_at IS NOT NULL)", name="ck_owner_nomination_cancelled_at"),
        sa.CheckConstraint("(status = 'CANCELLED') = (cancellation_reason_code IS NOT NULL)", name="ck_owner_nomination_cancel_reason"),
        sa.CheckConstraint("version >= 1", name="ck_owner_nomination_version"),
    )
    # At most one pending initial nomination per school (§2.6). Partial: a
    # cancelled or fulfilled one is history and several are expected.
    op.create_index(
        "uq_owner_nomination_pending_initial",
        "school_owner_nomination",
        ["school_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING' AND kind = 'INITIAL_PRIMARY_OWNER'"),
    )
    op.create_index("ix_owner_nomination_school_status", "school_owner_nomination", ["school_id", "status"])

    op.create_table(
        "school_primary_owner_term",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("school_id", sa.String(64), sa.ForeignKey("school.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_person_id", sa.String(64), nullable=False),
        sa.Column("owner_role_assignment_id", sa.String(64), nullable=False),
        sa.Column("owner_role_code", sa.String(40), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_nomination_id", sa.String(64), sa.ForeignKey("school_owner_nomination.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason_code", sa.String(40), nullable=False),
        sa.Column("created_by_actor_ref", sa.String(64), nullable=False),
        sa.Column("case_reference", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["school_id", "owner_role_assignment_id", "owner_person_id", "owner_role_code"],
            [
                "role_assignment.school_id",
                "role_assignment.id",
                "role_assignment.person_id",
                "role_assignment.role_code",
            ],
            name="fk_primary_owner_term_role",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(f"reason_code IN {_TERM_REASONS}", name="ck_primary_owner_term_reason"),
        sa.CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_primary_owner_term_period"),
        sa.CheckConstraint("owner_role_code = 'OWNER'", name="ck_primary_owner_term_role_code"),
        sa.CheckConstraint(
            "reason_code <> 'PLATFORM_LEGAL_OVERRIDE' OR case_reference IS NOT NULL",
            name="ck_primary_owner_term_override_case",
        ),
    )
    # At most one open term per school: the constraint that makes "exactly one
    # primary owner" true of the data rather than of the transfer function.
    op.create_index(
        "uq_primary_owner_term_current",
        "school_primary_owner_term",
        ["school_id"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index("ix_primary_owner_term_school", "school_primary_owner_term", ["school_id", "valid_from"])


def downgrade() -> None:
    op.drop_table("school_primary_owner_term")
    op.drop_table("school_owner_nomination")
    op.drop_constraint("uq_role_assignment_tenant_person_role", "role_assignment", type_="unique")
    op.drop_constraint("uq_school_membership_tenant_person", "school_membership", type_="unique")
