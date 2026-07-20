"""Invitation token generation and hashing.

The raw token is shown to the caller exactly once (send/reissue response);
only its hash is ever persisted, mirroring the "never store local secrets we
can't reset" posture the identity domain already keeps for auth (see
``app/security/oidc.py``).
"""

from __future__ import annotations

import hashlib
import secrets

INVITATION_TTL_DAYS = 7


def generate_token() -> tuple[str, str]:
    """Return ``(raw_token, token_hash)``."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
