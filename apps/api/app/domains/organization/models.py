from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, RecordStatusMixin, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.organization.enums import OrganizationType


class Organization(Base, TimestampMixin, RecordStatusMixin):
    """A tenant. The root of the isolation boundary: nearly every other row
    carries this id and is filtered by it server-side."""

    __tablename__ = "organization"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("org"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[OrganizationType] = mapped_column(
        enum_type(OrganizationType), nullable=False, default=OrganizationType.OTHER
    )
    # IANA timezone; recurring schedules are interpreted against this.
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Belgrade")
