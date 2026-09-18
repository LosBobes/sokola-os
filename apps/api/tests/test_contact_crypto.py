"""Contact protection: what the AEAD and the keyed fingerprint actually promise.

The point of these tests is not that encryption round-trips — that would pass
with a Caesar cipher. It is the three properties M04 §2.0 is buying:

* a ciphertext is bound to the field it was written for, so it cannot be moved;
* a tampered ciphertext is refused, not decoded into something plausible;
* the fingerprint is *keyed*, so the column alone does not reveal the contacts.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

import pytest
from app.config import Settings, get_settings
from app.main import _guard_contact_keys
from app.platform import crypto
from app.platform.crypto import ContactCryptoError

EMAIL = "Ana.Markovic@Example.Invalid"
SCHOOL_A = "school/org_aaaaaaaaaaaaaaaaaaaaaaaaaa/contact_email"
SCHOOL_B = "school/org_bbbbbbbbbbbbbbbbbbbbbbbbbb/contact_email"


def _key() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


@pytest.fixture
def two_versions(monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
    """A keyring where version 2 is current and version 1 is still readable."""
    v1, v2 = _key(), _key()
    monkeypatch.setattr(
        get_settings(), "contact_encryption_keys", f"1:{v1},2:{v2}", raising=True
    )
    return v1, v2


# ---------------------------------------------------------------------------
# EncryptedContact
# ---------------------------------------------------------------------------


def test_a_contact_round_trips_under_its_own_context() -> None:
    sealed = crypto.encrypt_contact(EMAIL, context=SCHOOL_A)
    assert EMAIL not in sealed
    assert crypto.decrypt_contact(sealed, context=SCHOOL_A) == EMAIL


def test_a_ciphertext_moved_to_another_row_will_not_decrypt() -> None:
    """The reason the context is authenticated: copying school A's contact
    column into school B's row has to fail, not read back as B's contact."""
    sealed = crypto.encrypt_contact(EMAIL, context=SCHOOL_A)
    with pytest.raises(ContactCryptoError, match="authentication"):
        crypto.decrypt_contact(sealed, context=SCHOOL_B)


def test_a_tampered_ciphertext_is_refused() -> None:
    sealed = crypto.encrypt_contact(EMAIL, context=SCHOOL_A)
    version, _, body = sealed.partition(".")
    raw = bytearray(base64.urlsafe_b64decode(body))
    raw[-1] ^= 0x01  # flip one bit of the GCM tag
    tampered = f"{version}.{base64.urlsafe_b64encode(bytes(raw)).decode('ascii')}"

    with pytest.raises(ContactCryptoError, match="authentication"):
        crypto.decrypt_contact(tampered, context=SCHOOL_A)


def test_the_same_contact_encrypts_differently_every_time() -> None:
    """A deterministic ciphertext would let anyone holding the column tell which
    two schools share a contact, without decrypting anything."""
    first = crypto.encrypt_contact(EMAIL, context=SCHOOL_A)
    second = crypto.encrypt_contact(EMAIL, context=SCHOOL_A)
    assert first != second
    assert crypto.decrypt_contact(second, context=SCHOOL_A) == EMAIL


def test_rotation_writes_under_the_new_key_and_still_reads_the_old(
    two_versions: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    v1, v2 = two_versions
    monkeypatch.setattr(get_settings(), "contact_encryption_keys", f"1:{v1}")
    written_before = crypto.encrypt_contact(EMAIL, context=SCHOOL_A)
    assert crypto.stored_key_version(written_before) == 1

    # Rotate: add version 2, change nothing else, re-encrypt nothing.
    monkeypatch.setattr(get_settings(), "contact_encryption_keys", f"1:{v1},2:{v2}")
    written_after = crypto.encrypt_contact(EMAIL, context=SCHOOL_A)

    assert crypto.stored_key_version(written_after) == 2
    assert crypto.decrypt_contact(written_before, context=SCHOOL_A) == EMAIL
    assert crypto.decrypt_contact(written_after, context=SCHOOL_A) == EMAIL


def test_dropping_a_key_version_names_it_rather_than_failing_obscurely(
    two_versions: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    v1, v2 = two_versions
    sealed = crypto.encrypt_contact(EMAIL, context=SCHOOL_A)
    monkeypatch.setattr(get_settings(), "contact_encryption_keys", f"1:{v1}")

    with pytest.raises(ContactCryptoError, match="version 2"):
        crypto.decrypt_contact(sealed, context=SCHOOL_A)


def test_a_malformed_stored_value_is_rejected() -> None:
    for bad in ("", "not-encrypted-at-all", "v1.", "1.abcd", "vx.abcd"):
        with pytest.raises(ContactCryptoError):
            crypto.decrypt_contact(bad, context=SCHOOL_A)


def test_an_empty_contact_is_never_encrypted() -> None:
    with pytest.raises(ContactCryptoError):
        crypto.encrypt_contact("", context=SCHOOL_A)


# ---------------------------------------------------------------------------
# Fingerprint256
# ---------------------------------------------------------------------------


def test_the_fingerprint_is_keyed_not_a_plain_digest() -> None:
    """If it equalled sha256(email), the column would be a contact list: the
    space of plausible addresses is small enough to enumerate."""
    canonical = crypto.canonical_email(EMAIL)
    digest, _ = crypto.fingerprint(canonical)

    assert digest != hashlib.sha256(canonical.encode()).hexdigest()
    key = crypto.fingerprint_keyring().write_key
    assert digest == hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()


def test_the_fingerprint_is_stable_and_distinguishes_addresses() -> None:
    a, version = crypto.fingerprint(crypto.canonical_email(EMAIL))
    again, _ = crypto.fingerprint(crypto.canonical_email(EMAIL))
    other, _ = crypto.fingerprint(crypto.canonical_email("drugi@example.invalid"))

    assert a == again
    assert a != other
    assert version == 1


def test_a_rotated_fingerprint_key_needs_the_old_version_to_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dedupe against rows written before a rotation only works if the stored
    key version is used to re-derive. Otherwise a duplicate reads as new."""
    v1, v2 = _key(), _key()
    canonical = crypto.canonical_email(EMAIL)

    monkeypatch.setattr(get_settings(), "contact_fingerprint_keys", f"1:{v1}")
    old_digest, old_version = crypto.fingerprint(canonical)

    monkeypatch.setattr(get_settings(), "contact_fingerprint_keys", f"1:{v1},2:{v2}")
    new_digest, new_version = crypto.fingerprint(canonical)

    assert (old_version, new_version) == (1, 2)
    assert new_digest != old_digest
    assert crypto.fingerprint_with_version(canonical, old_version) == old_digest


def test_encryption_and_fingerprint_keyrings_are_independent() -> None:
    """Rotating one must not force the other. They answer different questions and
    §2.2 stores their versions separately for exactly that reason."""
    settings = get_settings()
    assert settings.contact_encryption_keys != settings.contact_fingerprint_keys
    assert crypto.encryption_keyring().write_key != crypto.fingerprint_keyring().write_key


# ---------------------------------------------------------------------------
# Canonical form and masking
# ---------------------------------------------------------------------------


def test_canonical_email_trims_and_lowercases_only() -> None:
    assert crypto.canonical_email("  Ana@Example.INVALID ") == "ana@example.invalid"
    # Dots and +tags are provider conventions; treating them as equal would
    # merge two genuinely different mailboxes.
    a, _ = crypto.fingerprint(crypto.canonical_email("a.b@example.invalid"))
    b, _ = crypto.fingerprint(crypto.canonical_email("ab@example.invalid"))
    assert a != b


def test_a_non_address_is_not_canonicalized() -> None:
    for bad in ("ana", "@example.invalid", "ana@", "   "):
        with pytest.raises(ContactCryptoError):
            crypto.canonical_email(bad)


def test_the_masked_value_shows_enough_to_recognise_and_no_more() -> None:
    assert crypto.mask_email("ana.markovic@example.invalid") == "an***@example.invalid"
    # A short local part gives away proportionally less.
    assert crypto.mask_email("ana@example.invalid") == "a***@example.invalid"
    assert crypto.mask_email("a@example.invalid") == "a***@example.invalid"


def test_phone_is_canonicalized_to_e164() -> None:
    assert crypto.canonical_phone(" +381 64 123-4567 ") == "+381641234567"
    for bad in ("0641234567", "+0641234567", "+381", "381641234567"):
        with pytest.raises(ContactCryptoError):
            crypto.canonical_phone(bad)


# ---------------------------------------------------------------------------
# Keyring parsing and the boot guard
# ---------------------------------------------------------------------------


def test_the_highest_version_is_the_one_written_under() -> None:
    v1, v2, v3 = _key(), _key(), _key()
    keyring = crypto.parse_keyring(f"2:{v2},1:{v1},3:{v3}", what="t")
    assert keyring.write_version == 3
    assert set(keyring.keys) == {1, 2, 3}


def test_a_broken_keyring_is_rejected_with_the_reason() -> None:
    good = _key()
    cases = {
        "": "empty",
        "1": "'<version>:<base64 key>'",
        "x:" + good: "integer",
        "0:" + good: "1 or greater",
        "1:not-base64!!": "base64",
        "1:" + base64.b64encode(b"short").decode(): "32 bytes",
        f"1:{good},1:{_key()}": "twice",
    }
    for raw, expected in cases.items():
        with pytest.raises(ContactCryptoError, match=expected):
            crypto.parse_keyring(raw, what="t")


def test_a_generated_key_is_accepted() -> None:
    assert crypto.parse_keyring(f"1:{crypto.generate_key()}", what="t").write_version == 1


def test_production_refuses_the_published_dev_keys() -> None:
    settings = Settings(environment="production")
    with pytest.raises(RuntimeError, match="CONTACT_ENCRYPTION_KEYS"):
        _guard_contact_keys(settings)

    settings = Settings(environment="production", contact_encryption_keys=f"1:{_key()}")
    with pytest.raises(RuntimeError, match="CONTACT_FINGERPRINT_KEYS"):
        _guard_contact_keys(settings)

    real = Settings(
        environment="production",
        contact_encryption_keys=f"1:{_key()}",
        contact_fingerprint_keys=f"1:{_key()}",
    )
    _guard_contact_keys(real)


def test_a_mistyped_key_stops_the_app_at_boot_not_at_first_read() -> None:
    with pytest.raises(ContactCryptoError):
        _guard_contact_keys(Settings(contact_encryption_keys="1:oops"))
