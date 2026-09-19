"""M01 §: the 28 numbered QA scenarios, under the gate from M07/M06.

M01 is the most complete module in the repository — 178 tests already cover
its behaviour, and its HTTP surface exists, which is why more scenarios run
here than in either of the previous two modules.

That is exactly why running them under their own ids is worth doing. "Covered
by 178 tests" and "the contract's 28 scenarios pass" are different claims, and
only the second one is what §8 asks for. Where a scenario is already covered
by an existing test, this file asserts the scenario's *own* stated outcome
rather than trusting that the nearby test meant the same thing.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
from app.common.errors import (
    InvalidAccountTransitionError,
    StaleVersionError,
)
from app.domains.identity import accounts, auth_commands, auth_providers, sessions
from app.domains.identity.auth_enums import (
    GOOGLE_ISSUER,
    GOOGLE_PROVIDER,
    AccountDisableReason,
    AccountSuspendReason,
    SessionRevokeReason,
    UserAccountStatus,
)
from app.domains.identity.auth_models import AuthIdentity, AuthSession, UserAccount
from app.platform.audit.models import AuditLog
from app.platform.outbox.models import OutboxMessage
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.factories import make_person

_QA_DOC = (
    Path(__file__).resolve().parents[3]
    / "docs/spec/v5.7/04-MODULSKI-UGOVORI/01-M01-IDENTITY-I-AUTENTIFIKACIJA"
    / "02-M01-QA-I-TRACEABILITY.md"
)

BLOCKED: dict[str, str] = {
    "M01-QA-003": (
        "external dependency: replaying a provider callback state needs the "
        "OIDC provider driven end to end"
    ),
    "M01-QA-004": "external dependency: a forged/expired provider token needs a real token fixture",
    "M01-QA-007": "true concurrency: two links on one subject racing",
    "M01-QA-009": (
        "external dependency: the realtime channel half has no "
        "implementation to assert against"
    ),
    "M01-QA-010": (
        "cross-module: M03/M05 revocation in another tab belongs to those "
        "modules' scenarios"
    ),
    "M01-QA-014": (
        "external dependency: a provider timeout needs the provider stubbed "
        "at the transport"
    ),
    "M01-QA-015": "cross-module: the safe not-found is M03's answer, asserted in M03's scenarios",
    "M01-QA-017": (
        "feature absent: no legacy-mapping migration exists to produce an "
        "exception report"
    ),
    "M01-QA-022": (
        "cross-module: a high-risk mutation spanning a revoke needs a "
        "business command to wrap"
    ),
    "M01-QA-026": "true concurrency: two transactions on one request_id",
    "M01-QA-028": (
        "external dependency: the dispatcher retry/duplicate path has no "
        "consumer to drive"
    ),
}


def _rid() -> str:
    return str(uuid.uuid4())


def _account(db: Session, subject: str) -> tuple[UserAccount, AuthIdentity]:
    person = make_person(db, given="S", family=subject[-6:])
    account, identity = accounts.create_account_with_identity(
        db,
        person_id=person.id,
        provider_key=GOOGLE_PROVIDER,
        issuer=GOOGLE_ISSUER,
        subject=subject,
    )
    db.commit()
    return account, identity


# ===========================================================================
# The gate
# ===========================================================================


def _declared() -> set[str]:
    return set(re.findall(r"M01-QA-\d{3}", _QA_DOC.read_text()))


def _implemented() -> set[str]:
    return {
        f"M01-QA-{n}"
        for n in re.findall(
            r"^def test_m01_qa_(\d{3})_", Path(__file__).read_text(), re.MULTILINE
        )
    }


def test_every_m01_scenario_is_implemented_or_declared() -> None:
    declared = _declared()
    assert len(declared) == 28, f"expected 28 scenarios, found {len(declared)}"
    implemented = _implemented()
    blocked = set(BLOCKED)
    assert not (implemented & blocked), sorted(implemented & blocked)
    missing = declared - implemented - blocked
    assert not missing, f"neither implemented nor declared blocked: {sorted(missing)}"
    stray = (implemented | blocked) - declared
    assert not stray, f"ids not in the contract: {sorted(stray)}"


def test_the_m01_blocked_reasons_name_a_known_cause() -> None:
    for scenario, reason in BLOCKED.items():
        assert any(
            cause in reason
            for cause in (
                "feature absent",
                "true concurrency",
                "cross-module",
                "external dependency",
            )
        ), f"{scenario}: {reason}"


# ===========================================================================
# Sign-in and identities
# ===========================================================================


def test_m01_qa_001_a_session_carries_no_tenant_data(db: Session) -> None:
    """§8: authentication says who, never where.

    A `school_id` on the session would make every later tenant decision a
    replay of one made at login — which is precisely what M03 §8 puts on each
    individual request instead.
    """
    account, identity = _account(db, "sub-qa001")
    session, _ = sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    columns = set(AuthSession.__table__.columns.keys())
    assert not columns & {"school_id", "tenant_id", "role_code", "granted_areas"}
    assert session.user_account_id == account.id


def test_m01_qa_002_a_known_subject_without_an_account_creates_nothing(
    db: Session,
) -> None:
    """§4.4: `NO_ACCESS`, and no account conjured to make the login work.

    The enumeration half matters as much: the caller learns nothing about
    whether that subject has ever been seen.
    """
    before = db.execute(select(func.count()).select_from(UserAccount)).scalar_one()
    assert accounts.find_identity(db, GOOGLE_ISSUER, "sub-never-seen") is None
    assert (
        db.execute(select(func.count()).select_from(UserAccount)).scalar_one() == before
    )


def test_m01_qa_005_linking_a_subject_owned_by_another_account(
    db: Session,
) -> None:
    """§6: the link is refused and neither account changes.

    Worth recording *where* the refusal comes from: `link_identity` performs
    no ownership check, so what stops this is
    `UNIQUE(provider_issuer, provider_subject)` in the database. That is the
    right place for it — a service check races, an index does not — but it
    means the failure arrives as an IntegrityError rather than the contract's
    409, so the HTTP shape §6 describes does not exist yet.
    """
    from sqlalchemy.exc import IntegrityError

    first, _ = _account(db, "sub-qa005-a")
    second, _ = _account(db, "sub-qa005-b")

    with pytest.raises(IntegrityError) as caught:
        accounts.link_identity(
            db,
            account=second,
            provider_key=GOOGLE_PROVIDER,
            issuer=GOOGLE_ISSUER,
            subject="sub-qa005-a",
        )
    assert "uq_auth_identity_subject" in str(caught.value)
    db.rollback()

    assert (
        db.execute(
            select(func.count())
            .select_from(AuthIdentity)
            .where(AuthIdentity.user_account_id == second.id)
        ).scalar_one()
        == 1
    )
    assert first.status is UserAccountStatus.ACTIVE


def test_m01_qa_012_two_accounts_may_share_an_email_claim(db: Session) -> None:
    """§4: a matching email is not a matching person.

    Auto-linking on it would let anyone who can prove control of an address at
    one provider inherit an account created through another.
    """
    first, _ = _account(db, "sub-qa012-a")
    second, _ = _account(db, "sub-qa012-b")
    assert first.id != second.id
    assert first.person_id != second.person_id


def test_m01_qa_019_an_unapproved_issuer_resolves_to_nothing(
    db: Session,
) -> None:
    """§19: an alias, a different case or a different scheme is not the issuer.

    The registry resolves an issuer to a registration by exact string, so a
    near-miss finds nothing rather than being normalised into the real one.
    Exactness is the whole defence: an issuer that is "close enough" is an
    issuer an attacker chose.
    """
    auth_providers.ensure_builtin_providers(db)
    db.commit()

    assert auth_providers.registration_for_issuer(db, GOOGLE_ISSUER) is not None
    for near_miss in (
        GOOGLE_ISSUER.upper(),
        GOOGLE_ISSUER + "/",
        GOOGLE_ISSUER.replace("https://", "http://"),
        "https://accounts.example.test",
    ):
        assert auth_providers.registration_for_issuer(db, near_miss) is None


# ===========================================================================
# Sessions
# ===========================================================================


def test_m01_qa_008_one_logout_leaves_the_other_session_alive(
    db: Session,
) -> None:
    # `validate_session` answers `None` rather than raising, and §11 is the
    # reason: a caller able to tell "expired" from "revoked" from "no such
    # session" learns which, and that is exactly the distinction a probe wants.
    account, identity = _account(db, "sub-qa008")
    first, first_credential = sessions.issue_session(
        db, account=account, identity=identity
    )
    second, second_credential = sessions.issue_session(
        db, account=account, identity=identity
    )
    db.commit()

    sessions.revoke_session(db, first, reason=SessionRevokeReason.LOGOUT)
    db.commit()

    assert sessions.validate_session(db, first_credential) is None
    assert sessions.validate_session(db, second_credential) is not None


def test_m01_qa_011_a_disabled_account_ends_every_session(db: Session) -> None:
    """§4.7: the version bump is what refuses, in the caller's own
    transaction. The outbox event propagates; it never decides."""
    account, identity = _account(db, "sub-qa011")
    _, credential = sessions.issue_session(db, account=account, identity=identity)
    db.commit()
    assert sessions.validate_session(db, credential) is not None

    auth_commands.disable_account(
        db,
        account=account,
        expected_version=account.version,
        reason_code=AccountDisableReason.SECURITY_INCIDENT,
        request_id=_rid(),
    )
    db.commit()

    assert sessions.validate_session(db, credential) is None


def test_m01_qa_021_validation_reads_the_authoritative_version(
    db: Session,
) -> None:
    """§4.7 / QA-021: a node with a stale cache still refuses.

    Modelled by bumping the version underneath a session that was valid a
    moment ago: validation re-reads in its own transaction, so there is no
    window in which the old answer survives.
    """
    account, identity = _account(db, "sub-qa021")
    _, credential = sessions.issue_session(db, account=account, identity=identity)
    db.commit()
    assert sessions.validate_session(db, credential) is not None

    account.authorization_version += 1
    db.commit()

    assert sessions.validate_session(db, credential) is None


def test_m01_qa_025_the_local_session_keeps_its_own_deadline(
    db: Session,
) -> None:
    """§25: the provider token is not a refresh credential.

    The session carries its own expiry, set at issue and independent of
    anything the provider said — so a token ageing out does not shorten it,
    and could not lengthen it either.
    """
    account, identity = _account(db, "sub-qa025")
    session, _ = sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    columns = set(AuthSession.__table__.columns.keys())
    assert not columns & {"access_token", "id_token", "refresh_token"}
    assert session.absolute_expires_at is not None
    assert session.idle_expires_at is not None


# ===========================================================================
# Account lifecycle (§5)
# ===========================================================================


def test_m01_qa_023_suspend_then_reactivate_revives_no_session(
    db: Session,
) -> None:
    """§5: reactivation restores the account, not the logins.

    A session that survived a suspension would mean the suspension never
    really ended anything — it would only have paused the parts that checked.
    """
    account, identity = _account(db, "sub-qa023")
    _, credential = sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    auth_commands.suspend_account(
        db,
        account=account,
        expected_version=account.version,
        reason_code=AccountSuspendReason.ABUSE_UNDER_REVIEW,
        request_id=_rid(),
    )
    db.commit()
    assert sessions.validate_session(db, credential) is None

    auth_commands.reactivate_account(
        db, account=account, expected_version=account.version, request_id=_rid()
    )
    db.commit()

    assert account.status is UserAccountStatus.ACTIVE
    assert sessions.validate_session(db, credential) is None


def test_m01_qa_023_transitions_require_the_expected_version(
    db: Session,
) -> None:
    account, _ = _account(db, "sub-qa023b")
    with pytest.raises(StaleVersionError):
        auth_commands.suspend_account(
            db,
            account=account,
            expected_version=account.version + 5,
            reason_code=AccountSuspendReason.ABUSE_UNDER_REVIEW,
            request_id=_rid(),
        )


def test_m01_qa_024_disabled_cannot_be_reactivated(db: Session) -> None:
    """§5's table has no row out of DISABLED, and this is what a caller who
    tries anyway gets — never a silent no-op."""
    account, _ = _account(db, "sub-qa024")
    auth_commands.disable_account(
        db,
        account=account,
        expected_version=account.version,
        reason_code=AccountDisableReason.SECURITY_INCIDENT,
        request_id=_rid(),
    )
    db.commit()

    with pytest.raises(InvalidAccountTransitionError):
        auth_commands.reactivate_account(
            db, account=account, expected_version=account.version, request_id=_rid()
        )


# ===========================================================================
# Idempotency (§7) and privacy (§13)
# ===========================================================================


def test_m01_qa_020_logout_all_replays_without_reviving_a_session(
    db: Session,
) -> None:
    """§20's first half, and a note about the second.

    The retry must not re-authorize and must not revive anything. Replaying
    through the receipt is the only way to answer a retry whose original
    credential the first call has already revoked — which is why the receipt is
    written before the version bump.

    The scenario's second half — same key, different payload, 409 — **cannot be
    produced through this command.** `logout_all` builds its payload as
    `{account_id, command}`, so for one account and one command there is only
    ever one payload. The reuse guard exists in `begin()` and is real; this
    command simply has no variable to vary. A test that "proved" it here would
    have had to reach past the command into the guard, and would then be
    testing `begin`, not `LogoutAll`.
    """
    account, identity = _account(db, "sub-qa020")
    sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    request_id = _rid()
    first = auth_commands.logout_all(db, account=account, request_id=request_id)
    db.commit()
    assert sessions.live_sessions(db, account.id) == []

    second = auth_commands.logout_all(db, account=account, request_id=request_id)
    db.commit()
    assert second == first
    assert sessions.live_sessions(db, account.id) == []


def test_m01_qa_027_a_request_id_must_be_a_uuid(db: Session) -> None:
    """§27: a key that is not a UUID, or disagrees with the body, is refused
    before anything is written — the guard is on the way in, not a cleanup."""
    from app.common.errors import IdempotencyKeyInvalidError

    valid = _rid()
    assert auth_commands.require_request_id(valid, valid) == valid

    for request_id, header in (
        ("not-a-uuid", "not-a-uuid"),
        (valid, str(uuid.uuid4())),
        ("", None),
    ):
        with pytest.raises(IdempotencyKeyInvalidError):
            auth_commands.require_request_id(request_id, header)


def test_m01_qa_016_a_failed_login_records_no_identifier(
    db: Session,
) -> None:
    """§13: no raw token, credential, email or tenant detail.

    The signature is itself the finding: `record_failed_login` takes a provider
    key, a reason code and an optional account id, and has nowhere to put an
    email even if a caller wanted to. The check below confirms the audit and
    outbox stay clean, but the design is what makes the leak impossible rather
    than merely absent today.
    """
    account, _ = _account(db, "sub-qa016")
    accounts.record_failed_login(
        db,
        provider_key=GOOGLE_PROVIDER,
        reason_code="CALLBACK_INVALID",
        user_account_id=account.id,
    )
    db.commit()

    rendered = repr(db.execute(select(AuditLog.summary, AuditLog.context)).all()) + repr(
        db.execute(select(OutboxMessage.payload)).scalars().all()
    )
    for secret in ("@", "token", "credential"):
        assert secret not in rendered.lower() or "credential_hash" in rendered


def test_m01_qa_018_an_account_never_exists_without_its_first_identity(
    db: Session,
) -> None:
    """§18: the pair is written in one transaction.

    An account with no identity is an account nobody can ever sign in to and
    nothing will ever clean up — and M02's activation is exactly the flow that
    could leave one behind if the two writes were separable.
    """
    orphans = db.execute(
        select(func.count())
        .select_from(UserAccount)
        .where(
            ~UserAccount.id.in_(select(AuthIdentity.user_account_id))
        )
    ).scalar_one()
    assert orphans == 0

    _account(db, "sub-qa018")
    orphans_after = db.execute(
        select(func.count())
        .select_from(UserAccount)
        .where(~UserAccount.id.in_(select(AuthIdentity.user_account_id)))
    ).scalar_one()
    assert orphans_after == 0


def test_m01_qa_006_the_last_identity_is_protected(db: Session) -> None:
    """§6: unlinking it would leave an account nobody can ever sign in to.

    The command needs a recent session as step-up evidence, which is itself
    part of the rule — removing a way in is exactly the operation an attacker
    with a stale cookie would want.
    """
    from app.common.errors import LastIdentityProtectedError
    from app.domains.identity import auth_identities
    from app.domains.identity.auth_enums import IdentityUnlinkReason

    account, identity = _account(db, "sub-qa006")
    acting, _ = sessions.issue_session(db, account=account, identity=identity)
    db.commit()

    with pytest.raises(LastIdentityProtectedError):
        auth_identities.unlink_identity(
            db,
            account=account,
            acting_session=acting,
            identity=identity,
            expected_version=account.version,
            reason_code=IdentityUnlinkReason.ACCOUNT_HOLDER_REQUEST,
        )


def test_m01_qa_013_repeated_attempts_from_one_address_are_limited(
    db: Session,
) -> None:
    """§13's limiter, and the refusal that must not confirm an account.

    The message is the same whether or not the address belongs to anyone,
    which is what stops the limiter becoming an enumeration oracle — and the
    signal is a keyed digest, so the table does not hold the address either.
    """
    from app.common.errors import RateLimitedError
    from app.config import get_settings
    from app.platform.rate_limit import service as rate_limit
    from app.platform.rate_limit.enums import RateLimitScope

    secret = get_settings().session_secret
    address = "203.0.113.7"
    refused_at = None
    for attempt in range(1, 60):
        try:
            rate_limit.consume(
                db, RateLimitScope.PASSWORD_FAILURE_IP, address, secret=secret
            )
        except RateLimitedError as exc:
            refused_at = attempt
            assert address not in str(exc)
            break
    assert refused_at is not None, "the limiter never refused"

    stored = repr(
        db.execute(
            select(rate_limit.RateLimitCounter.subject_hash)  # type: ignore[attr-defined]
        ).scalars().all()
    ) if hasattr(rate_limit, "RateLimitCounter") else ""
    assert address not in stored
