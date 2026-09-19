"""M07 §2.4: the keyed digest of a verification's case reference.

§2.4 permits storing "keyed HMAC tenant-internog case reference-a" and forbids
"nikad broj dokumenta, ime ili hash niskoentropijskog PII-ja". The two halves
of that sentence are one rule: a plain hash of an identity-document number is
the number. National ID formats are short, structured and often carry a
checksum, so the space a brute-forcer has to walk is small enough to walk — and
a stored SHA-256 of one is a document number written in a font nobody reads
aloud.

The key is what removes that. Without the key nothing can be recomputed, so the
digest is useful for exactly what §2.4 wants it for — "is this the same case
reference I filed earlier" — and useless for recovering what it was made from.

`school_id` goes into the message, not just for tidiness: the same case
reference filed at two schools must not produce the same digest, or the column
becomes a cross-tenant correlation handle in a module whose §4 goes out of its
way to keep schools from learning about one another.

The key is derived from `session_secret` under its own domain separator, the
same arrangement `app.platform.rate_limit.service` and
`app.application.tenant_context` use. That avoids adding a deployment variable
whose absence would be discovered in production — and, more to the point, an
operator who must remember a new secret is an operator who will eventually be
handed a system that quietly ran without one.
"""

from __future__ import annotations

import hashlib
import hmac

#: Domain separator for the derived key. Versioned, so a later change of
#: derivation cannot silently reuse old digests under a new meaning — the
#: digests would simply stop matching, which is the honest failure.
_EVIDENCE_INFO = b"sokola/m07-evidence-reference/v1"


def evidence_reference_digest(
    case_reference: str, *, school_id: str, secret: str
) -> str:
    """The value for `relationship_verification_record.evidence_reference_digest`.

    `case_reference` is the school's **own** internal reference for the check
    it performed — a case number in its records, a ticket id. It is not, and
    must never be, a document number, a person's name, a date of birth or any
    other low-entropy identifier about the person: those are what §2.4's second
    half forbids, and keying the digest protects the column, not the decision
    to put the wrong thing in it.

    Returns 64 hex characters, matching the column's `char(64)`.
    """
    key = hmac.new(secret.encode("utf-8"), _EVIDENCE_INFO, hashlib.sha256).digest()
    message = f"{school_id}\x1f{case_reference}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


__all__ = ["evidence_reference_digest"]
