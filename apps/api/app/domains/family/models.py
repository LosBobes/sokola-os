"""M07 §2.1-2.5: families, guardianship, who pays, and the proof behind each.

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
    LinkKind,
    LinkStatus,
    MemberKind,
    PayerBasisKind,
    RelationshipKind,
    VerificationMethod,
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


class PayerChildLink(Base, TimestampMixin):
    """§2.5. Someone who pays for a child — and who, by paying, learns nothing.

    This is the table whose *absence* was the sharpest gap in the repo (F-32).
    Until now the only way to mark an adult as paying for a child was to make
    them that child's guardian, which handed them the child's attendance,
    documents, health records and profile as a side effect of a billing
    arrangement. §3.7 forbids exactly that: a payer link gives access to
    "samo M12 finansijskim operacijama koje izričito prihvataju
    `PAYER_CHILD_LINK` basis", and M05 §3.2 point 9 says a `PAYER` subject
    basis "nikad ne daje attendance/document/health/profile/guardian pravo".

    Nothing here enforces that, because nothing *can* at this level — a table
    cannot stop a reader joining to it. What the schema does is make the
    financial link expressible on its own, so the readers that must not see
    child data have a basis to resolve that is not guardianship. The guard
    lives in M05, and M07 §7.2's `PayerSubjectBasisPort` is required to return
    `FINANCE_ONLY` and no guardian implication.

    Two shapes differ from `GuardianChildLink`, both deliberately:

    * the payer's membership type is a **pair** — `CONTACT` or `GUARDIAN` —
      where the guardian link pins a single value. A payer need not be a
      guardian, and a school records a non-guardian payer as a `CONTACT`.
    * there is **no distinct-people CHECK**. §2.3 says of the guardian link
      "ne sme biti isti ID" and §2.5 says nothing of the kind, which reads as
      intentional rather than as an omission: an adult who trains at the school
      and pays their own fees holds a `PARTICIPANT` membership and a `CONTACT`
      one, and both sides of this row would be satisfied. Inventing the
      constraint would refuse a case the contract leaves open.
    """

    __tablename__ = "payer_child_link"
    __table_args__ = (
        UniqueConstraint("school_id", "id", name="uq_payer_child_link_tenant"),
        # §2.5's partial unique, same reasoning as the guardian link's: §5.3
        # makes a fresh check a new row, so refused and revoked rows are the
        # history. §2.5 adds that several *different* ACTIVE payers for one
        # child are allowed — M12 decides how an obligation is split — which is
        # why the key names the payer rather than the child alone.
        Index(
            "uq_payer_child_link_open",
            "school_id",
            "payer_person_id",
            "child_person_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING_VERIFICATION', 'ACTIVE')"),
        ),
        ForeignKeyConstraint(
            ["school_id", "family_id"],
            ["family.school_id", "family.id"],
            name="fk_payer_child_link_family",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["school_id", "payer_school_membership_id", "payer_membership_type"],
            [
                "school_membership.school_id",
                "school_membership.id",
                "school_membership.membership_type",
            ],
            name="fk_payer_child_link_payer_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["school_id", "child_school_membership_id", "child_membership_type"],
            [
                "school_membership.school_id",
                "school_membership.id",
                "school_membership.membership_type",
            ],
            name="fk_payer_child_link_child_membership",
            ondelete="RESTRICT",
        ),
        # The payer's type is constrained to §2.5's pair rather than pinned to
        # one value. Together with the foreign key above this says: the type
        # recorded here is the membership's real type, *and* it is one a payer
        # is allowed to hold. Either half alone would let a STAFF membership
        # through.
        CheckConstraint(
            "payer_membership_type IN ('CONTACT', 'GUARDIAN')",
            name="ck_payer_child_link_payer_type",
        ),
        CheckConstraint(
            "child_membership_type = 'PARTICIPANT'",
            name="ck_payer_child_link_child_type",
        ),
        CheckConstraint(
            "(status = 'ACTIVE') = (activated_at IS NOT NULL)",
            name="ck_payer_child_link_activated_at",
        ),
        CheckConstraint(
            "(status = 'REJECTED') = (rejected_at IS NOT NULL)",
            name="ck_payer_child_link_rejected_at",
        ),
        CheckConstraint(
            "(status = 'REVOKED') = (revoked_at IS NOT NULL)",
            name="ck_payer_child_link_revoked_at",
        ),
        CheckConstraint(
            "(status = 'PENDING_VERIFICATION') = (decision_by_account_id IS NULL)",
            name="ck_payer_child_link_decider",
        ),
        CheckConstraint(
            "(status IN ('REJECTED', 'REVOKED')) = (decision_reason_code IS NOT NULL)",
            name="ck_payer_child_link_decision_reason",
        ),
        CheckConstraint("version >= 1", name="ck_payer_child_link_version"),
        Index("ix_payer_child_link_child", "school_id", "child_person_id", "status"),
        Index("ix_payer_child_link_payer", "school_id", "payer_person_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("pcl"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    payer_person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    child_person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    payer_school_membership_id: Mapped[str] = mapped_column(String(64), nullable=False)
    child_school_membership_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payer_membership_type: Mapped[str] = mapped_column(String(40), nullable=False)
    child_membership_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="PARTICIPANT"
    )
    #: §2.5 makes this mandatory. Which family, and whether both people are
    #: ACTIVE in it, is a service rule — §3.1 refuses a payer in family A for a
    #: child in family B with `M07_PAYER_BASIS_INVALID` unless the sponsor
    #: process verified it — and checking that needs two `FamilyMembership`
    #: rows, which a CHECK cannot read. `RESTRICT` rather than `CASCADE`:
    #: §3.13 makes an open link a *blocker* on archiving a family, so the
    #: database must not quietly remove the evidence that the blocker exists.
    family_id: Mapped[str] = mapped_column(String(64), nullable=False)
    basis_kind: Mapped[PayerBasisKind] = mapped_column(
        enum_type(PayerBasisKind), nullable=False
    )
    status: Mapped[LinkStatus] = mapped_column(
        enum_type(LinkStatus), nullable=False, default=LinkStatus.PENDING_VERIFICATION
    )
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
    decision_by_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class RelationshipVerificationRecord(Base, TimestampMixin):
    """§2.4. The immutable proof that a school checked a link before activating it.

    §3.5 makes this and the link's activation one transaction: a link becomes
    ACTIVE "i tačno jedan odgovarajući immutable verification record nastaju
    atomarno tek posle school approval-a". A link that is ACTIVE with no record
    is an activation nobody can account for afterwards, which is the state this
    table exists to make impossible.

    One table with a `link_kind` discriminator rather than one per link type.
    The evidence has the same shape either way — a method, a moment, an
    authorized verifier, a policy version — while what it proves does not, and
    keeping them together is what lets §5.3's "exactly one activation proof per
    link" be a single partial unique index instead of an invariant maintained
    in two places that can drift apart.

    **Nothing here stores what was seen.** §2.4 is explicit for the document
    case: "čuva se samo činjenica provere i opcioni keyed case digest; nema
    slike, broja ili običnog hash-a dokumenta u M07." A school that inspected an
    identity document records *that* it did.

    §2.4's rule that the verifier may not be the account of the person whose
    link is being checked (`M07_SELF_VERIFICATION_FORBIDDEN`) is not a
    constraint here, for the same reason the guardian link's distinct-approver
    rule is not: the database cannot know which human an account belongs to.
    It is enforced where the decision is made.
    """

    __tablename__ = "relationship_verification_record"
    __table_args__ = (
        UniqueConstraint(
            "school_id", "id", name="uq_relationship_verification_record_tenant"
        ),
        # §2.4: exactly one activation proof per link. Two separate partial
        # uniques rather than one over a coalesced column, because each is a
        # real index on a real column and Postgres can use them for the lookup
        # "does this link have its proof" that §3.5 needs on every activation.
        Index(
            "uq_relationship_verification_guardian_link",
            "guardian_child_link_id",
            unique=True,
            postgresql_where=text("guardian_child_link_id IS NOT NULL"),
        ),
        Index(
            "uq_relationship_verification_payer_link",
            "payer_child_link_id",
            unique=True,
            postgresql_where=text("payer_child_link_id IS NOT NULL"),
        ),
        ForeignKeyConstraint(
            ["school_id", "guardian_child_link_id"],
            ["guardian_child_link.school_id", "guardian_child_link.id"],
            name="fk_relationship_verification_guardian_link",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["school_id", "payer_child_link_id"],
            ["payer_child_link.school_id", "payer_child_link.id"],
            name="fk_relationship_verification_payer_link",
            ondelete="CASCADE",
        ),
        # §2.4: "CHECK zahteva tačno jedan link FK u skladu sa `link_kind`."
        # Both halves matter. Without the agreement clause a GUARDIAN_CHILD
        # record could hold a payer link and satisfy "exactly one"; without
        # "exactly one" a record could hold both or neither.
        CheckConstraint(
            "(guardian_child_link_id IS NOT NULL)::int "
            "+ (payer_child_link_id IS NOT NULL)::int = 1",
            name="ck_relationship_verification_one_link",
        ),
        CheckConstraint(
            "(link_kind = 'GUARDIAN_CHILD') = (guardian_child_link_id IS NOT NULL)",
            name="ck_relationship_verification_link_kind",
        ),
        # The digest is 64 hex characters or absent. §2.4 makes it optional —
        # `SCHOOL_RECORD` has no case reference to point at — and the length
        # check is what stops the column quietly accepting a raw reference
        # someone forgot to hash.
        CheckConstraint(
            "evidence_reference_digest IS NULL "
            "OR evidence_reference_digest ~ '^[0-9a-f]{64}$'",
            name="ck_relationship_verification_digest_shape",
        ),
        Index(
            "ix_relationship_verification_school",
            "school_id",
            "link_kind",
            "verified_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("rvr"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    link_kind: Mapped[LinkKind] = mapped_column(enum_type(LinkKind), nullable=False)
    guardian_child_link_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payer_child_link_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_method: Mapped[VerificationMethod] = mapped_column(
        enum_type(VerificationMethod), nullable=False
    )
    #: Keyed HMAC of the school's own case reference, never a document number,
    #: a name, or a plain hash of low-entropy PII (§2.4). Produced by
    #: :func:`app.domains.family.evidence.evidence_reference_digest`, which
    #: explains why the key is not optional.
    evidence_reference_digest: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    #: §2.4: an authorized school actor, and not the account of the person
    #: whose link is being verified. The second half is a service rule.
    verified_by_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    verified_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    #: Which version of the school's checking procedure was followed. Kept so a
    #: later change of procedure does not retroactively reinterpret what an
    #: older record means.
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
