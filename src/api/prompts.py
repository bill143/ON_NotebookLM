"""
Prompt Management API — Feature 14: Prompt Registry, Versioning, Testing
Codename: ESPERANTO
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.infra.nexus_vault_keys import AuthContext, get_current_user

router = APIRouter(prefix="/prompts", tags=["Prompt Registry"])


# ── Schemas ──────────────────────────────────────────────────


class PromptCreate(BaseModel):
    namespace: str = Field(description="e.g., 'chat', 'research', 'podcast'")
    name: str = Field(description="e.g., 'system', 'grounding'")
    content: str
    variables: list[str] = Field(default_factory=list)
    model_target: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    changelog: str = ""


class PromptResponse(BaseModel):
    id: str
    namespace: str
    name: str
    version: str
    content: str
    variables: list[str]
    model_target: str | None
    status: str  # "draft", "active", "deprecated"
    created_by: str | None
    created_at: str
    avg_latency_ms: float | None = None
    avg_token_cost: float | None = None


class PromptVersionHistory(BaseModel):
    version: str
    status: str
    changelog: str
    created_at: str
    created_by: str | None


class PromptTestCase(BaseModel):
    input_variables: dict[str, str]
    expected_criteria: dict[str, Any]
    pass_threshold: float = 0.8


class PromptTestResult(BaseModel):
    test_case_id: str
    passed: bool
    score: float
    details: str


class PromptRollbackRequest(BaseModel):
    target_version: str


# ── Endpoints ────────────────────────────────────────────────


@router.get("")
async def list_prompts(
    namespace: str | None = Query(default=None),
    status: str = Query(default="active"),
    auth: AuthContext = Depends(get_current_user),
) -> list[PromptResponse]:
    """List prompts, optionally filtered by namespace and status."""
    auth.require_role("admin")
    from src.infra.nexus_prompt_registry import prompt_registry

    prompts = await prompt_registry.list_prompts(
        namespace=namespace,
        status=status,
    )
    return [PromptResponse(**p) for p in prompts]


@router.post("")
async def create_prompt(
    data: PromptCreate,
    auth: AuthContext = Depends(get_current_user),
) -> PromptResponse:
    """Create a new prompt version."""
    auth.require_role("admin")
    from src.infra.nexus_prompt_registry import prompt_registry

    prompt = await prompt_registry.create_version(
        namespace=data.namespace,
        name=data.name,
        content=data.content,
        variables=data.variables,
        model_target=data.model_target,
        max_tokens=data.max_tokens,
        temperature=data.temperature,
        changelog=data.changelog,
        created_by=auth.user_id,
    )
    return PromptResponse(**prompt)


@router.get("/{namespace}/{name}")
async def get_prompt(
    namespace: str,
    name: str,
    version: str | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
) -> PromptResponse:
    """Get a specific prompt (latest or specific version)."""
    auth.require_role("admin")
    from src.infra.nexus_prompt_registry import prompt_registry

    ref = f"{namespace}/{name}"
    if version:
        ref = f"{ref}@{version}"

    await prompt_registry.resolve(ref)
    prompt = await prompt_registry.get_prompt_metadata(namespace, name, version)
    return PromptResponse(**prompt)


@router.get("/{namespace}/{name}/versions")
async def list_versions(
    namespace: str,
    name: str,
    auth: AuthContext = Depends(get_current_user),
) -> list[PromptVersionHistory]:
    """Get version history for a prompt."""
    auth.require_role("admin")
    from src.infra.nexus_prompt_registry import prompt_registry

    versions = await prompt_registry.list_versions(namespace, name)
    return [PromptVersionHistory(**v) for v in versions]


@router.post("/{namespace}/{name}/rollback")
async def rollback_prompt(
    namespace: str,
    name: str,
    data: PromptRollbackRequest,
    auth: AuthContext = Depends(get_current_user),
) -> PromptResponse:
    """Rollback a prompt to a previous version."""
    auth.require_role("admin")
    from src.infra.nexus_prompt_registry import prompt_registry

    prompt = await prompt_registry.rollback(
        namespace=namespace,
        name=name,
        target_version=data.target_version,
        rolled_back_by=auth.user_id,
    )
    return PromptResponse(**prompt)


@router.post("/{namespace}/{name}/test")
async def test_prompt(
    namespace: str,
    name: str,
    test_cases: list[PromptTestCase],
    auth: AuthContext = Depends(get_current_user),
) -> list[PromptTestResult]:
    """Run test cases against a prompt version."""
    auth.require_role("admin")
    from src.infra.nexus_prompt_registry import prompt_registry

    results = await prompt_registry.run_tests(
        namespace=namespace,
        name=name,
        test_cases=[tc.model_dump() for tc in test_cases],
    )
    return [PromptTestResult(**r) for r in results]


@router.get("/{namespace}/{name}/performance")
async def get_prompt_performance(
    namespace: str,
    name: str,
    days: int = Query(default=7, ge=1, le=90),
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Get prompt performance metrics."""
    auth.require_role("admin")
    from src.infra.nexus_prompt_registry import prompt_registry

    return await prompt_registry.get_performance(
        namespace=namespace,
        name=name,
        days=days,
    )
