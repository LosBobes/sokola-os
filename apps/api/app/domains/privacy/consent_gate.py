"""The consent-gating hook other domains may call before relying on a
person's consent for something, e.g. "has this person consented to appear
in photos before a media feature publishes one".

This is deliberately **not wired into any other domain yet**; each domain
adopts it as its own follow-up (see the PR description). It exists here,
tested, so that follow-up is a one-line call rather than new plumbing.

Module name matters: the architecture gate (``scripts/check_architecture.py``)
forbids a domain importing another domain's ``service``/``repository``/
``router``/``policy`` module. This module is named ``consent_gate`` precisely
so that a future ``from app.domains.privacy.consent_gate import
has_active_consent`` in another domain's service never trips that rule.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.privacy.enums import ConsentScope
from app.domains.privacy.models import ConsentRecord


def has_active_consent(
    db: Session, organization_id: str, person_id: str, scope: ConsentScope
) -> bool:
    """True iff ``person_id`` currently holds a live (granted, un-withdrawn)
    consent for ``scope`` within ``organization_id``. Withdrawn consents
    (``revoked_at`` set) never count, regardless of when they were granted."""
    stmt = select(ConsentRecord.id).where(
        ConsentRecord.organization_id == organization_id,
        ConsentRecord.person_id == person_id,
        ConsentRecord.scope == scope,
        ConsentRecord.revoked_at.is_(None),
    )
    return db.execute(stmt.limit(1)).first() is not None


__all__ = ["has_active_consent"]
