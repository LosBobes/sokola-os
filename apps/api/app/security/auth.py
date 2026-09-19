"""Principal resolution, who is making the request.

Order:

1. **Dev header adapter** (local only): ``x-sokola-person-id`` names the acting
   person. Refused unless ``allow_insecure_dev_auth`` is on (and that flag is
   refused in staging/production at startup).
2. **Session cookie**: the signed cookie carries an opaque credential for a
   server-side :class:`AuthSession`, and M01 §6 AUTH-03 is run against it on
   every request — hash, revocation, both expiries, account status, and exact
   ``authorization_version`` match.

The cookie is only transport. The session is the row, which is what makes it
possible to end one (AUTH-04) or all of them (AUTH-08) and have the next request
actually notice.

The acting school/role is resolved separately and re-checked on every
request (see :mod:`app.security.deps`).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session
from starlette.requests import Request

from app.common.enums import RecordStatus
from app.common.errors import UnauthorizedError
from app.config import Settings
from app.domains.identity import sessions
from app.domains.identity.auth_enums import UserAccountStatus
from app.domains.identity.auth_models import UserAccount
from app.domains.identity.models import Person

DEV_PERSON_HEADER = "x-sokola-person-id"
#: The key under which the signed cookie carries the session credential. Short
#: and meaningless on purpose: it is not a person id, an account id or anything
#: else a reader could act on if they saw it.
SESSION_CREDENTIAL_KEY = "sid"


@dataclass(frozen=True, slots=True)
class Principal:
    person_id: str
    #: Present only for a real session. The dev header adapter has no account
    #: and no session, and code that needs either must say so rather than
    #: assume.
    user_account_id: str | None = None
    session_id: str | None = None


def resolve_principal(request: Request, db: Session, settings: Settings) -> Principal:
    if settings.allow_insecure_dev_auth:
        principal = _resolve_dev_header(request, db)
        if principal is not None:
            return principal

    principal = _resolve_session(request, db, settings)
    if principal is not None:
        return principal

    raise UnauthorizedError("Nedostaje prijava.")


def _resolve_dev_header(request: Request, db: Session) -> Principal | None:
    person_id = request.headers.get(DEV_PERSON_HEADER)
    if not person_id:
        return None
    if not _is_active_person(db, person_id):
        raise UnauthorizedError("Nepoznata osoba.")
    return Principal(person_id=person_id)


def _resolve_session(
    request: Request, db: Session, settings: Settings
) -> Principal | None:
    """M01 §6 AUTH-03, on every protected request.

    Every failure returns ``None`` and they are deliberately indistinguishable:
    §11 keeps ``UNAUTHENTICATED`` free of tenant state, and a caller able to
    tell "expired" from "revoked" from "never existed" would have exactly the
    oracle that is being withheld.
    """
    # Read from the raw scope so this works with or without SessionMiddleware
    # installed (e.g. in unit tests that construct a bare Request).
    cookie = request.scope.get("session") or {}
    credential = cookie.get(SESSION_CREDENTIAL_KEY)
    if not credential:
        return None

    validated = sessions.validate_session(
        db, credential, idle_minutes=settings.session_idle_minutes
    )
    if validated is None:
        return None
    session, account = validated

    # The account's person may still have been archived out from under it —
    # a different lifecycle (M06) with its own reasons.
    if not _is_active_person(db, account.person_id):
        return None
    return Principal(
        person_id=account.person_id,
        user_account_id=account.id,
        session_id=session.id,
    )


def _is_active_person(db: Session, person_id: str) -> bool:
    person = db.get(Person, person_id)
    return person is not None and person.record_status is not RecordStatus.ARCHIVED


def account_can_sign_in(db: Session, person_id: str) -> bool:
    """Whether this person has an account that may open a session (§3.1).

    Only ``ACTIVE`` qualifies. A suspended account is refused here as firmly as
    a disabled one: §6 AUTH-10 says a suspension ends by an audited command, not
    by the holder trying again.
    """
    account = (
        db.query(UserAccount)
        .filter(UserAccount.person_id == person_id)
        .order_by(UserAccount.created_at.desc())
        .first()
    )
    return account is not None and account.status is UserAccountStatus.ACTIVE
