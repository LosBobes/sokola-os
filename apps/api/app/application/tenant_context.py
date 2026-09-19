"""TEN-Q02 `GetActiveTenantContext` (M03 §12, §6.1–6.3, §8).

"Which school am I working in, and what may this context be used for?" — the
question a client asks once, on load, before it renders anything tenant-shaped.

It takes no input. §12 is explicit that the session comes only from the M01
credential: a school id in the request would be the client choosing its own
tenant, which is the whole thing M03 exists to prevent.

The answer is deliberately thin. §12 forbids returning a permission list as
authority, so nothing here says what the person may *do* — that is M05's, computed
per action, and a list shipped to the client would become a cached authority
the moment someone read it as one. What comes back is the tenant, what the
context may be used for, and enough version material to notice staleness.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac

from sqlalchemy.orm import Session

from app.common.errors import TenantContextNotAvailableError
from app.domains.identity.auth_models import UserAccount
from app.domains.school.enums import SchoolStatus
from app.domains.school.models import School
from app.domains.school.ownership import current_primary_term
from app.domains.tenancy import context as tenant_context
from app.domains.tenancy import security as tenant_security
from app.domains.tenancy.enums import (
    START_ROUTE_REGULAR,
    START_ROUTE_SETUP,
    SchoolMode,
)
from app.domains.tenancy.models import SessionTenantContext

#: Domain separation for the etag key. Derived from the session secret rather
#: than being its own deployment variable, exactly as the rate-limit signals
#: are: a new required secret is a new way for a deploy to come up half
#: configured, and this value protects nothing that outlives a context.
_ETAG_INFO = b"sokola/m03/context-etag/v1"


@dataclasses.dataclass(frozen=True, slots=True)
class ActiveTenantContext:
    """§12's TEN-Q02 result. Six fields, and no permission list among them."""

    school_id: str
    school_mode: SchoolMode
    workspace_key: str
    context_version: int
    context_etag: str
    allowed_start_route: str


def get_active_tenant_context(
    db: Session,
    *,
    context: SessionTenantContext,
    account: UserAccount,
    person_id: str,
    secret: str,
) -> ActiveTenantContext:
    """Run the whole §8 pipeline, then say what the surviving context is.

    Raises rather than returning a degraded answer. §12: a stale or invalid
    context is atomically invalidated and the caller gets
    `TENANT_CONTEXT_REQUIRED` with a neutral recovery hint and no protected
    payload — which `resolve` already does, including moving the row out of
    `ACTIVE` so the next request does not rediscover the same staleness.
    """
    school = tenant_context.resolve(
        db, context=context, account=account, person_id=person_id
    )
    mode = _mode_for(db, school=school, person_id=person_id)
    return ActiveTenantContext(
        school_id=school.id,
        school_mode=mode,
        workspace_key=context.workspace_key,
        context_version=context.context_version,
        context_etag=context_etag(
            db, context=context, account=account, school=school, mode=mode, secret=secret
        ),
        allowed_start_route=(
            START_ROUTE_SETUP if mode is SchoolMode.SETUP_ONLY else START_ROUTE_REGULAR
        ),
    )


def _mode_for(db: Session, *, school: School, person_id: str) -> SchoolMode:
    """§6.1 vs §6.2, decided from the school's live status and who is asking.

    `resolve` has already refused a `DEACTIVATED` school (§6.3), so the choice
    here is between the two statuses that can carry a context at all.

    §6.2 is the part that is easy to miss: `IN_PREPARATION` may give *only* a
    `SETUP_ONLY` context, and only to the authorized first owner or onboarding
    actor. Before this, an active membership in a school still being set up
    produced an ordinary context for anyone who had one — the guard read the
    status only to reject `DEACTIVATED`.

    A nominee who has not accepted yet never reaches this function: §8 step 5
    requires current `ACTIVE` membership evidence, and a pending nomination is
    not membership. So the question here is only whether the caller is the
    school's current primary owner.
    """
    if school.status is SchoolStatus.ACTIVE:
        return SchoolMode.REGULAR

    term = current_primary_term(db, school.id)
    if term is not None and term.owner_person_id == person_id:
        return SchoolMode.SETUP_ONLY

    # §11's enumeration rule applies to the refusal too: it says the context is
    # unavailable, not that the school exists and is still being set up.
    raise TenantContextNotAvailableError("Škola trenutno nije dostupna za rad.")


def context_etag(
    db: Session,
    *,
    context: SessionTenantContext,
    account: UserAccount,
    school: School,
    mode: SchoolMode,
    secret: str,
) -> str:
    """§5.4's `context_etag`: a strong version for a stale check.

    Keyed, not a plain hash. An unkeyed digest over this material would be
    reproducible by anyone who could guess the inputs — and the inputs are a
    school id, a workspace key and three small integers, which is a guessable
    space. A client could then forge an etag that claims to be current, or
    confirm a guess about another school's version counters by comparing
    digests. The key makes both useless.

    It covers everything whose change must invalidate the context: the
    context's own version, M01's authorization version, M03's tenant access
    version, and the tenant/workspace/mode the answer was computed for. Reading
    the live tenant access version rather than the one stored at selection is
    deliberate — the stored one cannot change, so an etag built on it would
    stay fresh through exactly the invalidation it is supposed to report.
    """
    material = "|".join(
        (
            school.id,
            context.workspace_key,
            mode.value,
            str(context.context_version),
            str(account.authorization_version),
            str(tenant_security.current_version(db, school.id)),
        )
    )
    key = hmac.new(secret.encode("utf-8"), _ETAG_INFO, hashlib.sha256).digest()
    return hmac.new(key, material.encode("utf-8"), hashlib.sha256).hexdigest()
