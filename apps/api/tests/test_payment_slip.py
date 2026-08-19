"""The payment slip is an aid for filling in a payment order, nothing more.

It never moves money, never marks anything paid, and only the school (or the
paying family) may see it.
"""

from __future__ import annotations

import datetime as dt

from app.domains.identity.enums import RoleCode
from app.domains.organization.models import Organization
from app.domains.payments import ips_qr
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import Actor, add_actor, bootstrap_actor, make_child_with_guardian


def _set_payee(db: Session, organization_id: str) -> None:
    org = db.get(Organization, organization_id)
    assert org is not None
    org.bank_account_number = "160-0000000123456-78"
    org.address = "Ulica 1"
    org.city = "Beograd"
    db.commit()


def _charge_for(client: TestClient, actor: Actor, person_id: str) -> dict:
    group_id = client.post("/groups", headers=actor.headers, json={"name": "G"}).json()["id"]
    client.post(
        f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": person_id}
    )
    body = {
        "group_id": group_id,
        "amount_minor": 300000,
        "description": "Članarina",
        "period_label": "2026-09",
    }
    preview = client.post("/billing/runs/preview", headers=actor.headers, json=body).json()
    client.post(
        "/billing/runs",
        headers=actor.headers,
        json={**body, "preview_hash": preview["preview_hash"]},
    )
    charges = client.get("/charges", headers=actor.headers).json()["items"]
    return next(c for c in charges if c["person_id"] == person_id)


# --- payload construction --------------------------------------------------


def test_mod97_control_digits_follow_the_nbs_rule() -> None:
    base = "123456789012"
    reference = ips_qr.mod97_reference(base)
    control = int(reference[:2])
    assert reference[2:] == base
    assert control == 98 - (int(base + "00") % 97)


def test_amount_is_formatted_from_minor_units_without_float_rounding() -> None:
    assert ips_qr.format_amount(300000, "RSD") == "RSD3000,00"
    assert ips_qr.format_amount(305, "RSD") == "RSD3,05"
    assert ips_qr.format_amount(1, "RSD") == "RSD0,01"


def test_field_separators_in_user_text_cannot_forge_a_payload() -> None:
    payload = ips_qr.build_ips_qr_payload(
        account="160-0000000123456-78",
        payee_name="Klub|I:RSD999999,00",
        payee_address=None,
        payee_city=None,
        amount_minor=300000,
        currency="RSD",
        purpose="Članarina",
        reference="123456789012",
    )
    # The injected amount became part of the payee's name, not a second I field.
    assert payload.count("|I:") == 1
    assert "RSD3000,00" in payload
    assert "RSD999999,00" not in payload.split("|I:")[1].split("|")[0]


def test_a_short_account_number_is_refused() -> None:
    try:
        ips_qr.normalize_account("160-123-45")
    except ips_qr.PaymentSlipError:
        return
    raise AssertionError("an 18-digit account should be required")


# --- the endpoint ----------------------------------------------------------


def test_slip_carries_the_outstanding_amount_and_a_stable_reference(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    _set_payee(db, actor.organization.id)
    child = client.post(
        "/people", headers=actor.headers, json={"given_name": "Mika", "family_name": "M"}
    ).json()["id"]
    charge = _charge_for(client, actor, child)

    # The billing run derived a due date from the "2026-09" period label.
    assert charge["due_date"] == "2026-09-30"

    slip = client.get(f"/charges/{charge['id']}/payment-slip", headers=actor.headers)
    assert slip.status_code == 200, slip.text
    body = slip.json()
    assert body["amount_minor"] == 300000
    assert body["account_number"] == "160000000012345678"
    assert body["reference_number"].startswith("97")
    assert "K:PR|V:01|C:1|" in body["ips_qr_payload"]
    assert "I:RSD3000,00" in body["ips_qr_payload"]

    # Re-issuing the slip prints the same reference the payer already used.
    again = client.get(f"/charges/{charge['id']}/payment-slip", headers=actor.headers).json()
    assert again["reference_number"] == body["reference_number"]

    # Part-paying it makes the next slip ask for the remainder, not the full sum.
    client.post(
        f"/charges/{charge['id']}/payments",
        headers=actor.headers,
        json={"amount_minor": 100000, "method": "CASH"},
    )
    remainder = client.get(
        f"/charges/{charge['id']}/payment-slip", headers=actor.headers
    ).json()
    assert remainder["amount_minor"] == 200000
    assert "I:RSD2000,00" in remainder["ips_qr_payload"]


def test_generating_a_slip_never_settles_the_charge(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    _set_payee(db, actor.organization.id)
    child = client.post(
        "/people", headers=actor.headers, json={"given_name": "Mika", "family_name": "M"}
    ).json()["id"]
    charge = _charge_for(client, actor, child)

    client.get(f"/charges/{charge['id']}/payment-slip", headers=actor.headers)

    after = next(
        c for c in client.get("/charges", headers=actor.headers).json()["items"]
        if c["id"] == charge["id"]
    )
    assert after["status"] == "OPEN"
    assert after["amount_paid_minor"] == 0


def test_a_school_without_an_account_number_is_told_so(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    child = client.post(
        "/people", headers=actor.headers, json={"given_name": "Mika", "family_name": "M"}
    ).json()["id"]
    charge = _charge_for(client, actor, child)

    refused = client.get(f"/charges/{charge['id']}/payment-slip", headers=actor.headers)
    assert refused.status_code == 409
    assert refused.json()["error"]["details"]["code"] == "PAYEE_ACCOUNT_NOT_SET"


def test_a_settled_charge_has_no_slip(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    _set_payee(db, actor.organization.id)
    child = client.post(
        "/people", headers=actor.headers, json={"given_name": "Mika", "family_name": "M"}
    ).json()["id"]
    charge = _charge_for(client, actor, child)
    client.post(
        f"/charges/{charge['id']}/payments",
        headers=actor.headers,
        json={"amount_minor": 300000, "method": "CASH"},
    )

    assert (
        client.get(
            f"/charges/{charge['id']}/payment-slip", headers=actor.headers
        ).status_code
        == 409
    )


def test_a_parent_sees_only_their_own_childs_slip(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    _set_payee(db, actor.organization.id)
    parent = add_actor(
        db, organization=actor.organization, role=RoleCode.PARENT, given="Roditelj"
    )
    child = make_child_with_guardian(
        db, organization=actor.organization, guardian=parent.person, given="Moje"
    )
    stranger = client.post(
        "/people", headers=actor.headers, json={"given_name": "Tuđe", "family_name": "D"}
    ).json()["id"]

    own_charge = _charge_for(client, actor, child.id)
    other_charge = _charge_for(client, actor, stranger)

    mine = client.get(f"/charges/{own_charge['id']}/payment-slip", headers=parent.headers)
    assert mine.status_code == 200, mine.text
    assert mine.json()["payer_name"] == "Moje D"

    # Another family's charge is indistinguishable from one that does not exist.
    theirs = client.get(
        f"/charges/{other_charge['id']}/payment-slip", headers=parent.headers
    )
    assert theirs.status_code == 404


def test_a_reference_from_a_bank_statement_resolves_back_to_its_charge(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    _set_payee(db, actor.organization.id)
    child = client.post(
        "/people", headers=actor.headers, json={"given_name": "Mika", "family_name": "M"}
    ).json()["id"]
    charge = _charge_for(client, actor, child)
    printed = client.get(
        f"/charges/{charge['id']}/payment-slip", headers=actor.headers
    ).json()["reference_number"]

    # However the operator copies it: with the model prefix, without it, or with
    # the punctuation a statement tends to carry.
    for typed in (printed, printed[2:], f"97-{printed[2:]}", charge["payment_reference"]):
        found = client.get(
            "/charges/lookup", headers=actor.headers, params={"reference": typed}
        )
        assert found.status_code == 200, f"{typed}: {found.text}"
        assert found.json()["id"] == charge["id"]

    missing = client.get(
        "/charges/lookup", headers=actor.headers, params={"reference": "9700000000000001"}
    )
    assert missing.status_code == 404


def test_an_unparseable_period_label_leaves_the_charge_without_a_due_date(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    group_id = client.post("/groups", headers=actor.headers, json={"name": "G"}).json()["id"]
    person_id = client.post(
        "/people", headers=actor.headers, json={"given_name": "Mika", "family_name": "M"}
    ).json()["id"]
    client.post(
        f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": person_id}
    )
    body = {
        "group_id": group_id,
        "amount_minor": 300000,
        "description": "Članarina",
        "period_label": "Jesenja sezona",
    }
    preview = client.post("/billing/runs/preview", headers=actor.headers, json=body).json()
    client.post(
        "/billing/runs",
        headers=actor.headers,
        json={**body, "preview_hash": preview["preview_hash"]},
    )

    charge = client.get("/charges", headers=actor.headers).json()["items"][0]
    assert charge["due_date"] is None


def test_an_explicit_due_date_overrides_the_period_label(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    group_id = client.post("/groups", headers=actor.headers, json={"name": "G"}).json()["id"]
    person_id = client.post(
        "/people", headers=actor.headers, json={"given_name": "Mika", "family_name": "M"}
    ).json()["id"]
    client.post(
        f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": person_id}
    )
    due = dt.date(2026, 9, 15).isoformat()
    body = {
        "group_id": group_id,
        "amount_minor": 300000,
        "description": "Članarina",
        "period_label": "2026-09",
        "due_date": due,
    }
    preview = client.post("/billing/runs/preview", headers=actor.headers, json=body).json()
    client.post(
        "/billing/runs",
        headers=actor.headers,
        json={**body, "preview_hash": preview["preview_hash"]},
    )

    assert client.get("/charges", headers=actor.headers).json()["items"][0]["due_date"] == due
