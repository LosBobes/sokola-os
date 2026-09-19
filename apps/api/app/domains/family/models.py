"""M07 §2.1-2.3: families, who is in them, and who may act for a child.

The three tables here are three *separate facts*, which §3.1 states outright:
a family grouping, someone's place in it, and a verified guardian relationship
are not derived from one another, nor from a surname, an email or an address.
Nothing in this module grants access on the strength of a shared household —
that is `GuardianChildLink` and only `GuardianChildLink`, and §3.2 says even a
shared child leaves two families invisible to each other.

`GuardianChildLink` goes in **alongside** `people.GuardianRelationship` and
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
    Date,
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
from app.domains.family.enums import (
    FamilyMembershipStatus,
    FamilyStatus,
    LinkStatus,
    MemberKind,
    RelationshipKind,
)
from app.platform import clock


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


class Family(Base, TimestampMixin):
    """§2.1. A grouping one school recorded — a household, as that school sees it.

    §3.1 is the rule that gives this table its shape: family, membership,
    guardian link, payer link and primacy are **five separate facts**, and none
    is derived from a surname, an email, an address or another table. So this
    row carries almost nothing. It has no name of its own beyond an internal
    label the school may set for its own lists, and §2.1 says that label "ne
    koristi se za identitet" — it is not a key, not a search handle, not a way
    to find a family you were not already allowed to see.

    What it deliberately does *not* do is grant anything. Two people in one
    family see nothing of each other because of it; §3.2 says even a shared
    child does not make two families visible to one another. Whether an adult
    may act for a child is `GuardianChildLink`, and only that.
    """

    __tablename__ = "family"
    __table_args__ = (
        UniqueConstraint("school_id", "id", name="uq_family_tenant"),
        # §2.1: a reason is required exactly when the family is archived.
        # Symmetric rather than one-sided, because an ACTIVE family carrying an
        # archive reason is a row that was archived and then quietly brought
        # back — which §5.1 does not allow at all.
        CheckConstraint(
            "(status = 'ARCHIVED') = (archive_reason_code IS NOT NULL)",
            name="ck_family_archive_reason",
        ),
        CheckConstraint(
            "display_label IS NULL OR length(display_label) BETWEEN 1 AND 100",
            name="ck_family_display_label_length",
        ),
        CheckConstraint("version >= 1", name="ck_family_version"),
        Index("ix_family_school_status", "school_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("fam"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    #: §2.1: the school's internal label, never an identity. Nullable because a
    #: school that has not named a grouping still has the grouping.
    display_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[FamilyStatus] = mapped_column(
        enum_type(FamilyStatus), nullable=False, default=FamilyStatus.ACTIVE
    )
    #: No foreign key, for the reason the guardian link's actor columns have
    #: none: who created this is an audit fact, not a live reference.
    created_by_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    archive_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class FamilyMembership(Base, TimestampMixin):
    """§2.2. One person's place in one family grouping, for a period.

    The composite foreign key names the **person** as well as the tenant —
    `(school_id, school_membership_id, person_id)` against M06's
    `uq_school_membership_tenant_person`. `person_id` is therefore not a
    denormalized convenience that could drift from the membership it sits
    beside: the database will not hold a row where the two disagree.

    §2.2's closing sentence is the one worth keeping in view: the same person
    may belong to several families in one school — separated households are the
    normal case, not an anomaly — "to samo po sebi ne daje međusobnu
    vidljivost". The partial unique below is scoped to one family for exactly
    that reason.
    """

    __tablename__ = "family_membership"
    __table_args__ = (
        UniqueConstraint("school_id", "id", name="uq_family_membership_tenant"),
        # §2.2's partial unique: one open place per person per family. Partial
        # because ENDED rows are the history and §5.2 makes a return a new row,
        # so a family someone left and rejoined holds two.
        Index(
            "uq_family_membership_open",
            "school_id",
            "family_id",
            "person_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        ForeignKeyConstraint(
            ["school_id", "family_id"],
            ["family.school_id", "family.id"],
            name="fk_family_membership_family",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["school_id", "school_membership_id", "person_id"],
            [
                "school_membership.school_id",
                "school_membership.id",
                "school_membership.person_id",
            ],
            name="fk_family_membership_school_membership",
            ondelete="RESTRICT",
        ),
        # §2.2: an ended membership says when and why; an active one says
        # neither. Both directions, so a row cannot carry an end date while
        # still claiming to be ACTIVE.
        CheckConstraint(
            "(status = 'ENDED') = (effective_until IS NOT NULL)",
            name="ck_family_membership_effective_until",
        ),
        CheckConstraint(
            "(status = 'ENDED') = (end_reason_code IS NOT NULL)",
            name="ck_family_membership_end_reason",
        ),
        # §2.2: "ne pre from".
        CheckConstraint(
            "effective_until IS NULL OR effective_until >= effective_from",
            name="ck_family_membership_period",
        ),
        CheckConstraint("version >= 1", name="ck_family_membership_version"),
        Index("ix_family_membership_person", "school_id", "person_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("fmem"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    family_id: Mapped[str] = mapped_column(String(64), nullable=False)
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    school_membership_id: Mapped[str] = mapped_column(String(64), nullable=False)
    member_kind: Mapped[MemberKind] = mapped_column(enum_type(MemberKind), nullable=False)
    status: Mapped[FamilyMembershipStatus] = mapped_column(
        enum_type(FamilyMembershipStatus),
        nullable=False,
        default=FamilyMembershipStatus.ACTIVE,
    )
    #: §2.2 calls these business dates rather than timestamps: when a school
    #: considers someone part of a household is a decision, and it has no time
    #: of day. Same choice M06 made for a membership's start.
    effective_from: Mapped[dt.date] = mapped_column(
        Date, nullable=False, default=lambda: clock.now().date()
    )
    effective_until: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    end_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
