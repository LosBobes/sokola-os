from __future__ import annotations

import io
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from fastapi.responses import StreamingResponse

from app.common.pagination import Page, PageParams, page_params
from app.domains.documents import service
from app.domains.documents.enums import DocumentType, DocumentVisibility, RetentionPeriod
from app.domains.documents.schemas import DocumentResponse
from app.security.deps import ContextDep, DbDep
from app.security.permissions import PermissionArea, require_permission

router = APIRouter(tags=["documents"])

# Upload is a staff write path. Reads (list/get/download/acknowledge) are
# gated at the resource level in the service instead — a non-staff caller may
# still reach their own or their guarded child's documents.
_staff = require_permission(PermissionArea.DOCUMENTS)
StaffContext = Annotated[ContextDep, Depends(_staff)]


@router.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="uploadDocument",
    responses={400: {"description": "Unsupported format, empty, or oversized file."}},
)
async def upload_document(
    db: DbDep,
    context: StaffContext,
    file: Annotated[UploadFile, File()],
    document_type: Annotated[DocumentType, Form()] = DocumentType.GENERAL,
    visibility: Annotated[DocumentVisibility, Form()] = DocumentVisibility.STAFF_ONLY,
    subject_person_id: Annotated[str | None, Form()] = None,
    retention_period: Annotated[RetentionPeriod | None, Form()] = None,
) -> DocumentResponse:
    data = await file.read()
    return service.upload_document(
        db,
        context,
        filename=file.filename or "dokument",
        content_type=file.content_type or "application/octet-stream",
        data=data,
        document_type=document_type,
        visibility=visibility,
        subject_person_id=subject_person_id,
        retention_period=retention_period,
    )


@router.get("/documents", response_model=Page[DocumentResponse], operation_id="listDocuments")
def list_documents(
    db: DbDep,
    context: ContextDep,
    params: Annotated[PageParams, Depends(page_params)],
    document_type: DocumentType | None = None,
    subject_person_id: str | None = None,
) -> Page[DocumentResponse]:
    return service.list_documents(
        db, context, params, document_type=document_type, subject_person_id=subject_person_id
    )


@router.get(
    "/documents/{document_id}", response_model=DocumentResponse, operation_id="getDocument"
)
def get_document(document_id: str, db: DbDep, context: ContextDep) -> DocumentResponse:
    return service.get_document_metadata(db, context, document_id)


@router.get(
    "/documents/{document_id}/content",
    operation_id="downloadDocumentContent",
    responses={200: {"content": {"application/octet-stream": {}}}},
)
def download_document_content(
    document_id: str, db: DbDep, context: ContextDep
) -> StreamingResponse:
    content = service.download_document(db, context, document_id)
    return StreamingResponse(
        io.BytesIO(content.data),
        media_type=content.content_type,
        headers={"Content-Disposition": f'attachment; filename="{content.filename}"'},
    )


@router.post(
    "/documents/{document_id}/acknowledge",
    response_model=DocumentResponse,
    operation_id="acknowledgeDocument",
    responses={400: {"description": "Document is not a contract."}},
)
def acknowledge_document(
    document_id: str, db: DbDep, context: ContextDep
) -> DocumentResponse:
    return service.acknowledge_document(db, context, document_id)
