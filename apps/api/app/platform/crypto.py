"""Contact protection: AEAD ciphertext and keyed fingerprints.

M04 §2.0 names two logical types this module implements, and they are
deliberately different things:

``EncryptedContact``
    AEAD ciphertext carrying a **key version** and an **authenticated context**.
    The context is bound into the ciphertext, not stored beside it, so a
    ciphertext lifted out of one row and pasted into another fails to decrypt
    rather than silently reading as that other row's contact.

``Fingerprint256``
    A **keyed** HMAC-SHA-256 over the canonical value. Not a plain hash: an
    unkeyed digest of an email address is trivially reversible by guessing, so
    a leaked fingerprint column would be a leaked contact list. It carries its
    own key version, separate from the encryption key's, because deduplication
    and confidentiality are rotated on different schedules and by different
    reasons. It is a dedupe key only, never an identity or account-linking key.

Keys live in the environment (``SOKOLA_CONTACT_ENCRYPTION_KEYS``,
``SOKOLA_CONTACT_FINGERPRINT_KEYS``), the same place as the session secret and
the password pepper, and never in the database or the repository. That is the
weakest form of key management the contract tolerates and it is stated here
plainly: there is no KMS, no HSM and no envelope encryption in this increment,
so a host compromise that reads the environment reads the contacts. What the
keyring *does* buy is rotation without re-encryption, and that is what makes a
KMS a drop-in replacement later: every stored value names the version that
produced it, so a future backend only has to answer "give me key N".

Plaintext contacts never reach a log, audit entry, event payload or metric.
:func:`mask_email` exists so an admin screen can still show *something*.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

#: AES-256-GCM. 12-byte nonce is the size the construction is defined for.
_KEY_BYTES = 32
_NONCE_BYTES = 12

#: Stored form: ``v<version>.<base64url(nonce || ciphertext || tag)>``. Version
#: first and in the clear, because choosing the key is what has to happen before
#: anything can be decoded.
_STORED = re.compile(r"^v(?P<version>[0-9]+)\.(?P<body>[A-Za-z0-9_-]+=*)$")


class ContactCryptoError(RuntimeError):
    """Configuration or integrity failure. Never carries a plaintext value."""


@dataclass(frozen=True)
class Keyring:
    """Every key the process can *read* with, and the one it *writes* with.

    Rotation is: generate a key, append it with the next version, point
    ``write_version`` at it. Old ciphertext keeps decrypting under its own
    version, so nothing has to be rewritten in the same deploy as the rotation.
    """

    keys: dict[int, bytes]
    write_version: int

    def read(self, version: int) -> bytes:
        key = self.keys.get(version)
        if key is None:
            # The version is in the clear in the stored value, so naming it
            # leaks nothing and is the one fact an operator needs.
            raise ContactCryptoError(f"no contact key configured for version {version}")
        return key

    @property
    def write_key(self) -> bytes:
        return self.read(self.write_version)


def parse_keyring(raw: str, *, what: str) -> Keyring:
    """Parse ``"1:<base64>,2:<base64>"``. The highest version is the write key.

    Making the newest version the writer by construction removes the failure
    where a key is added but never switched to, which looks like a successful
    rotation and is not one.
    """
    keys: dict[int, bytes] = {}
    for entry in (e.strip() for e in raw.split(",")):
        if not entry:
            continue
        version_text, _, material = entry.partition(":")
        if not material:
            raise ContactCryptoError(f"{what} entry must be '<version>:<base64 key>'")
        try:
            version = int(version_text)
        except ValueError:
            raise ContactCryptoError(f"{what} key version must be an integer") from None
        if version < 1:
            raise ContactCryptoError(f"{what} key version must be 1 or greater")
        try:
            key = base64.b64decode(material, validate=True)
        except Exception:
            raise ContactCryptoError(f"{what} key must be base64") from None
        if len(key) != _KEY_BYTES:
            raise ContactCryptoError(f"{what} key must be {_KEY_BYTES} bytes ({len(key)} given)")
        if version in keys:
            raise ContactCryptoError(f"{what} key version {version} is declared twice")
        keys[version] = key
    if not keys:
        raise ContactCryptoError(f"{what} keyring is empty")
    return Keyring(keys=keys, write_version=max(keys))


def encryption_keyring() -> Keyring:
    return parse_keyring(get_settings().contact_encryption_keys, what="contact encryption")


def fingerprint_keyring() -> Keyring:
    return parse_keyring(get_settings().contact_fingerprint_keys, what="contact fingerprint")


def generate_key() -> str:
    """A fresh base64 key, for operators adding a version to a keyring."""
    return base64.b64encode(secrets.token_bytes(_KEY_BYTES)).decode("ascii")


# ---------------------------------------------------------------------------
# EncryptedContact
# ---------------------------------------------------------------------------


def encrypt_contact(plaintext: str, *, context: str) -> str:
    """Encrypt under the current key, binding ``context`` into the ciphertext.

    ``context`` identifies the field this value belongs to, e.g.
    ``school/sch_01J.../contact_email``. It is authenticated but not encrypted,
    and it is not stored: decryption reconstructs it from the row being read, so
    a ciphertext that has been moved fails :class:`ContactCryptoError` instead of
    decrypting into the wrong record.
    """
    if not plaintext:
        raise ContactCryptoError("refusing to encrypt an empty contact value")
    keyring = encryption_keyring()
    nonce = secrets.token_bytes(_NONCE_BYTES)
    sealed = AESGCM(keyring.write_key).encrypt(
        nonce, plaintext.encode("utf-8"), context.encode("utf-8")
    )
    body = base64.urlsafe_b64encode(nonce + sealed).decode("ascii")
    return f"v{keyring.write_version}.{body}"


def decrypt_contact(stored: str, *, context: str) -> str:
    match = _STORED.match(stored)
    if match is None:
        raise ContactCryptoError("stored contact is not in the expected form")
    keyring = encryption_keyring()
    key = keyring.read(int(match["version"]))
    raw = base64.urlsafe_b64decode(match["body"])
    if len(raw) <= _NONCE_BYTES:
        raise ContactCryptoError("stored contact is truncated")
    try:
        opened = AESGCM(key).decrypt(
            raw[:_NONCE_BYTES], raw[_NONCE_BYTES:], context.encode("utf-8")
        )
    except InvalidTag:
        # Wrong key, wrong context, or a tampered row. They are indistinguishable
        # by design, and saying which one would itself be an oracle.
        raise ContactCryptoError("contact failed authentication") from None
    return opened.decode("utf-8")


def stored_key_version(stored: str) -> int:
    match = _STORED.match(stored)
    if match is None:
        raise ContactCryptoError("stored contact is not in the expected form")
    return int(match["version"])


# ---------------------------------------------------------------------------
# Fingerprint256
# ---------------------------------------------------------------------------


def fingerprint(value: str) -> tuple[str, int]:
    """Keyed digest of an already-canonical value, with the key version used.

    Returns both because the version has to be stored next to the digest for the
    comparison to still work after a rotation: two rows fingerprinted under
    different versions are simply not comparable, and the version is how a
    lookup knows to re-derive rather than to conclude "no match".
    """
    if not value:
        raise ContactCryptoError("refusing to fingerprint an empty value")
    keyring = fingerprint_keyring()
    digest = hmac.new(keyring.write_key, value.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest, keyring.write_version


def fingerprint_with_version(value: str, version: int) -> str:
    """Re-derive under a specific version, to match rows written before a rotation."""
    if not value:
        raise ContactCryptoError("refusing to fingerprint an empty value")
    key = fingerprint_keyring().read(version)
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Canonical form and the masked display value
# ---------------------------------------------------------------------------


def canonical_email(email: str) -> str:
    """Trim and lowercase, and nothing else.

    Deliberately not "clever": stripping dots or ``+tag`` suffixes is a
    provider-specific convention, and applying it uniformly would fingerprint two
    genuinely different mailboxes as one. Dedupe that under-matches is a nuisance;
    dedupe that over-matches merges two schools' contacts.
    """
    canonical = email.strip().lower()
    if "@" not in canonical or canonical.startswith("@") or canonical.endswith("@"):
        raise ContactCryptoError("contact email is not an address")
    return canonical


def mask_email(email: str) -> str:
    """``ana.markovic@example.com`` -> ``an***@example.com``.

    Enough for an admin to recognise a contact they already know, not enough to
    learn one they do not. The domain stays whole: it is the part that makes the
    row identifiable to its owner, and it is rarely the secret.
    """
    canonical = canonical_email(email)
    local, _, domain = canonical.partition("@")
    shown = local[:2] if len(local) > 3 else local[:1]
    return f"{shown}***@{domain}"


def canonical_phone(phone: str) -> str:
    """E.164: a leading ``+`` and digits. Separators are formatting, not data."""
    cleaned = re.sub(r"[\s()./-]", "", phone.strip())
    if not re.fullmatch(r"\+[1-9][0-9]{6,14}", cleaned):
        raise ContactCryptoError("contact phone is not in E.164 form")
    return cleaned
