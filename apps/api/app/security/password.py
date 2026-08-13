"""Local password hashing, salt **and** pepper.

Uses stdlib :func:`hashlib.scrypt`, a memory-hard KDF built into Python, so we
add no third-party dependency. The
stored value is a self-describing ``scrypt$N$r$p$salt$key`` string: the salt is
random per password and the parameters travel with the hash, so they can be
raised later without invalidating existing rows.

Two secrets protect the password, at two layers:

- **Salt**, random per password, stored alongside the hash. Defeats rainbow
  tables and stops two identical passwords hashing to the same value.
- **Pepper**, a single application secret (``SOKOLA_PASSWORD_PEPPER``) held in
  the environment, **never** in the database. Folded into every password via
  HMAC before the salt + scrypt. A stolen ``auth_account`` table therefore
  can't be brute-forced offline without also compromising the server config.

Unlike OIDC (which stores only an identity link), a password is a secret we
verify against, so we store its hash, never the password itself.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from app.config import get_settings

# scrypt cost parameters. n=2**14 needs ~16 MiB per hash, deliberately slow to
# brute-force while staying comfortable for a single login request.
_N = 2**14
_R = 8
_P = 1
_SALT_BYTES = 16
_KEY_LEN = 32
# OpenSSL rejects the hash if maxmem is below 128*n*r bytes; give it headroom.
_MAXMEM = 128 * _N * _R * 2

# A password shorter than this is refused at registration.
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 200


def _peppered(password: str) -> bytes:
    """HMAC the password under the server-side pepper before it ever reaches the
    KDF. Using HMAC (not concatenation) keeps the pepper's bytes and length from
    influencing the scrypt input in a recoverable way, and yields a fixed-size
    block regardless of password length."""
    pepper = get_settings().password_pepper.encode("utf-8")
    return hmac.new(pepper, password.encode("utf-8"), hashlib.sha256).digest()


def _derive(password: str, salt: bytes, n: int, r: int, p: int, key_len: int) -> bytes:
    return hashlib.scrypt(
        _peppered(password), salt=salt, n=n, r=r, p=p, dklen=key_len, maxmem=_MAXMEM
    )


def hash_password(password: str) -> str:
    """Return a self-describing ``scrypt$N$r$p$salt$key`` string."""
    salt = secrets.token_bytes(_SALT_BYTES)
    key = _derive(password, salt, _N, _R, _P, _KEY_LEN)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of ``password`` against a stored hash. Never raises on
    a malformed stored value, a corrupt row simply fails to verify."""
    try:
        scheme, n_s, r_s, p_s, salt_hex, key_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(key_hex)
        candidate = _derive(password, salt, int(n_s), int(r_s), int(p_s), len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, expected)
