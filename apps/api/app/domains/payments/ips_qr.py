"""NBS IPS QR payload for a Serbian payment slip (uplatnica).

What this is, and deliberately is not
-------------------------------------
The QR code is an **aid for filling in a payment order**, nothing more. A parent
scans it in their own banking app so they do not have to retype the school's
account number, the amount and the reference number by hand. Money then moves
directly from the parent's account to the school's, through their bank.

SOKOLA OS is not in that path. It does not initiate the transfer, it is not
told when the transfer happens, and it never marks a charge as paid on its own:
an authorised person at the school confirms the payment after checking the bank
account, exactly as they would for a cash or counter payment. Cards, payment
gateways, bank integrations, automatic reconciliation and automatic refunds are
all out of scope, and generating this payload must never be mistaken for any of
them.

Format
------
IPS QR (NBS specification, version 01) is a flat ``key:value`` string with
``|`` between fields. The fields used here:

===== ===========================================================
K     Identification code. ``PR`` = payment request.
V     Format version, ``01``.
C     Character set, ``1`` = UTF-8.
R     Payee account, 18 digits, no dashes or spaces.
N     Payee, as ``name``, ``address`` and ``city`` on separate lines.
I     Currency + amount, e.g. ``RSD3000,00`` (comma as decimal separator).
P     Payer, same line layout as ``N``. Omitted when unknown.
SF    Payment code (šifra plaćanja), 3 digits.
S     Purpose of payment, free text.
RO    Model + reference number, e.g. ``97`` + the reference.
===== ===========================================================

Every value is sanitised: ``|`` and newlines would otherwise let a school's own
name or a charge description terminate a field early and forge the rest of the
payload, so they are stripped from user-supplied text before assembly.
"""

from __future__ import annotations

import re

#: Payment code for a service/membership fee paid by a citizen ("ostale usluge").
DEFAULT_PAYMENT_CODE = "189"

#: Reference model 97 carries an ISO 7064 MOD 97-10 control number.
REFERENCE_MODEL = "97"

_ACCOUNT_DIGITS = 18
_FIELD_SEPARATOR = "|"
_LINE_SEPARATOR = "\n"


class PaymentSlipError(ValueError):
    """The school has not supplied enough valid payee data to build a slip."""


def normalize_account(raw: str) -> str:
    """Strip formatting from a bank account and validate its length.

    Serbian accounts are written many ways (``160-0000000123456-78``,
    ``160 5000 1234567 89``); the QR carries the bare 18 digits.
    """
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) != _ACCOUNT_DIGITS:
        raise PaymentSlipError(
            "Broj računa škole mora imati 18 cifara da bi se generisala uplatnica."
        )
    return digits


def format_amount(amount_minor: int, currency: str = "RSD") -> str:
    """``I`` field: currency code followed by the amount, comma-separated.

    Formatted from integer minor units so the printed amount is exactly the
    amount charged , no float rounding anywhere between the ledger and the QR.
    """
    if amount_minor < 0:
        raise PaymentSlipError("Iznos uplate ne može biti negativan.")
    return f"{currency}{amount_minor // 100},{amount_minor % 100:02d}"


def mod97_reference(base: str) -> str:
    """Append the ISO 7064 MOD 97-10 control digits to a numeric base.

    Model 97 requires them, and a reference number that fails the bank's own
    check is worse than no QR at all: the payer's app accepts the scan and the
    transfer is rejected later.
    """
    digits = re.sub(r"\D", "", base or "")
    if not digits:
        raise PaymentSlipError("Poziv na broj ne može biti prazan.")
    check = 98 - (int(digits + "00") % 97)
    return f"{check:02d}{digits}"


#: Digits in a generated payment reference base (before model + control digits).
REFERENCE_BASE_DIGITS = 12

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def reference_base_from_id(entity_id: str) -> str:
    """Derive a stable numeric reference base from a prefixed ULID.

    A payment reference has to be digits only, but our ids are
    ``chg_<ULID>``. Decoding the ULID's Crockford base32 to an integer and
    keeping the low :data:`REFERENCE_BASE_DIGITS` gives a value that is
    deterministic (the same charge always prints the same reference, so a
    re-issued slip matches the first one) and derived from a ULID's
    timestamp+randomness, which makes a collision within one school's charges
    a non-issue in practice. It is stored on the charge anyway, so
    reconciliation is an indexed lookup rather than a recomputation.
    """
    _, _, ulid = entity_id.rpartition("_")
    value = 0
    for char in ulid.upper():
        index = _CROCKFORD.find(char)
        if index < 0:
            continue  # tolerate separators / unexpected characters
        value = value * 32 + index
    return str(value % (10**REFERENCE_BASE_DIGITS)).zfill(REFERENCE_BASE_DIGITS)


def _sanitize(value: str | None, *, limit: int) -> str:
    """Collapse anything that could break the flat payload, then clip to length."""
    if not value:
        return ""
    cleaned = value.replace(_FIELD_SEPARATOR, " ").replace("\r", " ").replace("\n", " ")
    return " ".join(cleaned.split())[:limit]


def _party(name: str | None, address: str | None, city: str | None, *, limit: int) -> str:
    """``N``/``P`` field: up to three lines, empty ones dropped."""
    lines = [
        _sanitize(name, limit=limit),
        _sanitize(address, limit=limit),
        _sanitize(city, limit=limit),
    ]
    return _LINE_SEPARATOR.join(line for line in lines if line)


def build_ips_qr_payload(
    *,
    account: str,
    payee_name: str,
    payee_address: str | None,
    payee_city: str | None,
    amount_minor: int,
    currency: str,
    purpose: str,
    reference: str,
    payer_name: str | None = None,
    payment_code: str = DEFAULT_PAYMENT_CODE,
) -> str:
    """Assemble the IPS QR string for one charge.

    ``reference`` is the bare base (typically the charge id's digits); the
    control digits and the ``97`` model prefix are added here so callers cannot
    forget them.
    """
    payee = _party(payee_name, payee_address, payee_city, limit=70)
    if not payee:
        raise PaymentSlipError("Škola nema unet naziv primaoca uplate.")

    fields = [
        "K:PR",
        "V:01",
        "C:1",
        f"R:{normalize_account(account)}",
        f"N:{payee}",
        f"I:{format_amount(amount_minor, currency)}",
    ]
    payer = _party(payer_name, None, None, limit=70)
    if payer:
        fields.append(f"P:{payer}")
    fields.extend(
        [
            f"SF:{payment_code}",
            f"S:{_sanitize(purpose, limit=35) or 'Uplata'}",
            f"RO:{REFERENCE_MODEL}{mod97_reference(reference)}",
        ]
    )
    return _FIELD_SEPARATOR.join(fields)
