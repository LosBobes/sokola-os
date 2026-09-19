"""TEN-Q01 `ListMyAvailableTenantContexts` (M03 §12, §5.4, §6.4).

The chooser's query. Most of what is worth testing here is what it must *not*
do: duplicate a school per role, offer a school the request guard would then
refuse, leak anything §5.4 lists as forbidden, or sort unstably.
"""

from __future__ import annotations

import pytest
from app.application.available_contexts import (
    MAX_PAGE_SIZE,
    list_available_contexts,
)
from app.common.errors import BadRequestError
from app.domains.identity import sessions
from app.domains.identity.accounts import create_account_with_identity
from app.domains.identity.auth_enums import GOOGLE_ISSUER, GOOGLE_PROVIDER
from app.domains.identity.auth_models import AuthSession, UserAccount
from app.domains.identity.enums import RoleCode
from app.domains.identity.models import Person
from app.domains.school.enums import MembershipStatus, SchoolStatus
from app.domains.school.models import School
from app.domains.tenancy import context as tenant_context
from app.domains.tenancy.enums import WORKSPACE_ADMIN, SchoolMode
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.factories import add_membership, assign_role, make_person, make_school


def _signed_in(db: Session, subject: str) -> tuple[Person, UserAccount, AuthSession]:
    person = make_person(db, given="K", family=subject[-4:])
    account, identity = create_account_with_identity(
        db,
        person_id=person.id,
        provider_key=GOOGLE_PROVIDER,
        issuer=GOOGLE_ISSUER,
        subject=subject,
    )
    session, _ = sessions.issue_session(db, account=account, identity=identity)
    db.commit()
    return person, account, session


def _member(
    db: Session,
    person: Person,
    school: School,
    role: RoleCode = RoleCode.MANAGER,
    membership: MembershipStatus = MembershipStatus.ACTIVE,
) -> None:
    add_membership(db, person=person, school=school, status=membership)
    assign_role(db, person=person, school=school, role=role)
    db.commit()


def _ask(db: Session, person: Person, account: UserAccount, **kwargs):
    return list_available_contexts(
        db, person_id=person.id, user_account_id=account.id, **kwargs
    )


# ---------------------------------------------------------------------------
# §6.4 — one item per school, never one per role
# ---------------------------------------------------------------------------


def test_two_roles_in_one_school_give_one_context_with_two_workspaces(
    db: Session,
) -> None:
    """§6.4 verbatim: "ista osoba sa dve uloge u istoj školi dobija jedan
    tenant kontekst sa dve workspace opcije".

    Building this off role assignments directly would produce the school
    twice, which is exactly the bug the section names.
    """
    person, account, _ = _signed_in(db, "sub-two-roles")
    school = make_school(db, name="Dvostruka")
    add_membership(db, person=person, school=school)
    assign_role(db, person=person, school=school, role=RoleCode.MANAGER)
    assign_role(db, person=person, school=school, role=RoleCode.TRAINER)
    db.commit()

    page = _ask(db, person, account)

    assert len(page.items) == 1
    keys = [o.workspace_key for o in page.items[0].workspace_options]
    assert keys == ["ADMIN", "INSTRUCTOR"]


def test_two_roles_sharing_a_workspace_give_one_option(db: Session) -> None:
    """OWNER and MANAGER both map to ADMIN, so the option appears once. A set
    that kept them apart would show the same tab twice."""
    person, account, _ = _signed_in(db, "sub-same-ws")
    school = make_school(db)
    add_membership(db, person=person, school=school)
    assign_role(db, person=person, school=school, role=RoleCode.OWNER)
    assign_role(db, person=person, school=school, role=RoleCode.MANAGER)
    db.commit()

    page = _ask(db, person, account)
    assert [o.workspace_key for o in page.items[0].workspace_options] == ["ADMIN"]


# ---------------------------------------------------------------------------
# §6.1 — an offered school must survive the request guard
# ---------------------------------------------------------------------------


def test_a_role_without_membership_offers_nothing(db: Session) -> None:
    """§6.1 point 4 needs both. Offering a school on the strength of a role
    alone would put it in the chooser and then have §8 refuse it — the worst
    of both, since the person sees access they do not have."""
    person, account, _ = _signed_in(db, "sub-norole")
    school = make_school(db)
    assign_role(db, person=person, school=school, role=RoleCode.MANAGER)
    db.commit()

    assert _ask(db, person, account).items == ()


def test_a_terminated_membership_offers_nothing(db: Session) -> None:
    person, account, _ = _signed_in(db, "sub-term")
    school = make_school(db)
    _member(db, person, school, membership=MembershipStatus.TERMINATED)

    assert _ask(db, person, account).items == ()


def test_a_deactivated_school_is_not_offered(db: Session) -> None:
    """§6.3: not a permitted user context at all."""
    person, account, _ = _signed_in(db, "sub-deact")
    school = make_school(db, name="Ugašena")
    _member(db, person, school)
    # `ck_school_deactivated_at` requires the timestamp alongside the status —
    # a deactivated school that cannot say when is not a state the schema holds.
    db.execute(
        text(
            "UPDATE school SET status = 'DEACTIVATED', deactivated_at = now()"
            " WHERE id = :id"
        ),
        {"id": school.id},
    )
    db.commit()

    assert _ask(db, person, account).items == ()


def test_a_school_in_preparation_is_offered_as_setup_only(db: Session) -> None:
    person, account, _ = _signed_in(db, "sub-prep")
    school = make_school(db, name="Priprema", status=SchoolStatus.IN_PREPARATION)
    _member(db, person, school, role=RoleCode.OWNER)

    page = _ask(db, person, account)
    assert page.items[0].school_mode is SchoolMode.SETUP_ONLY


def test_no_access_is_a_successful_empty_result(db: Session) -> None:
    """§12: "Prazna lista je uspešan neutralan rezultat." Not an error, and
    not a hint that something was withheld."""
    person, account, _ = _signed_in(db, "sub-none")
    page = _ask(db, person, account)
    assert page.items == ()
    assert page.next_cursor is None


def test_another_persons_school_is_not_offered(db: Session) -> None:
    """§5.4: no other people's schools. The most basic tenant property this
    query has, and the one a join written slightly wrong would lose."""
    mine, my_account, _ = _signed_in(db, "sub-mine")
    theirs, _, _ = _signed_in(db, "sub-theirs")
    my_school = make_school(db, name="Moja")
    their_school = make_school(db, name="Njihova")
    _member(db, mine, my_school)
    _member(db, theirs, their_school)

    page = _ask(db, mine, my_account)
    assert [i.school_id for i in page.items] == [my_school.id]


# ---------------------------------------------------------------------------
# §12 — the sort
# ---------------------------------------------------------------------------


def test_last_used_sorts_first_then_name(db: Session) -> None:
    """§12's order: last valid use descending, then normalized name, then id.

    `Ana` would sort before `Zoran` on name alone, so putting `Zoran` last-used
    proves the first key actually wins rather than the list merely looking
    sorted.
    """
    person, account, session = _signed_in(db, "sub-sort")
    ana = make_school(db, name="Ana")
    zoran = make_school(db, name="Zoran")
    _member(db, person, ana)
    _member(db, person, zoran)

    tenant_context.select_context(
        db, session=session, account=account, school=zoran, workspace_key=WORKSPACE_ADMIN
    )
    db.commit()

    names = [i.school_display_name for i in _ask(db, person, account).items]
    assert names == ["Zoran", "Ana"]


def test_never_used_schools_fall_back_to_name_order(db: Session) -> None:
    person, account, _ = _signed_in(db, "sub-name")
    for name in ("Ćuprija", "Ada", "Zemun"):
        school = make_school(db, name=name)
        _member(db, person, school)

    names = [i.school_display_name for i in _ask(db, person, account).items]
    # Accent-folded: Ćuprija sorts as "cuprija", between Ada and Zemun.
    assert names == ["Ada", "Ćuprija", "Zemun"]


def test_the_last_used_workspace_comes_back_as_a_hint(db: Session) -> None:
    """§5.4's `last_used_workspace_key`, "hint, bez statusa autoriteta"."""
    person, account, session = _signed_in(db, "sub-hint")
    school = make_school(db)
    _member(db, person, school)
    tenant_context.select_context(
        db, session=session, account=account, school=school, workspace_key=WORKSPACE_ADMIN
    )
    db.commit()

    assert _ask(db, person, account).items[0].last_used_workspace_key == WORKSPACE_ADMIN


def test_an_unvisited_school_has_no_hint(db: Session) -> None:
    person, account, _ = _signed_in(db, "sub-nohint")
    school = make_school(db)
    _member(db, person, school)

    assert _ask(db, person, account).items[0].last_used_workspace_key is None


# ---------------------------------------------------------------------------
# §12 — pagination
# ---------------------------------------------------------------------------


def test_paging_covers_every_school_exactly_once(db: Session) -> None:
    """§12's bounded pagination: "stabilan cursor/sort; nema preskakanja/
    duplikata". Walked page by page and compared as a multiset, because a
    cursor off by one loses or repeats exactly one row and a set would hide
    the repeat."""
    person, account, _ = _signed_in(db, "sub-page")
    expected = set()
    for n in range(7):
        school = make_school(db, name=f"Skola {n:02d}")
        _member(db, person, school)
        expected.add(school.id)

    seen: list[str] = []
    cursor = None
    for _ in range(10):  # generous bound; the loop should end well before this
        page = _ask(db, person, account, cursor=cursor, page_size=2)
        seen.extend(i.school_id for i in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break

    assert cursor is None, "paging did not terminate"
    assert len(seen) == len(expected), f"{len(seen)} rows for {len(expected)} schools"
    assert set(seen) == expected


def test_page_size_is_bounded(db: Session) -> None:
    person, account, _ = _signed_in(db, "sub-bound")
    for bad in (0, -1, MAX_PAGE_SIZE + 1):
        with pytest.raises(BadRequestError):
            _ask(db, person, account, page_size=bad)


def test_a_malformed_cursor_is_refused(db: Session) -> None:
    """Not silently ignored: a cursor that decoded to nothing would quietly
    restart paging from the top and the caller would loop forever."""
    person, account, _ = _signed_in(db, "sub-badcur")
    with pytest.raises(BadRequestError):
        _ask(db, person, account, cursor="!!!not-base64!!!")


def test_the_cursor_is_opaque(db: Session) -> None:
    """§5.4 keeps the chooser free of readable detail; a cursor spelling out a
    school id and a timestamp would be a small leak of that shape."""
    person, account, _ = _signed_in(db, "sub-opaque")
    for n in range(3):
        school = make_school(db, name=f"Skola {n}")
        _member(db, person, school)

    page = _ask(db, person, account, page_size=1)
    assert page.next_cursor is not None
    assert page.next_cursor.isascii()
    for item in page.items:
        assert item.school_id not in page.next_cursor


# ---------------------------------------------------------------------------
# §5.4 — what must not come back
# ---------------------------------------------------------------------------


def test_the_result_carries_only_what_5_4_allows(db: Session) -> None:
    """Asserted against the dataclass's fields, so a field added later fails
    here rather than shipping. §5.4 forbids finances, debt, attendance,
    documents, message content and member counts."""
    person, account, _ = _signed_in(db, "sub-thin")
    school = make_school(db)
    _member(db, person, school)

    entry = _ask(db, person, account).items[0]
    assert set(entry.__dataclass_fields__) == {
        "school_id",
        "school_display_name",
        "school_mode",
        "workspace_options",
        "last_used_workspace_key",
    }


def test_a_student_only_account_sees_nothing(db: Session) -> None:
    """M05 has no student role, so there is no workspace to offer. An empty
    list rather than a guess — inventing one is exactly what F-29 is open to
    avoid."""
    person, account, _ = _signed_in(db, "sub-student")
    school = make_school(db)
    _member(db, person, school, role=RoleCode.STUDENT)

    assert _ask(db, person, account).items == ()
