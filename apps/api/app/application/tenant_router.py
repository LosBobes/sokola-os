"""The HTTP surface for TEN-Q02 (M03 §12).

The router lives here rather than under `app/domains/tenancy/` for the same
reason the coordinator does: answering this question needs School, ownership
and tenancy together, and a domain may not reach into another domain's
service. `app/application/` is the layer that may.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.application.tenant_context import get_active_tenant_context
from app.common.errors import TenantContextRequiredError
from app.domains.identity.auth_models import UserAccount
from app.domains.tenancy import context as tenant_context
from app.domains.tenancy.enums import SchoolMode
from app.security.deps import DbDep, PrincipalDep, SettingsDep

router = APIRouter(tags=["tenancy"])


class ActiveTenantContextResponse(BaseModel):
    """§12's TEN-Q02 result, and nothing beyond it.

    No permission list: §12 forbids returning one as authority, and a list on
    the wire becomes a cached authority the first time a client trusts it
    instead of asking. What the person may do is decided per action, by M05.
    """

    school_id: str
    school_mode: SchoolMode
    workspace_key: str
    context_version: int
    #: A strong, opaque version for stale checking (§5.4). Keyed, so it cannot
    #: be recomputed or forged by a client that guesses the inputs.
    context_etag: str = Field(description="Opaque; compare for equality only.")
    allowed_start_route: str


@router.get(
    "/tenant/context",
    response_model=ActiveTenantContextResponse,
    operation_id="getActiveTenantContext",
)
def get_active_context(
    db: DbDep, principal: PrincipalDep, settings: SettingsDep
) -> ActiveTenantContextResponse:
    """TEN-Q02. No body, no query, no school id — §12 takes the session from
    the M01 credential alone, because a client that names its own tenant is
    the thing M03 exists to prevent.

    Every refusal here is the same neutral `TENANT_CONTEXT_REQUIRED`: no
    session, no selection yet, or a selection that has gone stale all mean
    "choose a school", and distinguishing them would tell an unauthenticated
    caller which case they are in.
    """
    if principal.session_id is None or principal.user_account_id is None:
        # The dev-header adapter has no session to hang a context on, and
        # neither does an unauthenticated caller. Same answer to both.
        raise TenantContextRequiredError("Izaberite školu.")

    context = tenant_context.current(db, principal.session_id)
    if context is None:
        raise TenantContextRequiredError("Izaberite školu.")

    account = db.get(UserAccount, principal.user_account_id)
    if account is None:
        raise TenantContextRequiredError("Izaberite školu.")

    active = get_active_tenant_context(
        db,
        context=context,
        account=account,
        person_id=principal.person_id,
        secret=settings.session_secret,
    )
    db.commit()
    return ActiveTenantContextResponse(
        school_id=active.school_id,
        school_mode=active.school_mode,
        workspace_key=active.workspace_key,
        context_version=active.context_version,
        context_etag=active.context_etag,
        allowed_start_route=active.allowed_start_route,
    )
