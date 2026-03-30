"""
Nexus Model Seeding — Register Default AI Models & Credentials
Codename: ESPERANTO

Run this script to populate the ai_models and default_models tables
with the production model registry defined in the forensic analysis.

Usage:
    python -m database.seeds.seed_models
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone

from loguru import logger


# ── Default Model Registry ───────────────────────────────────
# Source: Forensic Analysis Section 4, AI Model Registry

DEFAULT_MODELS = [
    # ─── Chat / LLM Models ──────────────────────────────
    {
        "name": "GPT-4o",
        "provider": "openai",
        "model_type": "chat",
        "model_id_string": "gpt-4o",
        "is_local": False,
        "max_tokens": 4096,
        "supports_streaming": True,
        "supports_function_calling": True,
        "cost_per_1k_input": 0.005,
        "cost_per_1k_output": 0.015,
    },
    {
        "name": "GPT-4o Mini",
        "provider": "openai",
        "model_type": "chat",
        "model_id_string": "gpt-4o-mini",
        "is_local": False,
        "max_tokens": 4096,
        "supports_streaming": True,
        "supports_function_calling": True,
        "cost_per_1k_input": 0.00015,
        "cost_per_1k_output": 0.0006,
    },
    {
        "name": "Claude 3.5 Sonnet",
        "provider": "anthropic",
        "model_type": "chat",
        "model_id_string": "claude-3-5-sonnet-20241022",
        "is_local": False,
        "max_tokens": 8192,
        "supports_streaming": True,
        "supports_function_calling": True,
        "cost_per_1k_input": 0.003,
        "cost_per_1k_output": 0.015,
    },
    {
        "name": "Claude 3.5 Haiku",
        "provider": "anthropic",
        "model_type": "chat",
        "model_id_string": "claude-3-5-haiku-20241022",
        "is_local": False,
        "max_tokens": 8192,
        "supports_streaming": True,
        "supports_function_calling": True,
        "cost_per_1k_input": 0.001,
        "cost_per_1k_output": 0.005,
    },
    {
        "name": "Gemini 2.0 Flash",
        "provider": "google",
        "model_type": "chat",
        "model_id_string": "gemini-2.0-flash",
        "is_local": False,
        "max_tokens": 8192,
        "supports_streaming": True,
        "supports_function_calling": True,
        "cost_per_1k_input": 0.0001,
        "cost_per_1k_output": 0.0004,
    },
    {
        "name": "Gemini 1.5 Pro",
        "provider": "google",
        "model_type": "chat",
        "model_id_string": "gemini-1.5-pro",
        "is_local": False,
        "max_tokens": 8192,
        "supports_streaming": True,
        "supports_function_calling": True,
        "cost_per_1k_input": 0.00125,
        "cost_per_1k_output": 0.005,
    },
    # ─── Local Chat Models (ADR-7) ──────────────────────
    {
        "name": "[Local] Llama 3.1 8B",
        "provider": "ollama",
        "model_type": "chat",
        "model_id_string": "llama3.1:8b",
        "is_local": True,
        "base_url": "http://localhost:11434/v1",
        "max_tokens": 4096,
        "supports_streaming": True,
        "supports_function_calling": False,
        "cost_per_1k_input": 0.0,
        "cost_per_1k_output": 0.0,
    },
    {
        "name": "[Local] Mistral 7B",
        "provider": "ollama",
        "model_type": "chat",
        "model_id_string": "mistral:7b",
        "is_local": True,
        "base_url": "http://localhost:11434/v1",
        "max_tokens": 4096,
        "supports_streaming": True,
        "supports_function_calling": False,
        "cost_per_1k_input": 0.0,
        "cost_per_1k_output": 0.0,
    },
    {
        "name": "[Local] Qwen 2.5 7B",
        "provider": "ollama",
        "model_type": "chat",
        "model_id_string": "qwen2.5:7b",
        "is_local": True,
        "base_url": "http://localhost:11434/v1",
        "max_tokens": 4096,
        "supports_streaming": True,
        "supports_function_calling": False,
        "cost_per_1k_input": 0.0,
        "cost_per_1k_output": 0.0,
    },
    # ─── Embedding Models ───────────────────────────────
    {
        "name": "text-embedding-3-small",
        "provider": "openai",
        "model_type": "embedding",
        "model_id_string": "text-embedding-3-small",
        "is_local": False,
        "max_tokens": 8191,
        "supports_streaming": False,
        "cost_per_1k_input": 0.00002,
        "cost_per_1k_output": 0.0,
    },
    {
        "name": "text-embedding-3-large",
        "provider": "openai",
        "model_type": "embedding",
        "model_id_string": "text-embedding-3-large",
        "is_local": False,
        "max_tokens": 8191,
        "supports_streaming": False,
        "cost_per_1k_input": 0.00013,
        "cost_per_1k_output": 0.0,
    },
    {
        "name": "[Local] nomic-embed-text",
        "provider": "ollama",
        "model_type": "embedding",
        "model_id_string": "nomic-embed-text",
        "is_local": True,
        "base_url": "http://localhost:11434/v1",
        "max_tokens": 8192,
        "supports_streaming": False,
        "cost_per_1k_input": 0.0,
        "cost_per_1k_output": 0.0,
    },
    # ─── TTS Models ─────────────────────────────────────
    {
        "name": "OpenAI TTS-1",
        "provider": "openai",
        "model_type": "tts",
        "model_id_string": "tts-1",
        "is_local": False,
        "supports_streaming": False,
        "cost_per_1k_input": 0.015,
        "cost_per_1k_output": 0.0,
    },
    {
        "name": "OpenAI TTS-1 HD",
        "provider": "openai",
        "model_type": "tts",
        "model_id_string": "tts-1-hd",
        "is_local": False,
        "supports_streaming": False,
        "cost_per_1k_input": 0.030,
        "cost_per_1k_output": 0.0,
    },
    {
        "name": "[Local] Kokoro TTS",
        "provider": "kokoro",
        "model_type": "tts",
        "model_id_string": "kokoro",
        "is_local": True,
        "base_url": "http://localhost:8880",
        "supports_streaming": False,
        "cost_per_1k_input": 0.0,
        "cost_per_1k_output": 0.0,
    },
    # ─── Vision Models ──────────────────────────────────
    {
        "name": "GPT-4o Vision",
        "provider": "openai",
        "model_type": "vision",
        "model_id_string": "gpt-4o",
        "is_local": False,
        "max_tokens": 4096,
        "supports_streaming": True,
        "cost_per_1k_input": 0.005,
        "cost_per_1k_output": 0.015,
    },
    {
        "name": "Gemini 2.0 Flash Vision",
        "provider": "google",
        "model_type": "vision",
        "model_id_string": "gemini-2.0-flash",
        "is_local": False,
        "max_tokens": 8192,
        "supports_streaming": True,
        "cost_per_1k_input": 0.0001,
        "cost_per_1k_output": 0.0004,
    },
]


# ── Default Task→Model Mappings ──────────────────────────────

DEFAULT_TASK_MODELS = [
    {"task_type": "chat", "model_name": "GPT-4o Mini", "priority": 0},
    {"task_type": "chat", "model_name": "GPT-4o", "priority": 1},
    {"task_type": "research", "model_name": "Claude 3.5 Sonnet", "priority": 0},
    {"task_type": "research", "model_name": "Gemini 1.5 Pro", "priority": 1},
    {"task_type": "transformation", "model_name": "GPT-4o Mini", "priority": 0},
    {"task_type": "transformation", "model_name": "Gemini 2.0 Flash", "priority": 1},
    {"task_type": "embedding", "model_name": "text-embedding-3-small", "priority": 0},
    {"task_type": "embedding", "model_name": "text-embedding-3-large", "priority": 1},
    {"task_type": "tts", "model_name": "[Local] Kokoro TTS", "priority": 0},
    {"task_type": "tts", "model_name": "OpenAI TTS-1", "priority": 1},
    {"task_type": "vision", "model_name": "GPT-4o Vision", "priority": 0},
    {"task_type": "vision", "model_name": "Gemini 2.0 Flash Vision", "priority": 1},
]


# ── Seeding Functions ────────────────────────────────────────

async def seed_models(tenant_id: str | None = None) -> dict[str, int]:
    """Seed the database with default AI models."""
    from src.infra.nexus_data_persist import init_database, get_session
    from sqlalchemy import text

    await init_database()

    model_id_map: dict[str, str] = {}
    created = 0
    skipped = 0

    async with get_session(tenant_id) as session:
        for model in DEFAULT_MODELS:
            # Check if model already exists
            result = await session.execute(
                text("""
                    SELECT id FROM ai_models
                    WHERE model_id_string = :mid AND provider = :provider
                    LIMIT 1
                """),
                {"mid": model["model_id_string"], "provider": model["provider"]},
            )
            existing = result.mappings().first()

            if existing:
                model_id_map[model["name"]] = str(existing["id"])
                skipped += 1
                logger.debug(f"Model already exists: {model['name']}")
                continue

            model_id = str(uuid.uuid4())
            model_id_map[model["name"]] = model_id
            now = datetime.now(timezone.utc)

            await session.execute(
                text("""
                    INSERT INTO ai_models (
                        id, name, provider, model_type, model_id_string,
                        is_local, base_url, max_tokens, supports_streaming,
                        supports_function_calling, cost_per_1k_input, cost_per_1k_output,
                        is_active, created_at, updated_at
                    ) VALUES (
                        :id, :name, :provider, :model_type, :model_id_string,
                        :is_local, :base_url, :max_tokens, :supports_streaming,
                        :supports_function_calling, :cost_per_1k_input, :cost_per_1k_output,
                        true, :now, :now
                    )
                """),
                {
                    "id": model_id,
                    "name": model["name"],
                    "provider": model["provider"],
                    "model_type": model["model_type"],
                    "model_id_string": model["model_id_string"],
                    "is_local": model.get("is_local", False),
                    "base_url": model.get("base_url"),
                    "max_tokens": model.get("max_tokens", 4096),
                    "supports_streaming": model.get("supports_streaming", True),
                    "supports_function_calling": model.get("supports_function_calling", False),
                    "cost_per_1k_input": model.get("cost_per_1k_input", 0),
                    "cost_per_1k_output": model.get("cost_per_1k_output", 0),
                    "now": now,
                },
            )
            created += 1
            logger.info(f"Registered model: {model['name']} ({model['provider']}/{model['model_id_string']})")

    # Seed default task→model mappings
    defaults_created = 0
    async with get_session(tenant_id) as session:
        for mapping in DEFAULT_TASK_MODELS:
            model_id = model_id_map.get(mapping["model_name"])
            if not model_id:
                logger.warning(f"Model not found for default: {mapping['model_name']}")
                continue

            # Check if default already exists
            result = await session.execute(
                text("""
                    SELECT id FROM default_models
                    WHERE task_type = :task_type AND model_id = :model_id
                    LIMIT 1
                """),
                {"task_type": mapping["task_type"], "model_id": model_id},
            )
            if result.mappings().first():
                continue

            now = datetime.now(timezone.utc)
            await session.execute(
                text("""
                    INSERT INTO default_models (id, task_type, model_id, priority, created_at, updated_at)
                    VALUES (:id, :task_type, :model_id, :priority, :now, :now)
                """),
                {
                    "id": str(uuid.uuid4()),
                    "task_type": mapping["task_type"],
                    "model_id": model_id,
                    "priority": mapping["priority"],
                    "now": now,
                },
            )
            defaults_created += 1

    summary = {
        "models_created": created,
        "models_skipped": skipped,
        "defaults_created": defaults_created,
        "total_models": len(DEFAULT_MODELS),
    }

    logger.info(f"Model seeding complete", **summary)
    return summary


async def seed_demo_tenant() -> dict[str, str]:
    """Seed a demo tenant for development."""
    from src.infra.nexus_data_persist import get_session
    from sqlalchemy import text

    tenant_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    async with get_session() as session:
        await session.execute(
            text("""
                INSERT INTO tenants (id, name, slug, plan, settings, created_at, updated_at)
                VALUES (:id, :name, :slug, :plan, :settings, :now, :now)
                ON CONFLICT (slug) DO UPDATE SET updated_at = :now
                RETURNING id
            """),
            {
                "id": tenant_id,
                "name": "ONeill Development",
                "slug": "oneill-dev",
                "plan": "enterprise",
                "settings": '{"max_notebooks": 100, "max_sources_per_notebook": 50}',
                "now": now,
            },
        )
        # Get the actual tenant ID (might be existing)
        result = await session.execute(
            text("SELECT id FROM tenants WHERE slug = 'oneill-dev'")
        )
        row = result.mappings().first()
        if row:
            tenant_id = str(row["id"])

    logger.info(f"Demo tenant seeded: {tenant_id}")
    return {"tenant_id": tenant_id, "name": "ONeill Development", "slug": "oneill-dev"}


# ── CLI Entry Point ──────────────────────────────────────────

async def main():
    """Seed all defaults."""
    from src.infra.nexus_obs_tracing import setup_logging
    setup_logging("INFO", "text")

    logger.info("=" * 60)
    logger.info("Nexus Notebook 11 LM — Model Seeding")
    logger.info("=" * 60)

    # 1. Seed demo tenant
    tenant = await seed_demo_tenant()
    logger.info(f"Demo Tenant ID: {tenant['tenant_id']}")

    # 2. Seed models (global — no tenant)
    result = await seed_models()
    logger.info(f"Models: {result['models_created']} created, {result['models_skipped']} skipped")
    logger.info(f"Defaults: {result['defaults_created']} task→model mappings created")

    logger.info("=" * 60)
    logger.info("Seeding complete!")

    from src.infra.nexus_data_persist import close_database
    await close_database()


if __name__ == "__main__":
    asyncio.run(main())
