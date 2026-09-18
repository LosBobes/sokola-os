"""Ownership designations: who answers for a school, and since when.

M04 §2.6–2.7. Two tables, and the important thing about both is what they are
*not*:

* a nomination is not an account, a role or an invitation. It is the school's
  recorded intent, which an M02 invitation then carries. Separating them is what
  lets an invitation expire, bounce or be reissued without the school forgetting
  who it meant to make an owner.
* a primary-owner term is not a permission. ``PRIMARY_OWNER`` is a *designation
  over* an active OWNER role assignment, never a second role granting more
  (§2.7). Making it a role would mean two places to check before deciding what
  someone may do, and the one you forget is the one that matters.

Tenant proof is by composite foreign key, not by a matching ``school_id``
column. ``(school_id, id, person_id)`` on the target means a row physically
cannot reference a membership or a role assignment belonging to another school —
the thing a plain ``school_id`` column merely describes and a query has to
remember to check.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.school.ownership_enums import (
    OwnerNominationCancelReason,
    OwnerNominationKind,
    OwnerNominationStatus,
    PrimaryOwnerTermReason,
)


class SchoolOwnerNomination(Base, TimestampMixin):
    """§2.6. The school's intent that a named person become an owner.

    Its id is what M02 carries as ``ownership_designation_ref``, so an
    invitation can always say which intent it is serving — and, more usefully,
    an acceptance can be refused when it does not match one.
    """

    __tablename__ = "school_owner_nomination"
    __table_args__ = (
        # The membership must belong to this school *and* to this person. A
        # plain FK to school_membership.id would let a nomination point at
        # another tenant's membership row and still look consistent.
        ForeignKeyConstraint(
            ["school_id", "target_membership_id", "target_person_id"],
            [
                "school_membership.school_id",
                "school_membership.id",
                "school_membership.person_id",
            ],
            name="fk_owner_nomination_membership",
            ondelete="CASCADE",
        ),
        # At most one pending initial nomination per school. Partial, because a
        # cancelled or fulfilled one is history and several are expected.
        Index(
            "uq_owner_nomination_pending_initial",
            "school_id",
            unique=True,
            postgresql_where=text(
                "status = 'PENDING' AND kind = 'INITIAL_PRIMARY_OWNER'"
            ),
        ),
        Index("ix_owner_nomination_school_status", "school_id", "status"),
        CheckConstraint(
            "(status = 'FULFILLED') = (fulfilled_at IS NOT NULL)",
            name="ck_owner_nomination_fulfilled_at",
        ),
        CheckConstraint(
            "(status = 'FULFILLED') = (fulfilled_role_assignment_id IS NOT NULL)",
            name="ck_owner_nomination_fulfilled_role",
        ),
        CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL)",
            name="ck_owner_nomination_cancelled_at",
        ),
        CheckConstraint(
            "(status = 'CANCELLED') = (cancellation_reason_code IS NOT NULL)",
            name="ck_owner_nomination_cancel_reason",
        ),
        CheckConstraint("version >= 1", name="ck_owner_nomination_version"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("nom"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    target_person_id: Mapped[str] = mapped_column(String(64), nullable=False)
    #: This repo's stand-in for M06's ``SchoolPersonProfile``: the row that makes
    #: a global Person visible inside one tenant. See finding F-14.
    target_membership_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[OwnerNominationKind] = mapped_column(
        enum_type(OwnerNominationKind), nullable=False
    )
    status: Mapped[OwnerNominationStatus] = mapped_column(
        enum_type(OwnerNominationStatus), nullable=False, default=OwnerNominationStatus.PENDING
    )
    #: The M02 invitation currently carrying this intent. Reissuing an
    #: invitation changes only this reference: never the person, never the kind.
    latest_invitation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fulfilled_role_assignment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fulfilled_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancellation_reason_code: Mapped[OwnerNominationCancelReason | None] = mapped_column(
        enum_type(OwnerNominationCancelReason), nullable=True
    )
    created_by_actor_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class SchoolPrimaryOwnerTerm(Base):
    """§2.7. Who has been the school's primary owner, and for which period.

    Half-open ``[valid_from, valid_to)``, at most one open at a time. A transfer
    closes one and opens the next at the same instant in one transaction, so the
    school is never briefly without a primary owner and never briefly with two —
    and §5.4 forbids ending a term without a successor at all.
    """

    __tablename__ = "school_primary_owner_term"
    __table_args__ = (
        # The role assignment must be this school's, this person's, and OWNER.
        # Without the role_code column in the key, a transfer could point at the
        # same person's TRAINER assignment and read as a valid ownership proof.
        ForeignKeyConstraint(
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
        Index(
            "uq_primary_owner_term_current",
            "school_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from", name="ck_primary_owner_term_period"
        ),
        CheckConstraint("owner_role_code = 'OWNER'", name="ck_primary_owner_term_role_code"),
        # A platform override has to name its case; a transfer the owner asked
        # for does not need one.
        CheckConstraint(
            "reason_code <> 'PLATFORM_LEGAL_OVERRIDE' OR case_reference IS NOT NULL",
            name="ck_primary_owner_term_override_case",
        ),
        Index("ix_primary_owner_term_school", "school_id", "valid_from"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("pot"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    owner_person_id: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_role_assignment_id: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Denormalized solely so the composite FK above can pin it to OWNER. Never
    #: read as the authority for anything; the role assignment is.
    owner_role_code: Mapped[str] = mapped_column(String(40), nullable=False, default="OWNER")
    valid_from: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_nomination_id: Mapped[str | None] = mapped_column(
        ForeignKey("school_owner_nomination.id", ondelete="SET NULL"), nullable=True
    )
    reason_code: Mapped[PrimaryOwnerTermReason] = mapped_column(
        enum_type(PrimaryOwnerTermReason), nullable=False
    )
    created_by_actor_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    case_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
