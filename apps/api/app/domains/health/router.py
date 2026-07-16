"""Liveness and readiness endpoints. Unauthenticated on purpose."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.db import get_db

router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    status: Literal["ok"]
    version: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "degraded"]
    database: Literal["up", "down"]


@router.get("/health", response_model=LivenessResponse, operation_id="healthLiveness")
def liveness() -> LivenessResponse:
    return LivenessResponse(status="ok", version=__version__)


@router.get("/health/ready", response_model=ReadinessResponse, operation_id="healthReadiness")
def readiness(db: Annotated[Session, Depends(get_db)]) -> ReadinessResponse:
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return ReadinessResponse(status="degraded", database="down")
    return ReadinessResponse(status="ready", database="up")
