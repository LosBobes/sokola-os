"""M02 §1: the 84 numbered QA scenarios, under the gate #115 established.

Sixth module under the gate. One test per runnable scenario named for its id,
the rest declared in `BLOCKED` with a reason from a closed vocabulary, and a
gate that fails if any of the 84 is neither. Nothing is skipped.

M02 is the module where the contract and the repository describe **different
invitations**. The repo's is real and works end to end — send, list, revoke,
reissue, accept, with audit and outbox on each — but it is a one-stage
invitation: `send_invitation` mints a token immediately, stores the recipient
address in plaintext, and acceptance requires a caller who is *already*
authenticated. §2 describes a two-stage one: a `DRAFT` carrying no token, an
issue transaction that produces a keyed digest and an encrypted secret, a
delivery worker with fencing tokens, and acceptance attempts with browser
binding that create the account themselves.

That is why this file has a fifth blocking cause the earlier modules did not
need. `contract divergence` marks a scenario the repo *answers*, differently —
as opposed to `feature absent`, where there is nothing to answer with. Four
scenarios are that, and two of them are findings rather than mere differences:

* **QA-034** asks that an unknown token be indistinguishable from an expired,
  revoked or accepted one. This repo returns 404 for a token it has never
  seen and 409 for one it has, so a prober can tell "this token existed" from
  "it never did" (F-43).
* **QA-065** asks that no account be creatable without an invitation attempt.
  `/auth/password/register` does exactly that, deliberately, under M01 §4.9.

QA-057 was a fourth until this change. It asked that acceptance into a school
deactivated mid-flow be fail-closed, and `accept_invitation` did not read
`School.status` at all — so the write landed in a school that was off. It is
now implemented rather than declared, and the guard it tests is the point of
this increment (F-44).

One defect found here is fixed in this PR rather than recorded: the audit
summaries for `invitation.sent`, `invitation.revoked` and `invitation.reissued`
each wrote the **plaintext recipient email** into the audit trail, which §4.3
and QA-068/QA-084 both forbid. QA-068 below is what keeps it out. The rest of
the email-at-rest contract — ciphertext, keyed digest, a mask derived in
memory — is a schema change and stays a finding (F-42).
"""

from __future__ import annotations

import re
from pathlib import Path

from app.domains.identity.accounts import create_account_with_identity
from app.domains.identity.auth_enums import GOOGLE_ISSUER, GOOGLE_PROVIDER
from app.domains.identity.enums import RoleCode
from app.domains.identity.invite_tokens import hash_token
from app.domains.identity.models import Person
from app.domains.school import anchor
from app.domains.school.enums import SchoolStatus, SchoolStatusReason
from app.domains.school.models import School
from app.security.auth import DEV_PERSON_HEADER
from app.security.deps import CONTEXT_HEADER
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.factories import (
    Actor,
    add_membership,
    assign_role,
    bootstrap_actor,
    link_login_email,
    make_person,
)

_QA_DOC = (
    Path(__file__).resolve().parents[3]
    / "docs/spec/v5.7/04-MODULSKI-UGOVORI/02-M02-POZIVNICE-I-AKTIVACIJA"
    / "02-M02-QA-I-TRACEABILITY.md"
)


def _absent(what: str) -> str:
    return f"feature absent: {what}"


def _diverges(what: str) -> str:
    return f"contract divergence: {what}"


#: Five causes, and the reason test below refuses a sixth.
#:
#: `contract divergence` is the one M02 added. It means the repository answers
#: the scenario — just not the way §2 says — so the fix is a decision about
#: which behaviour is wanted, not a module to write. Filing those under
#: `feature absent` would hide two real findings inside a pile of unwritten
#: code.
BLOCKED: dict[str, str] = {}

_DRAFT = _absent(
    "there is no DRAFT stage. `send_invitation` mints a token and goes "
    "straight to PENDING, so there is no token-less draft to create, edit or "
    "issue"
)
for _n in (1, 2, 3, 20, 21, 22, 23):
    BLOCKED[f"M02-QA-{_n:03d}"] = _DRAFT

_APPROVAL = _absent(
    "there is no AWAITING_APPROVAL state and no guardian-requested invitation "
    "flow; a school actor issues every invitation directly"
)
for _n in (9, 10, 11, 12, 14, 79):
    BLOCKED[f"M02-QA-{_n:03d}"] = _APPROVAL

_EMAIL_AT_REST = _absent(
    "`Invitation.target_email` is a plaintext column. There is no ciphertext, "
    "no keyed fingerprint and no in-memory derived mask, so normalization, "
    "fingerprint equality and masking have nothing to assert against (F-42)"
)
for _n in (6, 7, 8, 62, 84):
    BLOCKED[f"M02-QA-{_n:03d}"] = _EMAIL_AT_REST

_DELIVERY = _absent(
    "nothing delivers an invitation. There is no delivery attempt table, no "
    "fencing token, no encrypted secret and no provider adapter — the raw "
    "token is returned to the API caller once and that is the whole channel"
)
for _n in (24, 25, 26, 27, 28, 83):
    BLOCKED[f"M02-QA-{_n:03d}"] = _DELIVERY
for _n in (25, 27, 28):
    BLOCKED[f"M02-QA-{_n:03d}"] = "no worker: " + _DELIVERY.split(": ", 1)[1]

_ATTEMPT = _absent(
    "there is no acceptance attempt: no attempt row, no browser binding, no "
    "15-minute window and no state parameter. `accept_invitation` takes a "
    "token from an already-authenticated caller in one shot"
)
for _n in (35, 36, 38, 51, 53):
    BLOCKED[f"M02-QA-{_n:03d}"] = _ATTEMPT

_ACCEPT_CREATES_ACCOUNT = _absent(
    "acceptance does not create accounts. `accept_invitation` requires an "
    "authenticated principal, so the account and its first identity already "
    "exist by the time it runs and INV-09's account-creation transaction has "
    "no implementation"
)
for _n in (44, 45, 46, 47):
    BLOCKED[f"M02-QA-{_n:03d}"] = _ACCEPT_CREATES_ACCOUNT

_OWNER_FLOW = _absent(
    "there are no INITIAL_OWNER or OWNER_ACCESS invitation types and no "
    "step-up authentication; `InvitationType` is STAFF/PARENT/STUDENT"
)
for _n in (17, 18, 19):
    BLOCKED[f"M02-QA-{_n:03d}"] = _OWNER_FLOW

_PAYER = _absent(
    "there is no PAYER_ACCESS invitation type. M07's `PayerChildLink` exists, "
    "but no invitation can name it and no M05 PAYER grant spec exists"
)
for _n in (75, 76, 77, 78):
    BLOCKED[f"M02-QA-{_n:03d}"] = _PAYER

_INV11 = _absent(
    "there is no INV-11 bulk revoke. `deactivate_school` transitions the "
    "school and bumps TEN-04 and touches no invitation (M04 F-40)"
)
for _n in (71, 72, 73, 74):
    BLOCKED[f"M02-QA-{_n:03d}"] = _INV11

BLOCKED.update(
    {
        "M02-QA-004": _absent(
            "no open-intent uniqueness: nothing stops two actors creating two "
            "PENDING invitations for the same person and role, and there is no "
            "`INVITATION_DUPLICATE_ACTIVE` code"
        ),
        "M02-QA-005": _absent(
            "`send_invitation` validates the *child* of a PARENT invite but "
            "never checks that the recipient is account-eligible, so a "
            "PARTICIPANT target is not refused"
        ),
        "M02-QA-015": _absent(
            "grant delegation is not modelled; `validate_granted_areas` checks "
            "areas against the actor's own, but there is no delegable-permission "
            "concept to be missing"
        ),
        "M02-QA-016": _diverges(
            "`OWNER` is inside `_STAFF_ROLE_CODES`, so an ordinary staff invite "
            "may grant it; §2 wants 403 and a separate owner flow"
        ),
        "M02-QA-033": _absent("no replacement rate limit and no owner override path"),
        "M02-QA-034": _diverges(
            "an unknown token raises NotFound (404) and a known-but-terminal one "
            "raises Conflict (409), so the two are distinguishable — the "
            "opposite of what this scenario requires (F-43)"
        ),
        "M02-QA-037": _absent("there is no pre-auth preview endpoint for a token"),
        "M02-QA-039": _absent(
            "M01's issuer registry is real, but no M02 attempt consumes a "
            "provider proof, so there is no attempt to leave unverified"
        ),
        "M02-QA-040": _absent(
            "acceptance compares the target address to the principal's verified "
            "login emails, not a fingerprint; with no fingerprint there is no "
            "mismatch of one to assert"
        ),
        "M02-QA-050": _absent(
            "`accept_invitation` resolves a Person and never reads the "
            "account's status, so a SUSPENDED or DISABLED account is not "
            "refused and `INVITATION_ACCOUNT_INACTIVE` does not exist"
        ),
        "M02-QA-052": _absent("no M01 proof is consumed by acceptance, so none can expire"),
        "M02-QA-058": _absent(
            "an invitation stores the role and areas it will grant but no "
            "policy version, so there is no snapshot to have gone stale"
        ),
        "M02-QA-063": _absent("there is no public token preview surface to read a context from"),
        "M02-QA-065": _diverges(
            "`/auth/password/register` creates a Person and an account with no "
            "invitation, deliberately, under M01 §4.9 — §2 asks the server to "
            "refuse exactly that"
        ),
        "M02-QA-067": _absent("no invitation email is composed or sent, so none can be inspected"),
        "M02-QA-070": _absent(
            "the final guard reads M04–M07 state through ordinary queries; "
            "there is no port that can report unavailable, so nothing can fail "
            "closed with 503"
        ),
        "M02-QA-080": _absent(
            "no invitation names an M07 link, so none can be revoked between "
            "issue and accept"
        ),
        "M02-QA-082": _absent("same missing M07 link reference as M02-QA-080"),
    }
)


# ===========================================================================
# The gate
# ===========================================================================


def _declared() -> set[str]:
    return set(re.findall(r"M02-QA-\d{3}", _QA_DOC.read_text()))


def _implemented() -> set[str]:
    source = Path(__file__).read_text()
    return {
        f"M02-QA-{n}"
        for n in re.findall(r"^def test_m02_qa_(\d{3})_", source, re.MULTILINE)
    }


def test_every_m02_scenario_is_implemented_or_declared() -> None:
    declared = _declared()
    assert len(declared) == 84, f"expected 84 scenarios, found {len(declared)}"
    implemented = _implemented()
    blocked = set(BLOCKED)
    assert not (implemented & blocked), sorted(implemented & blocked)
    missing = declared - implemented - blocked
    assert not missing, f"neither implemented nor declared blocked: {sorted(missing)}"
    stray = (implemented | blocked) - declared
    assert not stray, f"ids not in the contract: {sorted(stray)}"


def test_the_m02_blocked_reasons_name_one_of_five_causes() -> None:
    """A free-text reason rots into "TODO". `contract divergence` is the one
    that must not be absorbed into `feature absent`: it marks a scenario the
    repository answers differently, which is a decision to make rather than a
    module to write — and two of the four are findings."""
    for scenario, reason in BLOCKED.items():
        assert any(
            cause in reason
            for cause in (
                "feature absent",
                "contract divergence",
                "no command envelope",
                "no worker",
                "no migration harness",
            )
        ), f"{scenario} has an unrecognised blocking reason: {reason}"


# ===========================================================================
# Fixtures
# ===========================================================================


def _invite(
    client: TestClient,
    actor: Actor,
    *,
    email: str = "pozvani@example.invalid",
    type_: str = "STAFF",
    role_code: str | None = "TRAINER",
    child_id: str | None = None,
) -> tuple[str, str]:
    """Send an invitation the way the API does, and keep the one-shot token."""
    body: dict[str, object] = {"type": type_, "target_email": email}
    if role_code is not None:
        body["role_code"] = role_code
    if child_id is not None:
        body["target_child_person_id"] = child_id
    resp = client.post("/invitations", headers=actor.headers, json=body)
    assert resp.status_code == 201, resp.text
    return str(resp.json()["invitation"]["id"]), str(resp.json()["token"])


def _signed_in_recipient(
    db: Session, client: TestClient, email: str, *, given: str = "Pozvani"
) -> Person:
    """A person whose verified login email is `email`, as acceptance requires."""
    person = make_person(db, given=given, family="Primalac")
    link_login_email(db, person=person, email=email)
    return person


def _accept(client: TestClient, person: Person, token: str):
    return client.post(
        "/invitations/accept",
        headers={DEV_PERSON_HEADER: person.id},
        json={"token": token},
    )


# ===========================================================================
# Issue, replace and terminal transitions (§2, §5)
# ===========================================================================


def test_m02_qa_013_an_invite_cannot_name_another_schools_child(
    db: Session, client: TestClient
) -> None:
    """§4.1: safe not-found, with no child name and no confirmation that the
    child exists.

    The lookup is keyed on `(school_id, child_person_id)`, which is what makes
    "that child is in another school" and "no such child" the same answer.
    Telling them apart is how a guessed id confirms a child is enrolled
    somewhere.
    """
    a = bootstrap_actor(db, org_name="Skola A", given="Ana")
    b = bootstrap_actor(db, org_name="Skola B", given="Bora")
    their_child = make_person(db, given="Tudje", family="Dete")
    add_membership(db, person=their_child, school=b.school)

    theirs = client.post(
        "/invitations",
        headers=a.headers,
        json={
            "type": "PARENT",
            "target_email": "roditelj@example.invalid",
            "target_child_person_id": their_child.id,
        },
    )
    invented = client.post(
        "/invitations",
        headers=a.headers,
        json={
            "type": "PARENT",
            "target_email": "roditelj@example.invalid",
            "target_child_person_id": "per_nema_ovakvog",
        },
    )
    assert theirs.status_code == invented.status_code == 404
    assert theirs.json() == invented.json()
    assert "Tudje" not in theirs.text
    assert db.execute(text("SELECT count(*) FROM invitation")).scalar_one() == 0


def test_m02_qa_029_resending_supersedes_the_old_invitation_atomically(
    db: Session, client: TestClient
) -> None:
    """A new row with a new token, the old one terminal, in one transaction.

    A chain rather than a mutation in place: the superseded row keeps its own
    id and status, so "we invited them three times" stays three rows and the
    history of who was asked when survives.
    """
    actor = bootstrap_actor(db, org_name="Ponovno slanje", given="Ana")
    first_id, first_token = _invite(client, actor)

    resp = client.post(f"/invitations/{first_id}/reissue", headers=actor.headers)
    assert resp.status_code == 201, resp.text
    second = resp.json()["invitation"]
    second_token = resp.json()["token"]

    assert second["id"] != first_id
    assert second_token != first_token
    assert second["status"] == "PENDING"
    assert second["reissued_from_invitation_id"] == first_id
    assert (
        client.get(f"/invitations/{first_id}", headers=actor.headers).json()["status"]
        == "REISSUED"
    )
    assert db.execute(text("SELECT count(*) FROM invitation")).scalar_one() == 2


def test_m02_qa_030_the_superseded_token_stops_working_at_the_commit(
    db: Session, client: TestClient
) -> None:
    """No race window: the old token is refused from the moment the
    replacement commits, because the refusal reads the row's status rather
    than a cached view of it."""
    actor = bootstrap_actor(db, org_name="Stari token", given="Ana")
    first_id, first_token = _invite(client, actor, email="stari@example.invalid")
    recipient = _signed_in_recipient(db, client, "stari@example.invalid")

    reissued = client.post(f"/invitations/{first_id}/reissue", headers=actor.headers)
    assert reissued.status_code == 201

    refused = _accept(client, recipient, first_token)
    assert refused.status_code == 409
    assert (
        db.execute(
            text("SELECT count(*) FROM role_assignment WHERE person_id = :p"),
            {"p": recipient.id},
        ).scalar_one()
        == 0
    )


def test_m02_qa_031_a_replacement_references_the_row_it_replaced(
    db: Session, client: TestClient
) -> None:
    """An expired invitation may be replaced, and its terminal status does not
    change when it is: `EXPIRED` is a fact about what happened, not a slot to
    be reused."""
    actor = bootstrap_actor(db, org_name="Istekla", given="Ana")
    first_id, _ = _invite(client, actor)

    db.execute(
        text(
            "UPDATE invitation SET status = 'EXPIRED', expires_at = now() - interval '1 day' "
            "WHERE id = :id"
        ),
        {"id": first_id},
    )
    db.commit()

    resp = client.post(f"/invitations/{first_id}/reissue", headers=actor.headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["invitation"]["reissued_from_invitation_id"] == first_id

    old = client.get(f"/invitations/{first_id}", headers=actor.headers).json()
    assert old["status"] == "REISSUED"


def test_m02_qa_032_an_accepted_invitation_cannot_be_resent(
    db: Session, client: TestClient
) -> None:
    """§5: ACCEPTED is terminal, and the access it produced is not touched by
    the refusal. Resending would mint a second token for an offer that has
    already been taken up."""
    actor = bootstrap_actor(db, org_name="Prihvacena", given="Ana")
    invitation_id, token = _invite(client, actor, email="gotov@example.invalid")
    recipient = _signed_in_recipient(db, client, "gotov@example.invalid")
    assert _accept(client, recipient, token).status_code == 200

    before = db.execute(
        text("SELECT count(*) FROM role_assignment WHERE person_id = :p"),
        {"p": recipient.id},
    ).scalar_one()
    resp = client.post(f"/invitations/{invitation_id}/reissue", headers=actor.headers)
    assert resp.status_code == 409
    after = db.execute(
        text("SELECT count(*) FROM role_assignment WHERE person_id = :p"),
        {"p": recipient.id},
    ).scalar_one()
    assert after == before == 1


# ===========================================================================
# Acceptance: identity, reuse and the guards around it (§3, §11)
# ===========================================================================


def test_m02_qa_041_one_verified_email_on_two_subjects_links_nothing(
    db: Session, client: TestClient
) -> None:
    """§4.5 and M01 §4.5: a matching address links no accounts.

    Two OIDC principals assert the same verified address under different
    `(issuer, subject)` pairs, and they stay two accounts. Refusing on an
    email is safe; admitting on one is not — which is why M02 looks the
    address up to *refuse* a mismatch and never to find an account.
    """
    shared = "isti@example.invalid"
    first = make_person(db, given="Prvi", family="Nosilac")
    second = make_person(db, given="Drugi", family="Nosilac")
    first_account, _ = create_account_with_identity(
        db,
        person_id=first.id,
        provider_key=GOOGLE_PROVIDER,
        issuer=GOOGLE_ISSUER,
        subject="sub-one",
        login_email=shared,
        email_verified=True,
    )
    second_account, _ = create_account_with_identity(
        db,
        person_id=second.id,
        provider_key=GOOGLE_PROVIDER,
        issuer=GOOGLE_ISSUER,
        subject="sub-two",
        login_email=shared,
        email_verified=True,
    )
    db.commit()

    assert first_account.id != second_account.id
    assert first_account.person_id != second_account.person_id
    identities = db.execute(
        text("SELECT count(*) FROM auth_identity WHERE lower(login_email) = :e"),
        {"e": shared},
    ).scalar_one()
    assert identities == 2


def test_m02_qa_042_acceptance_reuses_the_principals_existing_account(
    db: Session, client: TestClient
) -> None:
    """The invited person already has an account; accepting adds access to it
    rather than minting a second one."""
    actor = bootstrap_actor(db, org_name="Postojeci nalog", given="Ana")
    email = "postojeci@example.invalid"
    _, token = _invite(client, actor, email=email)
    recipient = _signed_in_recipient(db, client, email)
    accounts_before = db.execute(text("SELECT count(*) FROM user_account")).scalar_one()

    resp = _accept(client, recipient, token)
    assert resp.status_code == 200, resp.text
    assert resp.json()["context"]["school_id"] == actor.school.id

    assert db.execute(text("SELECT count(*) FROM user_account")).scalar_one() == accounts_before
    assert (
        db.execute(
            text("SELECT count(*) FROM role_assignment WHERE person_id = :p"),
            {"p": recipient.id},
        ).scalar_one()
        == 1
    )


def test_m02_qa_043_an_invitation_meant_for_someone_else_is_refused(
    db: Session, client: TestClient
) -> None:
    """§23: the accepting principal's verified addresses must include the one
    the invitation was sent to.

    No merge, no new access, and the invitation stays open for the person it
    was actually for — a wrong-account attempt must not consume it.
    """
    actor = bootstrap_actor(db, org_name="Pogresan nalog", given="Ana")
    invitation_id, token = _invite(client, actor, email="pravi@example.invalid")
    intruder = _signed_in_recipient(db, client, "drugi@example.invalid", given="Uljez")

    resp = _accept(client, intruder, token)
    assert resp.status_code == 403
    assert (
        db.execute(
            text("SELECT count(*) FROM role_assignment WHERE person_id = :p"),
            {"p": intruder.id},
        ).scalar_one()
        == 0
    )
    assert (
        client.get(f"/invitations/{invitation_id}", headers=actor.headers).json()["status"]
        == "PENDING"
    )


def test_m02_qa_048_only_one_of_two_acceptances_of_one_invitation_commits(
    db: Session, client: TestClient
) -> None:
    """Exactly one commit, and the second gets a safe already-used answer
    rather than a second grant.

    Driven sequentially, which is the honest description: what is proved is
    that ACCEPTED is terminal on read, and that is the property that makes the
    concurrent case safe.
    """
    actor = bootstrap_actor(db, org_name="Dva pokusaja", given="Ana")
    email = "jednom@example.invalid"
    _, token = _invite(client, actor, email=email)
    recipient = _signed_in_recipient(db, client, email)

    assert _accept(client, recipient, token).status_code == 200
    second = _accept(client, recipient, token)
    assert second.status_code == 409

    assert (
        db.execute(
            text("SELECT count(*) FROM role_assignment WHERE person_id = :p"),
            {"p": recipient.id},
        ).scalar_one()
        == 1
    )
    assert (
        db.execute(
            text("SELECT count(*) FROM school_membership WHERE person_id = :p"),
            {"p": recipient.id},
        ).scalar_one()
        == 1
    )


def test_m02_qa_049_access_that_already_exists_is_reused_not_duplicated(
    db: Session, client: TestClient
) -> None:
    """The same access arrived by another route before acceptance committed.

    The invitation still completes, and produces no second grant: `_grant_role`
    reuses a matching assignment rather than inserting beside it. A duplicate
    here would be invisible on screen and would survive the revocation of
    either copy.
    """
    actor = bootstrap_actor(db, org_name="Vec ima pristup", given="Ana")
    email = "duplikat@example.invalid"
    _, token = _invite(client, actor, email=email, role_code="TRAINER")
    recipient = _signed_in_recipient(db, client, email)

    # The same role, granted by the ordinary path first.
    add_membership(db, person=recipient, school=actor.school)
    assign_role(db, person=recipient, school=actor.school, role=RoleCode.TRAINER)
    before = db.execute(
        text("SELECT count(*) FROM role_assignment WHERE person_id = :p"),
        {"p": recipient.id},
    ).scalar_one()
    assert before == 1

    assert _accept(client, recipient, token).status_code == 200
    after = db.execute(
        text("SELECT count(*) FROM role_assignment WHERE person_id = :p"),
        {"p": recipient.id},
    ).scalar_one()
    assert after == 1


def test_m02_qa_054_the_instant_an_invitation_expires_it_stops_working(
    db: Session, client: TestClient
) -> None:
    """Before the deadline it may proceed; at it and after, it may not.

    The boundary is asserted on the row rather than by waiting, and the guard
    is `expires_at <= now` — so the moment of expiry is already outside the
    window, the same way M04's entitlement window closes.
    """
    actor = bootstrap_actor(db, org_name="Rok", given="Ana")
    email = "rok@example.invalid"
    invitation_id, token = _invite(client, actor, email=email)
    recipient = _signed_in_recipient(db, client, email)

    db.execute(
        text("UPDATE invitation SET expires_at = now() WHERE id = :id"),
        {"id": invitation_id},
    )
    db.commit()

    refused = _accept(client, recipient, token)
    assert refused.status_code == 409
    assert (
        db.execute(
            text("SELECT count(*) FROM role_assignment WHERE person_id = :p"),
            {"p": recipient.id},
        ).scalar_one()
        == 0
    )


def test_m02_qa_055_expiry_is_decided_on_read_not_by_a_job(
    db: Session, client: TestClient
) -> None:
    """The row still says PENDING — no scan has run — and the token is refused
    anyway, then the status is materialized as a side effect of the read.

    A guard that waited for a sweep would give every expired invitation a
    window of extra life whose length was set by how backed up the job was.
    """
    actor = bootstrap_actor(db, org_name="Bez posla", given="Ana")
    email = "kasni@example.invalid"
    invitation_id, token = _invite(client, actor, email=email)
    recipient = _signed_in_recipient(db, client, email)

    db.execute(
        text("UPDATE invitation SET expires_at = now() - interval '1 hour' WHERE id = :id"),
        {"id": invitation_id},
    )
    db.commit()
    stored = db.execute(
        text("SELECT status FROM invitation WHERE id = :id"), {"id": invitation_id}
    ).scalar_one()
    assert stored == "PENDING", "no job has run; the row is still nominally open"

    assert _accept(client, recipient, token).status_code == 409
    db.expire_all()
    assert (
        db.execute(
            text("SELECT status FROM invitation WHERE id = :id"), {"id": invitation_id}
        ).scalar_one()
        == "EXPIRED"
    )


def test_m02_qa_056_a_revoke_that_commits_first_wins(
    db: Session, client: TestClient
) -> None:
    """Revoke commits, then acceptance is attempted: refused, no access.

    §11.4's ordering, in the direction that must fail closed. The other
    direction is M02-QA-069.
    """
    actor = bootstrap_actor(db, org_name="Opoziv prvi", given="Ana")
    email = "opozvan@example.invalid"
    invitation_id, token = _invite(client, actor, email=email)
    recipient = _signed_in_recipient(db, client, email)

    revoked = client.post(
        f"/invitations/{invitation_id}/revoke", headers=actor.headers, json={}
    )
    assert revoked.status_code == 200, revoked.text

    assert _accept(client, recipient, token).status_code == 409
    assert (
        db.execute(
            text("SELECT count(*) FROM role_assignment WHERE person_id = :p"),
            {"p": recipient.id},
        ).scalar_one()
        == 0
    )


def test_m02_qa_069_an_acceptance_that_commits_first_is_not_undone_by_revoke(
    db: Session, client: TestClient
) -> None:
    """§11.4's other direction: exactly one terminal transition either way.

    Once acceptance has committed, revoking the invitation is refused — and,
    the part that matters, the access it created is untouched. Withdrawing an
    offer someone already took up is a job for revoking the *role*, not for
    editing the invitation that produced it.
    """
    actor = bootstrap_actor(db, org_name="Prihvat prvi", given="Ana")
    email = "prihvacen@example.invalid"
    invitation_id, token = _invite(client, actor, email=email)
    recipient = _signed_in_recipient(db, client, email)

    assert _accept(client, recipient, token).status_code == 200
    refused = client.post(
        f"/invitations/{invitation_id}/revoke", headers=actor.headers, json={}
    )
    assert refused.status_code == 409

    detail = client.get(f"/invitations/{invitation_id}", headers=actor.headers).json()
    assert detail["status"] == "ACCEPTED"
    assert (
        db.execute(
            text(
                "SELECT count(*) FROM role_assignment WHERE person_id = :p "
                "AND status = 'ACTIVE'"
            ),
            {"p": recipient.id},
        ).scalar_one()
        == 1
    )


# ===========================================================================
# Scope of what acceptance grants, and tenant isolation (§4, §19.4)
# ===========================================================================


def test_m02_qa_059_a_guardian_invite_reaches_exactly_the_named_child(
    db: Session, client: TestClient
) -> None:
    """§19.4/19.5: the guardian gets the one child the invitation named.

    The other child in the same school and the child in another school both
    answer the same way — absent. Two children are used rather than one
    because a link that granted "the school's children" would pass a
    single-child test perfectly.
    """
    a = bootstrap_actor(db, org_name="Skola A", given="Ana")
    b = bootstrap_actor(db, org_name="Skola B", given="Bora")
    named = make_person(db, given="Imenovano", family="Dete")
    sibling = make_person(db, given="Drugo", family="Dete")
    elsewhere = make_person(db, given="Tudje", family="Dete")
    for child, school in ((named, a.school), (sibling, a.school), (elsewhere, b.school)):
        add_membership(db, person=child, school=school)

    email = "staratelj@example.invalid"
    _, token = _invite(
        client, a, email=email, type_="PARENT", role_code=None, child_id=named.id
    )
    guardian = _signed_in_recipient(db, client, email, given="Staratelj")
    accepted = _accept(client, guardian, token)
    assert accepted.status_code == 200, accepted.text

    guardian_headers = {
        DEV_PERSON_HEADER: guardian.id,
        CONTEXT_HEADER: accepted.json()["context"]["role_assignment_id"],
    }
    children = client.get("/parent/children", headers=guardian_headers)
    assert children.status_code == 200
    assert [row["person_id"] for row in children.json()] == [named.id]


def test_m02_qa_060_revoking_the_guardian_link_closes_the_child_at_once(
    db: Session, client: TestClient
) -> None:
    """The next request is refused with no cache window, and the invitation
    history survives — what was granted and then withdrawn is two facts, and
    losing either makes the trail useless."""
    actor = bootstrap_actor(db, org_name="Opoziv veze", given="Ana")
    child = make_person(db, given="Dete", family="Jedno")
    add_membership(db, person=child, school=actor.school)
    email = "roditelj2@example.invalid"
    invitation_id, token = _invite(
        client, actor, email=email, type_="PARENT", role_code=None, child_id=child.id
    )
    guardian = _signed_in_recipient(db, client, email, given="Roditelj")
    accepted = _accept(client, guardian, token)
    assert accepted.status_code == 200
    guardian_headers = {
        DEV_PERSON_HEADER: guardian.id,
        CONTEXT_HEADER: accepted.json()["context"]["role_assignment_id"],
    }
    assert len(client.get("/parent/children", headers=guardian_headers).json()) == 1

    db.execute(
        text(
            "UPDATE guardian_school_access SET status = 'REVOKED' "
            "WHERE guardian_person_id = :g AND child_person_id = :c"
        ),
        {"g": guardian.id, "c": child.id},
    )
    db.commit()

    assert client.get("/parent/children", headers=guardian_headers).json() == []
    assert (
        client.get(f"/invitations/{invitation_id}", headers=actor.headers).json()["status"]
        == "ACCEPTED"
    )


def test_m02_qa_061_another_schools_invitation_id_is_a_safe_not_found(
    db: Session, client: TestClient
) -> None:
    """§4.1, and the list is checked alongside the lookup: a safe 404 on the
    detail route means little if the list route hands the same row over."""
    a = bootstrap_actor(db, org_name="Skola A", given="Ana")
    b = bootstrap_actor(db, org_name="Skola B", given="Bora")
    theirs, _ = _invite(client, b, email="njihov@example.invalid")

    real = client.get(f"/invitations/{theirs}", headers=a.headers)
    invented = client.get("/invitations/inv_nema_ovakve", headers=a.headers)
    assert real.status_code == invented.status_code == 404
    assert real.json() == invented.json()

    listed = client.get("/invitations", headers=a.headers).json()
    assert listed["total"] == 0
    assert listed["items"] == []
    assert "njihov@example.invalid" not in client.get("/invitations", headers=a.headers).text


def test_m02_qa_064_accepting_adds_one_school_and_disturbs_no_other(
    db: Session, client: TestClient
) -> None:
    """The invitee already works at another school. Acceptance grants access
    to the target school only, and the existing access is untouched — an
    invitation is additive, never a move."""
    first = bootstrap_actor(db, org_name="Postojeca skola", given="Ana")
    second = bootstrap_actor(db, org_name="Nova skola", given="Bora")
    email = "dvoskolac@example.invalid"
    link_login_email(db, person=first.person, email=email)

    _, token = _invite(client, second, email=email, role_code="TRAINER")
    accepted = _accept(client, first.person, token)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["context"]["school_id"] == second.school.id

    schools = db.execute(
        text(
            "SELECT school_id FROM role_assignment WHERE person_id = :p "
            "AND status = 'ACTIVE' ORDER BY school_id"
        ),
        {"p": first.person.id},
    ).scalars().all()
    assert sorted(schools) == sorted([first.school.id, second.school.id])
    # The original context still resolves, unchanged.
    assert client.get("/people", headers=first.headers).status_code == 200


def test_m02_qa_066_a_school_code_alone_grants_nothing(
    db: Session, client: TestClient
) -> None:
    """§3.7.4 again, from M02's side: a locator is navigation, not an offer.

    Someone who types a real school code with no invitation gets the tenant's
    public identity and no membership, role, invitation or account.
    """
    founder = make_person(db, given="Osnivač", family="Koda")
    created = client.post(
        "/schools",
        headers={DEV_PERSON_HEADER: founder.id},
        json={"name": "Skola sa kodom", "type": "SPORTS_CLUB"},
    )
    assert created.status_code == 201
    school_id = created.json()["id"]
    slug = db.execute(
        text("SELECT slug FROM school WHERE id = :id"), {"id": school_id}
    ).scalar_one()

    stranger = make_person(db, given="Znatiželjni", family="Prolaznik")
    before = {
        table: db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
        for table in ("invitation", "role_assignment", "school_membership", "user_account")
    }

    resp = client.get(f"/tenants/{slug}")
    assert resp.status_code == 200
    assert set(resp.json()) == {"school_id", "name", "slug"}

    after = {
        table: db.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
        for table in ("invitation", "role_assignment", "school_membership", "user_account")
    }
    assert after == before
    assert (
        db.execute(
            text("SELECT count(*) FROM role_assignment WHERE person_id = :p"),
            {"p": stranger.id},
        ).scalar_one()
        == 0
    )


def test_m02_qa_068_no_recipient_address_reaches_the_audit_or_outbox_trail(
    db: Session, client: TestClient
) -> None:
    """§4.3, and the reason this test exists.

    All three invitation audit summaries used to interpolate the recipient
    address — `"Pozivnica poslata na {email}"`, `"Pozivnica za {email} je
    opozvana"`, `"Pozivnica za {email} je ponovo poslata"`. The audit log
    outlives the invitation and is read by people with no reason to see who
    was written to, so that is a copy of personal data into the wrong store.
    Fixed in this change; this is what keeps it fixed.

    The whole trail is read back rather than one command's row, because that
    is how such a leak arrives: one summary somewhere gains a convenient
    field, and a test that only knew about its own command would not notice.
    Raw tokens and digests are checked for on the same pass.
    """
    actor = bootstrap_actor(db, org_name="Trag", given="Ana")
    email = "poverljiva.adresa@example.invalid"
    first_id, first_token = _invite(client, actor, email=email)

    reissued = client.post(f"/invitations/{first_id}/reissue", headers=actor.headers)
    assert reissued.status_code == 201
    second_id = reissued.json()["invitation"]["id"]
    second_token = reissued.json()["token"]
    assert (
        client.post(
            f"/invitations/{second_id}/revoke", headers=actor.headers, json={}
        ).status_code
        == 200
    )

    trail = " ".join(
        str(row)
        for row in db.execute(
            text("SELECT action, summary, context FROM audit_log")
        ).all()
    )
    payloads = " ".join(
        str(row[0]) for row in db.execute(text("SELECT payload FROM outbox_message")).all()
    )
    haystack = f"{trail} {payloads}"

    assert "invitation.sent" in trail, "the commands really did run"
    assert "invitation.reissued" in trail
    assert "invitation.revoked" in trail
    for forbidden in (email, "poverljiva.adresa", first_token, second_token):
        assert forbidden not in haystack, f"{forbidden!r} reached the audit/outbox trail"
    for digest in (hash_token(first_token), hash_token(second_token)):
        assert digest not in haystack, "a token digest reached the trail"


def test_m02_qa_081_a_profile_from_another_school_cannot_be_targeted(
    db: Session, client: TestClient
) -> None:
    """Master §2.6 / §4.1–4.2: safe not-found, no invitation, no signal.

    The same refusal for "that person belongs to school B" and "no such
    person", because the difference between them is exactly what a guessed id
    is fishing for.
    """
    a = bootstrap_actor(db, org_name="Skola A", given="Ana")
    b = bootstrap_actor(db, org_name="Skola B", given="Bora")
    theirs = make_person(db, given="Tudji", family="Clan")
    add_membership(db, person=theirs, school=b.school)

    cross_tenant = client.post(
        "/invitations",
        headers=a.headers,
        json={
            "type": "PARENT",
            "target_email": "meta@example.invalid",
            "target_child_person_id": theirs.id,
        },
    )
    nonexistent = client.post(
        "/invitations",
        headers=a.headers,
        json={
            "type": "PARENT",
            "target_email": "meta@example.invalid",
            "target_child_person_id": "per_nikad_postojao",
        },
    )
    assert cross_tenant.status_code == nonexistent.status_code == 404
    assert cross_tenant.json() == nonexistent.json()
    assert "Tudji" not in cross_tenant.text
    assert db.execute(text("SELECT count(*) FROM invitation")).scalar_one() == 0


def test_m02_qa_057_a_school_deactivated_mid_flow_refuses_the_acceptance(
    db: Session, client: TestClient
) -> None:
    """§11.4: the final guard is fail-closed on the school, and the account's
    other schools are untouched.

    This is the scenario F-44 was recorded against. `accept_invitation`
    checked the invitation's status, its expiry and the recipient's address,
    and never read `School.status` — so a school deactivated between issue and
    accept still took the write. No *access* resulted, because the tenant
    guard refuses a deactivated school on the next request (M04-QA-057 proves
    that), but a membership and a role assignment were created in a school
    that was off. Rows nobody expects are their own problem: they are what a
    later reactivation, export or report reads back as real.

    The refusal reuses `ConflictError`, the same shape as revoked and expired,
    rather than introducing a code of its own. F-43 is already a finding about
    acceptance refusals being distinguishable from one another; this change
    does not add to it.

    Both halves are asserted. The second is the one a careless fix breaks: the
    person's *other* school must still work, because deactivating one school
    is not an account-level event.
    """
    target = bootstrap_actor(db, org_name="Ugašena škola", given="Ana")
    other = bootstrap_actor(db, org_name="Druga škola", given="Bora")
    email = "kasni.prihvat@example.invalid"
    link_login_email(db, person=other.person, email=email)

    invitation_id, token = _invite(client, target, email=email, role_code="TRAINER")

    # The school goes away after the invitation was issued and before it is
    # taken up — the race §11.4 names.
    anchor.transition_status(
        db,
        school=db.get(School, target.school.id),
        to_status=SchoolStatus.DEACTIVATED,
        reason_code=SchoolStatusReason.OPERATIONAL_PAUSE,
        actor_ref="test",
        correlation_id="qa-057",
    )
    db.commit()

    before_memberships = db.execute(
        text("SELECT count(*) FROM school_membership WHERE school_id = :s"),
        {"s": target.school.id},
    ).scalar_one()

    refused = _accept(client, other.person, token)
    assert refused.status_code == 409, refused.text

    # Nothing was written into the school that is off.
    assert (
        db.execute(
            text("SELECT count(*) FROM school_membership WHERE school_id = :s"),
            {"s": target.school.id},
        ).scalar_one()
        == before_memberships
    )
    assert (
        db.execute(
            text(
                "SELECT count(*) FROM role_assignment "
                "WHERE school_id = :s AND person_id = :p"
            ),
            {"s": target.school.id, "p": other.person.id},
        ).scalar_one()
        == 0
    )
    # The invitation is not consumed: it was never accepted.
    assert (
        db.execute(
            text("SELECT status FROM invitation WHERE id = :id"), {"id": invitation_id}
        ).scalar_one()
        == "PENDING"
    )

    # And the account's other school still works.
    assert client.get("/people", headers=other.headers).status_code == 200
