# Alignment: Dokumenti i ugovori

**oblast:** `dokumenti` · **v1.0**, status `odobreno` · **app @ `3c2d074`**

## Summary

**0 implemented · entire domain absent.** No `documents` backend domain, no
model, no endpoint, no file-storage integration. Confirmed: a codebase grep for
document/dokument concepts returns nothing in `apps/api/app/`.

## Missing (all of it)

- File upload with allowed format + max size.
- Document ownership / who-can-see / who-can-download (per-role, per-scope).
- Security scan of uploads.
- Retention period.
- Contracts (ugovori) as a document subtype with signature/acknowledgement state.
- The invariant "a private document must never be publicly reachable" — no
  storage layer exists to enforce or violate yet.

## Plan

Wave 3, after consents (PRD 12), since document access to child-related files is
gated by parental consent and privacy rules. Needs a decision on blob storage
(object store + signed, expiring URLs) before modeling. No dependency the other
way, so it can follow 12 directly.

## Open questions

1. Storage target (S3-compatible object store vs DB blobs)?
2. Which document types are v1.0 (contracts, consents-as-documents, media
   releases) vs later?
