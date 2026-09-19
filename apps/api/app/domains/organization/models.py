"""The ``Organization``: a legal/commercial holder of one or more schools.

Deliberately **not** a tenant and **not** an authorization domain (§3.1). Sharing
an organization grants nobody a single row in another of its schools: visibility
is proven per school, by M03/M05/M06, and the organization link is never accepted
as that proof. It is here because contracts, entitlements and invoices belong to a
legal entity, and a school does not have to be one.

This is why decision O-01 renamed the old ``Organization`` tenant table to
``School`` first: the word now means one thing.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.organization.enums import OrganizationStatus

#: ISO 3166-1 alpha-2, and the only value the current scope supports (§2.0).
SUPPORTED_COUNTRY_CODE = "RS"


class Organization(Base, TimestampMixin):
    """§2.1. Global, never tenant-scoped, and never a source of access."""

    __tablename__ = "organization"
    __table_args__ = (
        # Dedupe keys, in order of authority. `legal_name` is not one of them:
        # two genuinely different organizations may share a name, and merging
        # rows by name is how one legal entity's contracts end up on another's.
        Index("uq_organization_ref", "organization_ref", unique=True),
        Index(
            "uq_organization_registration",
            "country_code",
            "registration_number",
            unique=True,
            postgresql_where=(
                # Only among rows that still matter: an archived duplicate must
                # not block a correct re-registration of the same entity.
                "registration_number IS NOT NULL AND status <> 'ARCHIVED'"
            ),
        ),
        CheckConstraint(
            f"country_code = '{SUPPORTED_COUNTRY_CODE}'",
            name="ck_organization_country_supported",
        ),
        CheckConstraint("length(btrim(legal_name)) BETWEEN 1 AND 200", name="ck_organization_name"),
        CheckConstraint("version >= 1", name="ck_organization_version"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("org"))
    #: Platform provisioning / CRM reference. Globally unique, and not a secret:
    #: knowing it grants nothing.
    organization_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    #: Uppercase alphanumeric when present; unique with country among live rows.
    registration_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[OrganizationStatus] = mapped_column(
        enum_type(OrganizationStatus), nullable=False, default=OrganizationStatus.ACTIVE
    )
    archived_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Platform actor / service refs. Not person ids: an organization is
    #: maintained by the platform, and no school actor writes this table.
    created_by_actor_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_by_actor_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Optimistic concurrency. Starts at 1, +1 per mutation.
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
