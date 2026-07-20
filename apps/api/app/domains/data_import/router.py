from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.common.pagination import Page, PageParams, page_params
from app.domains.data_import import service
from app.domains.data_import.schemas import (
    ImportBatchResponse,
    ImportCommitResponse,
    ImportPreviewResponse,
)
from app.security.deps import ContextDep, DbDep
from app.security.permissions import PermissionArea, require_permission

router = APIRouter(tags=["import"])

# Staff who may bulk-import people/groups.
_staff = require_permission(PermissionArea.IMPORT)
StaffContext = Annotated[ContextDep, Depends(_staff)]


@router.post(
    "/import/uploads",
    response_model=ImportBatchResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createImportUpload",
    responses={400: {"description": "CSV missing a required column."}},
)
async def create_import_upload(
    db: DbDep, context: StaffContext, file: Annotated[UploadFile, File()]
) -> ImportBatchResponse:
    content = await file.read()
    return service.create_upload(db, context, file.filename or "upload.csv", content)


@router.get(
    "/import/uploads",
    response_model=Page[ImportBatchResponse],
    operation_id="listImportUploads",
)
def list_import_uploads(
    db: DbDep, context: StaffContext, params: Annotated[PageParams, Depends(page_params)]
) -> Page[ImportBatchResponse]:
    return service.list_uploads(db, context, params)


@router.get(
    "/import/uploads/{batch_id}",
    response_model=ImportBatchResponse,
    operation_id="getImportUpload",
)
def get_import_upload(batch_id: str, db: DbDep, context: StaffContext) -> ImportBatchResponse:
    return service.get_upload(db, context, batch_id)


@router.post(
    "/import/uploads/{batch_id}/preview",
    response_model=ImportPreviewResponse,
    operation_id="previewImportUpload",
    responses={409: {"description": "Import already committed."}},
)
def preview_import_upload(
    batch_id: str, db: DbDep, context: StaffContext
) -> ImportPreviewResponse:
    return service.preview_batch(db, context, batch_id)


@router.post(
    "/import/uploads/{batch_id}/commit",
    response_model=ImportCommitResponse,
    operation_id="commitImportUpload",
    responses={409: {"description": "Not yet previewed, or already committed."}},
)
def commit_import_upload(
    batch_id: str, db: DbDep, context: StaffContext
) -> ImportCommitResponse:
    return service.commit_batch(db, context, batch_id)
