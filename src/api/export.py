"""Nexus API — Export (PDF, DOCX, EPUB, Markdown, HTML, TXT)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.exceptions import NotFoundError, ValidationError
from src.infra.nexus_obs_tracing import traced
from src.infra.nexus_vault_keys import AuthContext, get_current_user

router = APIRouter(prefix="/export", tags=["Export"])


# ── Schemas ──────────────────────────────────────────────────


class ExportRequest(BaseModel):
    artifact_id: str | None = None
    notebook_id: str | None = None
    title: str = "Export"
    content: str | None = None
    format: str = Field("pdf", description="pdf, docx, epub, markdown, html, txt")
    include_toc: bool = True
    branding_color: str = "#6366f1"


# ── Endpoints ────────────────────────────────────────────────


@router.post("")
@traced("export.generate")
async def export_content(
    data: ExportRequest,
    auth: AuthContext = Depends(get_current_user),
) -> Response:
    """Export content to the specified format."""
    from src.core.nexus_export_engine import (
        ExportContent,
        ExportOptions,
        export_engine,
    )

    # Resolve content
    content_text = data.content or ""

    if data.artifact_id and not content_text:
        from src.infra.nexus_data_persist import artifacts_repo

        artifact = await artifacts_repo.get_by_id(data.artifact_id, auth.tenant_id)
        if not artifact:
            raise NotFoundError(f"Artifact '{data.artifact_id}' not found")
        content_text = artifact.get("content", "")
        data.title = artifact.get("title", data.title)

    if not content_text:
        raise ValidationError("No content to export")

    # Get notebook name if available
    notebook_name = ""
    if data.notebook_id:
        from src.infra.nexus_data_persist import notebooks_repo

        nb = await notebooks_repo.get_by_id(data.notebook_id, auth.tenant_id)
        if nb:
            notebook_name = nb.get("name", "")

    export_content_obj = ExportContent(
        title=data.title,
        content=content_text,
        author=auth.user_id,
        notebook_name=notebook_name,
    )

    export_options = ExportOptions(
        format=data.format,
        include_toc=data.include_toc,
        branding_color=data.branding_color,
    )

    result = await export_engine.export(export_content_obj, export_options)

    return Response(
        content=result.data,
        media_type=result.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
            "X-File-Size": str(result.file_size_bytes),
        },
    )


@router.get("/formats")
async def list_formats() -> dict[str, Any]:
    """List available export formats."""
    return {
        "formats": [
            {"id": "pdf", "name": "PDF", "mime": "application/pdf", "icon": "📄"},
            {
                "id": "docx",
                "name": "Word (DOCX)",
                "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "icon": "📝",
            },
            {"id": "epub", "name": "EPUB", "mime": "application/epub+zip", "icon": "📖"},
            {"id": "markdown", "name": "Markdown", "mime": "text/markdown", "icon": "📋"},
            {"id": "html", "name": "HTML", "mime": "text/html", "icon": "🌐"},
            {"id": "txt", "name": "Plain Text", "mime": "text/plain", "icon": "📃"},
        ]
    }
