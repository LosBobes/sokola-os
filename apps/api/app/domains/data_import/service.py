"""CSV import for people/groups (PRD 11, v1).

Three-step flow, mirroring how the rest of the system treats risky bulk writes
as deliberate, reviewable operations (cf. the merge-review workflow in
``app.domains.people.service``):

  1. ``create_upload`` parses the CSV against a FIXED header and stages every
     row as an :class:`ImportRow` — no validation, no writes to Person/Group
     yet. The v1 header is exactly::

         given_name,family_name,group_name,local_member_code

     ``given_name``/``family_name`` are required columns; ``group_name`` and
     ``local_member_code`` are optional (may be blank per-row, or the column
     may be absent entirely). This is a deliberate v1 scope cut over a full
     flexible column-mapper — see the PR description.
  2. ``preview_batch`` is a dry-run: it validates every staged row (required
     fields present, named group exists in this org, local member code not
     already taken) and flags rows that look like an existing person, without
     writing anything to Person/Group tables. Re-runnable until commit.
  3. ``commit_batch`` creates a real Person (+ GroupMembership, if a group was
     named) for every row that was VALID at the last preview, and SKIPS the
     rest — a partial result, never an all-or-nothing transaction. A batch may
     be committed at most once; there is no rollback (see module docstring in
     ``app.domains.data_import.enums`` and the PR description — undoing a
     commit would mean deleting real Person rows that other domains may
     already reference, which is unsafe to do blindly).
"""

from __future__ import annotations

import csv
import datetime as dt
import io

from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass
from app.common.errors import BadRequestError, ConflictError, NotFoundError
from app.common.pagination import Page, PageParams
from app.domains.data_import import repository
from app.domains.data_import.enums import (
    ImportBatchStatus,
    ImportRowCommitStatus,
    ImportRowValidationStatus,
)
from app.domains.data_import.models import ImportBatch, ImportRow
from app.domains.data_import.schemas import (
    ImportBatchResponse,
    ImportCommitResponse,
    ImportPreviewResponse,
    ImportRowCommitResult,
    ImportRowPreviewResult,
)
from app.domains.groups.models import GroupMembership
from app.domains.identity.enums import PersonIdentityStatus
from app.domains.identity.models import Person
from app.domains.organization.models import OrganizationMembership
from app.platform.audit.service import record_audit
from app.platform.outbox.service import enqueue
from app.security.context import RequestContext

REQUIRED_COLUMNS = ("given_name", "family_name")
OPTIONAL_COLUMNS = ("group_name", "local_member_code")


def _batch_response(batch: ImportBatch) -> ImportBatchResponse:
    return ImportBatchResponse.model_validate(batch)


def _get_batch_or_404(db: Session, context: RequestContext, batch_id: str) -> ImportBatch:
    batch = repository.get_org_batch(db, context.organization_id, batch_id)
    if batch is None:
        raise NotFoundError("Uvoz nije pronađen.")
    return batch


# ---------------------------------------------------------------------------
# 1. Upload — parse a fixed-header CSV into staged rows
# ---------------------------------------------------------------------------


def create_upload(
    db: Session, context: RequestContext, filename: str, content: bytes
) -> ImportBatchResponse:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BadRequestError("Fajl mora biti CSV u UTF-8 kodiranju.") from exc

    reader = csv.DictReader(io.StringIO(text))
    header = reader.fieldnames or []
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise BadRequestError(
            "CSV fajl mora imati kolone: "
            f"{', '.join(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)}. "
            f"Nedostaje: {', '.join(missing)}.",
            details={"required_columns": list(REQUIRED_COLUMNS)},
        )

    batch = ImportBatch(
        organization_id=context.organization_id,
        source_filename=filename or "upload.csv",
        created_by_person_id=context.person_id,
    )
    db.add(batch)
    db.flush()

    total = 0
    for row_number, raw_row in enumerate(reader, start=1):
        given = (raw_row.get("given_name") or "").strip()
        family = (raw_row.get("family_name") or "").strip()
        group_name = (raw_row.get("group_name") or "").strip() or None
        local_code = (raw_row.get("local_member_code") or "").strip() or None
        db.add(
            ImportRow(
                batch_id=batch.id,
                organization_id=context.organization_id,
                row_number=row_number,
                given_name=given,
                family_name=family,
                group_name=group_name,
                local_member_code=local_code,
            )
        )
        total += 1
    batch.total_rows = total

    record_audit(
        db,
        data_class=AuditDataClass.IDENTITY,
        action="import.uploaded",
        entity_type="import_batch",
        entity_id=batch.id,
        summary=f"Učitan fajl za uvoz „{batch.source_filename}“ ({total} redova).",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    db.commit()
    return _batch_response(batch)


def get_upload(db: Session, context: RequestContext, batch_id: str) -> ImportBatchResponse:
    return _batch_response(_get_batch_or_404(db, context, batch_id))


def list_uploads(
    db: Session, context: RequestContext, params: PageParams
) -> Page[ImportBatchResponse]:
    batches, total = repository.list_org_batches(db, context.organization_id, params)
    return Page.build([_batch_response(b) for b in batches], total, params)


# ---------------------------------------------------------------------------
# 2. Preview — dry-run validation, writes nothing to Person/Group
# ---------------------------------------------------------------------------


def _validate_row(
    db: Session, context: RequestContext, row: ImportRow, seen_codes: dict[str, int]
) -> None:
    reasons: list[str] = []
    given = row.given_name.strip()
    family = row.family_name.strip()
    if not given or not family:
        reasons.append("Ime i prezime su obavezni.")

    if row.group_name:
        group = repository.find_group_by_name(db, context.organization_id, row.group_name)
        if group is None:
            reasons.append(f"Grupa „{row.group_name}“ ne postoji u ovoj školi.")

    if row.local_member_code:
        code = row.local_member_code
        if repository.find_local_code_owner(db, context.organization_id, code) is not None:
            reasons.append(f"Lokalna šifra člana „{code}“ se već koristi u ovoj školi.")
        elif code in seen_codes:
            reasons.append(
                f"Lokalna šifra člana „{code}“ se ponavlja u fajlu (red {seen_codes[code]})."
            )
        else:
            seen_codes[code] = row.row_number

    duplicates: list[str] = []
    if given and family:
        candidates = repository.find_duplicate_people(
            db, context.organization_id, given, family
        )
        duplicates = [p.id for p in candidates]

    row.validation_reason = "; ".join(reasons) or None
    row.validation_status = (
        ImportRowValidationStatus.INVALID if reasons else ImportRowValidationStatus.VALID
    )
    row.duplicate_person_ids = duplicates or None


def preview_batch(
    db: Session, context: RequestContext, batch_id: str
) -> ImportPreviewResponse:
    batch = _get_batch_or_404(db, context, batch_id)
    if batch.status is ImportBatchStatus.COMMITTED:
        raise ConflictError("Uvoz je već potvrđen i ne može se ponovo pregledati.")

    rows = repository.list_rows(db, batch.id)
    seen_codes: dict[str, int] = {}
    for row in rows:
        _validate_row(db, context, row, seen_codes)

    valid = sum(1 for r in rows if r.validation_status is ImportRowValidationStatus.VALID)
    batch.valid_rows = valid
    batch.invalid_rows = len(rows) - valid
    batch.status = ImportBatchStatus.PREVIEWED
    batch.previewed_at = dt.datetime.now(tz=dt.UTC)

    record_audit(
        db,
        data_class=AuditDataClass.IDENTITY,
        action="import.previewed",
        entity_type="import_batch",
        entity_id=batch.id,
        summary=(
            f"Pregledan uvoz „{batch.source_filename}“: {valid} validno, "
            f"{batch.invalid_rows} nevalidno."
        ),
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    db.commit()

    return ImportPreviewResponse(
        batch=_batch_response(batch),
        rows=[
            ImportRowPreviewResult(
                row_number=r.row_number,
                given_name=r.given_name,
                family_name=r.family_name,
                group_name=r.group_name,
                local_member_code=r.local_member_code,
                valid=r.validation_status is ImportRowValidationStatus.VALID,
                reason=r.validation_reason,
                duplicate_person_ids=list(r.duplicate_person_ids or []),
            )
            for r in rows
        ],
    )


# ---------------------------------------------------------------------------
# 3. Commit — create valid rows as real Person records, skip the rest
# ---------------------------------------------------------------------------


def commit_batch(db: Session, context: RequestContext, batch_id: str) -> ImportCommitResponse:
    batch = _get_batch_or_404(db, context, batch_id)
    if batch.status is ImportBatchStatus.COMMITTED:
        raise ConflictError("Uvoz je već potvrđen.")
    if batch.status is ImportBatchStatus.PENDING:
        raise ConflictError("Uvoz mora prvo biti pregledan (probna provera) pre potvrde.")

    rows = repository.list_rows(db, batch.id)
    results: list[ImportRowCommitResult] = []
    created = 0
    skipped = 0

    for row in rows:
        if row.validation_status is not ImportRowValidationStatus.VALID:
            row.commit_status = ImportRowCommitStatus.SKIPPED
            row.commit_reason = row.validation_reason or "Red nije validan."
            skipped += 1
            results.append(
                ImportRowCommitResult(
                    row_number=row.row_number,
                    given_name=row.given_name,
                    family_name=row.family_name,
                    outcome="SKIPPED",
                    reason=row.commit_reason,
                    person_id=None,
                )
            )
            continue

        given = row.given_name.strip()
        family = row.family_name.strip()
        person = Person(
            given_name=given,
            family_name=family,
            display_name=f"{given} {family}",
            identity_status=PersonIdentityStatus.PROVISIONAL,
        )
        db.add(person)
        db.flush()
        db.add(
            OrganizationMembership(
                organization_id=context.organization_id,
                person_id=person.id,
                local_member_code=row.local_member_code,
            )
        )

        if row.group_name:
            group = repository.find_group_by_name(db, context.organization_id, row.group_name)
            if group is not None:
                db.add(
                    GroupMembership(
                        group_id=group.id,
                        organization_id=context.organization_id,
                        person_id=person.id,
                        joined_at=dt.datetime.now(tz=dt.UTC),
                    )
                )

        row.commit_status = ImportRowCommitStatus.CREATED
        row.created_person_id = person.id
        created += 1
        results.append(
            ImportRowCommitResult(
                row_number=row.row_number,
                given_name=given,
                family_name=family,
                outcome="CREATED",
                reason=None,
                person_id=person.id,
            )
        )

        record_audit(
            db,
            data_class=AuditDataClass.IDENTITY,
            action="person.created",
            entity_type="person",
            entity_id=person.id,
            summary=f"Dodata osoba „{person.display_name}“ uvozom fajla „{batch.source_filename}“.",
            organization_id=context.organization_id,
            actor_person_id=context.person_id,
            context={"import_batch_id": batch.id, "row_number": row.row_number},
        )
        enqueue(
            db,
            event_type="person.created",
            payload={"person_id": person.id, "organization_id": context.organization_id},
            organization_id=context.organization_id,
        )

    batch.status = ImportBatchStatus.COMMITTED
    batch.committed_at = dt.datetime.now(tz=dt.UTC)
    batch.created_rows = created
    batch.skipped_rows = skipped

    record_audit(
        db,
        data_class=AuditDataClass.IDENTITY,
        action="import.committed",
        entity_type="import_batch",
        entity_id=batch.id,
        summary=(
            f"Potvrđen uvoz „{batch.source_filename}“: {created} kreirano, {skipped} preskočeno."
        ),
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    enqueue(
        db,
        event_type="import.committed",
        payload={
            "batch_id": batch.id,
            "organization_id": context.organization_id,
            "created_rows": created,
            "skipped_rows": skipped,
        },
        organization_id=context.organization_id,
    )
    db.commit()

    return ImportCommitResponse(batch=_batch_response(batch), rows=results)
