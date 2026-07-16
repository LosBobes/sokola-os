"""Small HTTP-layer helpers shared by routers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Header

IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]
