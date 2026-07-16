"""Shared helpers for the OpenAPI parity gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.main import create_app

COMMITTED_PATH = Path(__file__).resolve().parents[3] / "openapi" / "sokola-p0-v1.openapi.json"


def generate() -> dict[str, Any]:
    return create_app().openapi()


def serialize(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"
