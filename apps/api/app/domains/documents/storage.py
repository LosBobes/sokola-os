"""Pluggable byte storage for uploaded documents.

``StorageBackend`` is the seam between the documents domain and wherever the
actual bytes live. This increment ships exactly one implementation —
``LocalFilesystemBackend``, writing to a gitignored runtime directory — because
standing up a real object store (S3/GCS) needs infrastructure credentials this
PR does not have.

Swapping to S3/GCS later is meant to be a drop-in: write a new class satisfying
this same ``save``/``load`` shape and construct it instead of
``LocalFilesystemBackend`` wherever the domain builds its backend (currently
``app.domains.documents.service._storage``). Nothing else in the domain — the
router, service business logic, or the ``storage_key`` column itself — needs to
change, since ``storage_key`` is already an opaque string as far as the rest of
the domain is concerned.
"""

from __future__ import annotations

import pathlib
import uuid
from typing import Protocol


class StorageBackend(Protocol):
    def save(self, data: bytes) -> str:
        """Persist ``data`` and return an opaque storage key that ``load`` can
        later resolve back to the same bytes."""
        ...

    def load(self, storage_key: str) -> bytes:
        """Return the bytes previously stored under ``storage_key``.

        Raises ``FileNotFoundError`` if the key is unknown.
        """
        ...


class LocalFilesystemBackend:
    """Writes each document under ``base_dir/<uuid4 hex>``.

    The directory is created lazily on first use and is NOT part of the git
    tree (see the repo ``.gitignore``) — it is a runtime cache, not a source of
    truth the way the database row is. Losing it loses file *contents*, not the
    document's existence/metadata/audit trail.

    Keys are server-generated opaque UUIDs; ``load`` still normalizes the
    resolved path to stay under ``base_dir`` before reading, so a corrupted or
    hand-crafted key can never escape the storage directory.
    """

    def __init__(self, base_dir: str | pathlib.Path) -> None:
        self._base_dir = pathlib.Path(base_dir)

    def save(self, data: bytes) -> str:
        self._base_dir.mkdir(parents=True, exist_ok=True)
        key = uuid.uuid4().hex
        (self._base_dir / key).write_bytes(data)
        return key

    def load(self, storage_key: str) -> bytes:
        base = self._base_dir.resolve()
        candidate = (self._base_dir / storage_key).resolve()
        if candidate != base and base not in candidate.parents:
            raise FileNotFoundError(storage_key)
        try:
            return candidate.read_bytes()
        except FileNotFoundError:
            raise FileNotFoundError(storage_key) from None
