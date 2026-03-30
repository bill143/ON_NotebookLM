"""Nexus API — AI Models (registry, defaults, credentials, usage)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.infra.nexus_vault_keys import AuthContext, get_current_user
from src.infra.nexus_obs_tracing import traced
from src.exceptions import NotFoundError

router = APIRouter(prefix="/models", tags=["AI Models"])


# ── Schemas ──────────────────────────────────────────────────

class ModelRegister(BaseModel):
    name: str
    provider: str
    model_type: str
    model_id_string: str
    is_local: bool = False
    base_url: Optional[str] = None
    max_tokens: int = 4096
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    config: dict = {}


class CredentialStore(BaseModel):
    provider: str
    credential_name: str
    api_key: str = Field(..., min_length=1)


class DefaultModelSet(BaseModel):
    task_type: str
    model_id: str
    priority: int = 0


class UsageSummaryResponse(BaseModel):
    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    avg_latency_ms: int = 0


# ── Endpoints ────────────────────────────────────────────────

@router.get("")
@traced("models.list")
async def list_models(
    auth: AuthContext = Depends(get_current_user),
    model_type: Optional[str] = None,
):
    """List registered AI models."""
    from src.agents.nexus_model_layer import model_manager

    models = await model_manager.list_models(auth.tenant_id)
    if model_type:
        models = [m for m in models if m.model_type.value == model_type]
    return [{"id": m.id, "name": m.name, "provider": m.provider.value,
             "model_type": m.model_type.value, "model_id_string": m.model_id_string,
             "is_local": m.is_local} for m in models]


@router.post("", status_code=201)
@traced("models.register")
async def register_model(
    data: ModelRegister,
    auth: AuthContext = Depends(get_current_user),
):
    """Register a new AI model."""
    auth.require_role("admin")
    from src.infra.nexus_data_persist import BaseRepository

    repo = BaseRepository("ai_models")
    result = await repo.create(
        data=data.model_dump(),
        tenant_id=auth.tenant_id,
    )
    return result


@router.post("/credentials", status_code=201)
@traced("models.store_credential")
async def store_credential(
    data: CredentialStore,
    auth: AuthContext = Depends(get_current_user),
):
    """Store an encrypted API credential."""
    auth.require_role("admin")
    from src.infra.nexus_vault_keys import encrypt_credential
    from src.infra.nexus_data_persist import BaseRepository

    encrypted = encrypt_credential(data.api_key)
    prefix = data.api_key[:4] + "..."

    repo = BaseRepository("ai_credentials")
    result = await repo.create(
        data={
            "provider": data.provider,
            "credential_name": data.credential_name,
            "encrypted_key": encrypted,
            "key_prefix": prefix,
        },
        tenant_id=auth.tenant_id,
    )

    return {"id": result["id"], "provider": data.provider, "key_prefix": prefix}


@router.post("/defaults", status_code=201)
@traced("models.set_default")
async def set_default_model(
    data: DefaultModelSet,
    auth: AuthContext = Depends(get_current_user),
):
    """Set a model as default for a task type."""
    auth.require_role("admin")
    from src.infra.nexus_data_persist import BaseRepository

    repo = BaseRepository("default_models")
    result = await repo.create(
        data={
            "task_type": data.task_type,
            "model_id": data.model_id,
            "priority": data.priority,
        },
        tenant_id=auth.tenant_id,
    )
    return result


@router.get("/usage/summary")
@traced("models.usage_summary")
async def usage_summary(
    auth: AuthContext = Depends(get_current_user),
    period_days: int = 30,
):
    """Get AI usage summary for the current tenant."""
    from src.infra.nexus_cost_tracker import cost_tracker

    summary = await cost_tracker.get_usage_summary(
        auth.tenant_id,
        user_id=auth.user_id if not auth.is_admin else None,
        period_days=period_days,
    )
    return summary


@router.get("/usage/budget")
@traced("models.budget_check")
async def budget_check(
    auth: AuthContext = Depends(get_current_user),
):
    """Check current budget status."""
    from src.infra.nexus_cost_tracker import cost_tracker

    return await cost_tracker.check_budget(auth.tenant_id, auth.user_id)
