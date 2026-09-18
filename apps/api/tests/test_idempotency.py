from __future__ import annotations

import pytest
from app.common.errors import IdempotencyConflictError
from app.platform.idempotency import service
from sqlalchemy.orm import Session


def test_same_key_same_params_replays_stored_result(db: Session) -> None:
    params = {"amount": 5000, "charge_id": "chg_1"}

    guard = service.begin(db, "org_1", "payments.record", "key-1", params)
    assert guard.replay is None
    service.complete(db, guard, status=201, body={"payment_id": "pay_1"})
    db.commit()

    again = service.begin(db, "org_1", "payments.record", "key-1", params)
    assert again.replay == {"status": 201, "body": {"payment_id": "pay_1"}}


def test_same_key_different_params_is_rejected(db: Session) -> None:
    guard = service.begin(db, "org_1", "payments.record", "key-2", {"amount": 5000})
    service.complete(db, guard, status=201, body={"payment_id": "pay_2"})
    db.commit()

    with pytest.raises(IdempotencyConflictError):
        service.begin(db, "org_1", "payments.record", "key-2", {"amount": 9999})


def test_keys_are_scoped_per_school(db: Session) -> None:
    params = {"amount": 5000}
    g1 = service.begin(db, "org_A", "payments.record", "shared-key", params)
    service.complete(db, g1, status=201, body={"payment_id": "pay_A"})
    db.commit()

    # Same key under a different org is a brand-new operation, not a replay.
    g2 = service.begin(db, "org_B", "payments.record", "shared-key", params)
    assert g2.replay is None
