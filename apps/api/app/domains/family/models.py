"""M07 §2.3: one school's verified link between an adult and a child.

This goes in **alongside** `people.GuardianRelationship` and
`people.GuardianSchoolAccess` rather than replacing them. Those two have 107
readers between them across identity, the parent router, communications and
events (F-31), so the replacement is staged: the new table first, readers moved
domain by domain, the old ones dropped only once nothing looks at them. The
same shape M01 used for sessions, and for the same reason — 107 call sites
rewritten in one commit is not a change anyone can review, least of all one
that governs which adult may see which child.
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
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.family.enums import LinkStatus, RelationshipKind


class GuardianChildLink(Base, TimestampMixin):
    """§2.3. "This school has checked that this adult may act for this child."

    Tenant-scoped, because that sentence only makes sense inside one school.
    The repo's `guardian_relationship` asserts one relationship per adult-child
    pair across the whole platform, which means school B cannot record its own
    verification once school A has recorded theirs — the concrete defect F-31
    describes.
    """

    __tablename__ = "guardian_child_link"
    __table_args__ = (
        # §2.0: every tenant entity exposes the composite target, so a later
        # row (a verification record, a primary-contact designation) can name
        # the tenant as part of its reference.
        UniqueConstraint("school_id", "id", name="uq_guardian_child_link_tenant"),
        # §2.3's partial unique. Partial because REJECTED and REVOKED rows are
        # the history and several are expected — §5.3 makes a fresh check a new
        # id rather than a revived row, so without the WHERE clause the second
        # check of the same pair could never be recorded.
        Index(
            "uq_guardian_child_link_open",
            "school_id",
            "guardian_person_id",
            "child_person_id",
            unique=True,
            postgresql_where=text(
                "status IN ('PENDING_VERIFICATION', 'ACTIVE')"
            ),
        ),
        # §2.3's tenant-safe triple FKs, with the membership *type* in the key.
        # Without the type a guardian link could name the same person's STAFF
        # membership and still satisfy the constraint; M06 added
        # `uq_school_membership_tenant_type` for exactly this.
        ForeignKeyConstraint(
            ["school_id", "guardian_school_membership_id", "guardian_membership_type"],
            [
                "school_membership.school_id",
                "school_membership.id",
                "school_membership.membership_type",
            ],
            name="fk_guardian_child_link_guardian_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["school_id", "child_school_membership_id", "child_membership_type"],
            [
                "school_membership.school_id",
                "school_membership.id",
                "school_membership.membership_type",
            ],
            name="fk_guardian_child_link_child_membership",
            ondelete="RESTRICT",
        ),
        # The denormalized types exist only to make those keys expressible, so
        # they are pinned. A row that said otherwise would be pointing the key
        # at the wrong kind of membership.
        CheckConstraint(
            "guardian_membership_type = 'GUARDIAN'",
            name="ck_guardian_child_link_guardian_type",
        ),
        CheckConstraint(
            "child_membership_type = 'PARTICIPANT'",
            name="ck_guardian_child_link_child_type",
        ),
        # §2.3: "ne sme biti isti ID". Nobody is their own guardian, and a
        # self-link would quietly grant an adult a second route to their own
        # record with a different subject basis.
        CheckConstraint(
            "guardian_person_id <> child_person_id",
            name="ck_guardian_child_link_distinct_people",
        ),
        # §2.3's conditional fields, in the database rather than in the service.
        # Each status owns exactly one timestamp, and a row that claims to be
        # ACTIVE without saying when is a verification nobody can audit.
        CheckConstraint(
            "(status = 'ACTIVE') = (activated_at IS NOT NULL)",
            name="ck_guardian_child_link_activated_at",
        ),
        CheckConstraint(
            "(status = 'REJECTED') = (rejected_at IS NOT NULL)",
            name="ck_guardian_child_link_rejected_at",
        ),
        CheckConstraint(
            "(status = 'REVOKED') = (revoked_at IS NOT NULL)",
            name="ck_guardian_child_link_revoked_at",
        ),
        # §2.3: the decider is required for every decided status. A link that
        # became ACTIVE with nobody named is exactly the "parent activated
        # another guardian themselves" that §1.2 forbids, and it would be
        # invisible afterwards.
        CheckConstraint(
            "(status = 'PENDING_VERIFICATION') = (decision_by_account_id IS NULL)",
            name="ck_guardian_child_link_decider",
        ),
        # §2.3: a refusal or a revocation has to say why. An ACTIVE link needs
        # no reason — approving is the unremarkable outcome — so this is not
        # the symmetric pair the three timestamps above are.
        CheckConstraint(
            "(status IN ('REJECTED', 'REVOKED')) = (decision_reason_code IS NOT NULL)",
            name="ck_guardian_child_link_decision_reason",
        ),
        CheckConstraint("version >= 1", name="ck_guardian_child_link_version"),
        Index("ix_guardian_child_link_child", "school_id", "child_person_id", "status"),
        Index(
            "ix_guardian_child_link_guardian",
            "school_id",
            "guardian_person_id",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("gcl"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    guardian_person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    child_person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    guardian_school_membership_id: Mapped[str] = mapped_column(String(64), nullable=False)
    child_school_membership_id: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Denormalized solely so the composite keys above can pin the membership
    #: type. Never read as the authority for anything; the membership is.
    guardian_membership_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="GUARDIAN"
    )
    child_membership_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="PARTICIPANT"
    )
    relationship_kind: Mapped[RelationshipKind] = mapped_column(
        enum_type(RelationshipKind), nullable=False
    )
    status: Mapped[LinkStatus] = mapped_column(
        enum_type(LinkStatus), nullable=False, default=LinkStatus.PENDING_VERIFICATION
    )
    #: Actor columns carry no foreign key, matching M05's policy-revision rows.
    #: Who asked and who decided is an audit fact: CASCADE would erase it when
    #: the account is deleted and RESTRICT would make a verified link block the
    #: deletion, and neither is what "this is what happened" should do.
    requested_by_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    activated_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: §5.3 requires a *distinct* approver from the requester. That is a
    #: service rule, not a column one — the database cannot know whether two
    #: account ids belong to the same human — so it is enforced where the
    #: decision is made and tested there.
    decision_by_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
