"""Seed the first platform role assignment, from a database connection.

M05 §2 leaves a chicken-and-egg problem: `platform.roles.manage` is bound to
`PLATFORM_SECURITY_ADMIN` alone, so the command that grants platform roles
needs a platform admin to already exist. The contract's answer is that the
first one arrives out of band. This is that band.

It is a script and not an endpoint on purpose. Granting platform access is the
single most consequential thing anyone can do in this system, and the control
that matters most here is not a permission check — it is that **the caller
needs the database**. An attacker with a session, however privileged, cannot
reach this. That property is also what makes the missing step-up (F-45) less
sharp than it would otherwise be: the unprotected mutation command cannot
create platform access from nothing, only extend it from an existing admin.

Usage::

    .venv/bin/python -m scripts.grant_platform_role \\
        --email ops@example.com \\
        --role PLATFORM_SECURITY_ADMIN \\
        --ticket OPS-1234

It refuses to create a second open assignment for the same account and role,
so re-running it is safe.
"""

from __future__ import annotations

import argparse
import sys

from app.db import SessionLocal
from app.domains.authorization.platform_enums import (
    OPEN_PLATFORM_ROLE_STATUSES,
    PlatformRoleKey,
    PlatformRoleStatus,
)
from app.domains.authorization.platform_models import PlatformRoleAssignment
from app.domains.identity.auth_models import AuthIdentity, UserAccount
from app.platform import clock
from sqlalchemy import select


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="verified login email")
    parser.add_argument(
        "--role",
        required=True,
        choices=[r.value for r in PlatformRoleKey],
        help="platform role key",
    )
    parser.add_argument(
        "--ticket", required=True, help="change-management reference (1..100 chars)"
    )
    args = parser.parse_args(argv)

    role_key = PlatformRoleKey(args.role)
    with SessionLocal() as db:
        account_id = db.execute(
            select(AuthIdentity.user_account_id).where(
                AuthIdentity.login_email.ilike(args.email),
                AuthIdentity.unlinked_at.is_(None),
            )
        ).scalar_one_or_none()
        if account_id is None:
            print(f"No live identity for {args.email!r}.", file=sys.stderr)
            return 2
        if db.get(UserAccount, account_id) is None:
            print("Identity points at no account.", file=sys.stderr)
            return 2

        existing = db.execute(
            select(PlatformRoleAssignment).where(
                PlatformRoleAssignment.user_account_id == account_id,
                PlatformRoleAssignment.role_key == role_key,
                PlatformRoleAssignment.status.in_(OPEN_PLATFORM_ROLE_STATUSES),
            )
        ).scalar_one_or_none()
        if existing is not None:
            print(
                f"Already holds {role_key.value} (assignment {existing.id}, "
                f"status {existing.status.value}); nothing to do."
            )
            return 0

        assignment = PlatformRoleAssignment(
            user_account_id=account_id,
            role_key=role_key,
            status=PlatformRoleStatus.ACTIVE,
            valid_from=clock.now(),
            valid_until=None,
            source_ticket_ref=args.ticket,
            # Self-attributed: there is no prior admin to credit, which is the
            # whole reason this path exists. The ticket reference is the
            # external record of who authorised it.
            created_by_account_id=account_id,
        )
        db.add(assignment)
        db.commit()
        print(f"Granted {role_key.value} to {args.email} as {assignment.id}.")
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry point
    raise SystemExit(main())
