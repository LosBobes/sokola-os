"""M05 publish authorization policy revision 1.3

M05 §2.2, §2.2.1, §2.4, §3.3.

Publishes the catalogue itself: four authorization domains, twelve role
definitions, thirty-eight permission definitions and their default role
bindings, exactly as the contract's tables give them.

The content lives in `app.domains.authorization.registry` rather than being
written out here, for two reasons. It is read by the application at boot and
by the tests, so a copy in a migration would be a second source of truth that
drifts. And a test asserts the module matches the contract key for key, which
it cannot do against SQL literals buried in a migration.

Nothing in this revision is invented. §3.3 is explicit that other modules'
permissions arrive only when their own module defines the semantics — so the
keys here are M05's own, plus the M04 school and platform keys §3.3 lists
outright. M06/M07 and M17–M28 keys have their own registry documents and
belong to a later revision, published when those modules are built.

This revision is `ACTIVE` on publication, and it is the first, so the partial
unique index that allows only one ACTIVE revision is satisfied trivially. A
correction is a new revision with a new number, never an edit of this one:
`canonical_content_hash` is what makes that checkable.

Revision ID: a7d2f4e91c63
Revises: f9bcbb4ddfb1
Create Date: 2026-09-19 18:05:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from app.domains.authorization.registry import REVISION_NO, ensure_policy_revision
from sqlalchemy.orm import Session

revision: str = 'a7d2f4e91c63'
down_revision: str | None = 'f9bcbb4ddfb1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with Session(bind=op.get_bind()) as session:
        ensure_policy_revision(session)
        session.commit()


def downgrade() -> None:
    # Every child row cascades from the revision, so removing the revision
    # removes the catalogue with it.
    op.execute(
        f"DELETE FROM authorization_policy_revision WHERE revision_no = {REVISION_NO}"
    )
