"""Nexus API — Sources (upload, ingest, search)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel, Field

from src.core.hybrid_search import get_search_profile, reciprocal_rank_fusion
from src.exceptions import (
    FileTooLargeError,
    NotFoundError,
    UnsupportedFormatError,
)
from src.infra.nexus_obs_tracing import traced
from src.infra.nexus_vault_keys import AuthContext, get_current_user

router = APIRouter(prefix="/sources", tags=["Sources"])

MAX_FILE_SIZE_MB = 100
SUPPORTED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
    "text/html",
    "application/json",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "audio/mpeg",
    "audio/wav",
    "audio/mp4",
    "image/png",
    "image/jpeg",
    "image/webp",
}


# ── Schemas ──────────────────────────────────────────────────


class SourceFromURL(BaseModel):
    url: str = Field(..., max_length=2048)
    title: str | None = None
    source_type: str = "url"


class SourceFromText(BaseModel):
    content: str = Field(..., min_length=1, max_length=500_000)
    title: str = "Pasted Text"
    source_type: str = "pasted_text"


class SourceResponse(BaseModel):
    id: str
    title: str | None
    source_type: str
    status: str
    word_count: int = 0
    chunk_count: int = 0


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    source_ids: list[str] | None = None
    limit: int = 10
    min_score: float = 0.5
    search_type: str = "hybrid"  # vector | text | hybrid
    search_profile: str = Field(
        default="balanced",
        description="Retrieval profile: fast | balanced | deep",
    )
    fusion_k: int = Field(
        default=60,
        ge=1,
        le=200,
        description="RRF smoothing factor (higher favors top-rank stability).",
    )


# ── Endpoints ────────────────────────────────────────────────


@router.post("/upload", response_model=SourceResponse, status_code=201)
@traced("sources.upload")
async def upload_source(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Upload a file source for processing."""
    from src.infra.nexus_vault_keys import rate_limiter

    rate_limiter.check(f"upload:{auth.user_id}", max_requests=10, window_seconds=60)

    # Validate file
    if file.content_type and file.content_type not in SUPPORTED_MIME_TYPES:
        raise UnsupportedFormatError(f"Unsupported file type: {file.content_type}")

    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise FileTooLargeError(f"File too large: {size_mb:.1f}MB (max {MAX_FILE_SIZE_MB}MB)")

    # Determine source type from mime
    mime_to_type = {
        "application/pdf": "pdf",
        "text/plain": "text",
        "text/markdown": "markdown",
        "text/csv": "csv",
    }
    source_type = mime_to_type.get(file.content_type or "", "upload")

    from src.config import get_settings
    from src.infra.nexus_data_persist import sources_repo

    settings = get_settings()

    # Persist file to local storage
    content_hash = hashlib.sha256(content).hexdigest()[:16]
    safe_filename = f"{content_hash}_{file.filename or 'upload'}"
    tenant_dir = Path(settings.storage_local_path) / "sources" / auth.tenant_id
    tenant_dir.mkdir(parents=True, exist_ok=True)
    file_path = tenant_dir / safe_filename
    file_path.write_bytes(content)

    result = await sources_repo.create(
        data={
            "title": title or file.filename or "Untitled",
            "source_type": source_type,
            "status": "pending",
            "asset_mime_type": file.content_type,
            "asset_size_bytes": len(content),
            "asset_file_path": str(file_path),
        },
        tenant_id=auth.tenant_id,
    )

    # Enqueue async processing (extract text, embed, generate insights)
    from src.worker import process_source as process_source_task

    process_source_task.delay(result["id"], auth.tenant_id)

    return result


@router.post("/from-url", response_model=SourceResponse, status_code=201)
@traced("sources.from_url")
async def create_from_url(
    data: SourceFromURL,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a source from a URL."""
    from src.infra.nexus_vault_keys import rate_limiter

    rate_limiter.check(f"upload:{auth.user_id}", max_requests=10, window_seconds=60)

    from src.infra.nexus_data_persist import sources_repo

    result = await sources_repo.create(
        data={
            "title": data.title or data.url[:100],
            "source_type": data.source_type,
            "status": "pending",
            "asset_url": data.url,
        },
        tenant_id=auth.tenant_id,
    )

    return result


@router.post("/from-text", response_model=SourceResponse, status_code=201)
@traced("sources.from_text")
async def create_from_text(
    data: SourceFromText,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a source from pasted text."""
    from src.infra.nexus_data_persist import sources_repo

    word_count = len(data.content.split())

    result = await sources_repo.create(
        data={
            "title": data.title,
            "source_type": data.source_type,
            "status": "ready",
            "full_text": data.content,
            "word_count": word_count,
        },
        tenant_id=auth.tenant_id,
    )

    return result


@router.get("", response_model=list[SourceResponse])
@traced("sources.list")
async def list_sources(
    auth: AuthContext = Depends(get_current_user),
    source_type: str | None = None,
    status: str | None = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List sources for the current tenant."""
    from src.infra.nexus_data_persist import sources_repo

    filters = {}
    if source_type:
        filters["source_type"] = source_type
    if status:
        filters["status"] = status

    return await sources_repo.list_all(
        auth.tenant_id,
        limit=limit,
        offset=offset,
        filters=filters if filters else None,
    )


@router.get("/{source_id}", response_model=dict)
@traced("sources.get")
async def get_source(
    source_id: str,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Get a source by ID."""
    from src.infra.nexus_data_persist import sources_repo

    result = await sources_repo.get_by_id(source_id, auth.tenant_id)
    if not result:
        raise NotFoundError(f"Source '{source_id}' not found")
    return result


@router.delete("/{source_id}", status_code=204)
@traced("sources.delete")
async def delete_source(
    source_id: str,
    auth: AuthContext = Depends(get_current_user),
) -> None:
    """Soft-delete a source."""
    from src.infra.nexus_data_persist import sources_repo

    deleted = await sources_repo.soft_delete(source_id, auth.tenant_id)
    if not deleted:
        raise NotFoundError(f"Source '{source_id}' not found")


@router.post("/search", response_model=list[dict])
@traced("sources.search")
async def search_sources(
    data: SearchRequest,
    auth: AuthContext = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Search source content (vector, text, or hybrid)."""
    from src.infra.nexus_data_persist import sources_repo

    results: list[dict] = []
    vector_results: list[dict] = []
    text_results: list[dict] = []
    profile = get_search_profile(data.search_profile)
    candidate_limit = max(data.limit, data.limit * profile.candidate_multiplier)

    if data.search_type in ("vector", "hybrid"):
        # Generate embedding for query
        from src.agents.nexus_model_layer import model_manager

        embedding_provider = await model_manager.provision_embedding(tenant_id=auth.tenant_id)
        embedding_result = await embedding_provider.embed([data.query])
        query_embedding = embedding_result.embeddings[0]

        vector_results = await sources_repo.vector_search(
            query_embedding=query_embedding,
            source_ids=data.source_ids or [],
            tenant_id=auth.tenant_id,
            limit=candidate_limit,
            min_score=data.min_score,
        )

    if data.search_type in ("text", "hybrid"):
        text_results = await sources_repo.text_search(
            query_text=data.query,
            tenant_id=auth.tenant_id,
            limit=candidate_limit,
        )

    if data.search_type == "hybrid":
        # SurfSense-inspired reciprocal rank fusion for higher quality retrieval.
        results = reciprocal_rank_fusion(
            vector_results=vector_results,
            text_results=text_results,
            limit=data.limit,
            k=data.fusion_k,
            vector_weight=profile.vector_weight,
            text_weight=profile.text_weight,
        )
    elif data.search_type == "vector":
        results = vector_results[: data.limit]
    else:
        results = text_results[: data.limit]

    return results
