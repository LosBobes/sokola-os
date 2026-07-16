from __future__ import annotations

from fastapi import APIRouter

from app.domains.identity import service
from app.domains.identity.schemas import ContextSummary, MeResponse
from app.security.deps import DbDep, PrincipalDep

router = APIRouter(tags=["me"])


@router.get("/me", response_model=MeResponse, operation_id="getMe")
def get_me(db: DbDep, principal: PrincipalDep) -> MeResponse:
    """The authenticated person and the contexts they may act in. Called before a
    context is chosen, so it requires authentication but no active context."""
    return service.get_me(db, principal)


@router.get("/me/contexts", response_model=list[ContextSummary], operation_id="listMyContexts")
def list_my_contexts(db: DbDep, principal: PrincipalDep) -> list[ContextSummary]:
    return service.get_me(db, principal).contexts
