"""
Nexus Model Seeding — Register Default AI Models & Prompt Versions
Codename: ESPERANTO

Populates the ai_models and prompt_versions tables with initial data.
Uses synchronous psycopg2 for simplicity — no async app infrastructure needed.

Usage:
    python -m database.seeds.seed_models
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

# ── Default Model Registry ───────────────────────────────────

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

DEFAULT_PROMPT_VERSIONS = [
    {
        "name": "default_chat",
        "namespace": "default",
        "version": "1.0.0",
        "content": (
            "You are a helpful AI assistant. Answer questions clearly and concisely "
            "based on the provided context."
        ),
    },
    {
        "name": "default_summarization",
        "namespace": "default",
        "version": "1.0.0",
        "content": (
            "You are an expert summarizer. Create a clear, comprehensive summary of the "
            "provided content, highlighting the key points and main ideas."
        ),
    },
    {
        "name": "default_quiz_generation",
        "namespace": "default",
        "version": "1.0.0",
        "content": (
            "You are an expert educator. Generate thoughtful quiz questions with multiple "
            "choice answers based on the provided content. Each question should test "
            "understanding of key concepts."
        ),
    },
    {
        "name": "default_flashcard_generation",
        "namespace": "default",
        "version": "1.0.0",
        "content": (
            "You are an expert at creating educational flashcards. Generate concise "
            "question-and-answer flashcard pairs from the provided content to aid memorization."
        ),
    },
]


# ── Seeding Functions ────────────────────────────────────────

def _get_connection():
    """Get a synchronous database connection."""
    import psycopg2
    import psycopg2.extras

    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://nexus:nexus_dev_password@localhost:5432/nexus_notebook_11",
    )
    # Convert asyncpg URL to psycopg2 format
    dsn = database_url.replace("postgresql+asyncpg://", "postgresql://")
    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


def seed_models() -> dict[str, int]:
    """Seed the database with default AI models using synchronous psycopg2."""
    import psycopg2.extras

    conn = _get_connection()
    model_id_map: dict[str, str] = {}
    created = 0
    skipped = 0

    try:
        with conn.cursor() as cur:
            for model in DEFAULT_MODELS:
                # Check if model already exists (idempotent)
                cur.execute(
                    """
                    SELECT id FROM ai_models
                    WHERE model_id_string = %s AND provider = %s
                    LIMIT 1
                    """,
                    (model["model_id_string"], model["provider"]),
                )
                existing = cur.fetchone()

                if existing:
                    model_id_map[model["name"]] = str(existing["id"])
                    skipped += 1
                    print(f"  [skip] {model['name']} already exists")
                    continue

                model_id = str(uuid.uuid4())
                model_id_map[model["name"]] = model_id
                now = datetime.now(timezone.utc)

                cur.execute(
                    """
                    INSERT INTO ai_models (
                        id, name, provider, model_type, model_id_string,
                        is_local, base_url, max_tokens, supports_streaming,
                        supports_function_calling, cost_per_1k_input, cost_per_1k_output,
                        is_active, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        true, %s, %s
                    )
                    """,
                    (
                        model_id,
                        model["name"],
                        model["provider"],
                        model["model_type"],
                        model["model_id_string"],
                        model.get("is_local", False),
                        model.get("base_url"),
                        model.get("max_tokens", 4096),
                        model.get("supports_streaming", True),
                        model.get("supports_function_calling", False),
                        model.get("cost_per_1k_input", 0),
                        model.get("cost_per_1k_output", 0),
                        now,
                        now,
                    ),
                )
                created += 1
                print(f"  [ok]   {model['name']} ({model['provider']}/{model['model_id_string']})")

        # Seed default task→model mappings
        defaults_created = 0
        with conn.cursor() as cur:
            for mapping in DEFAULT_TASK_MODELS:
                model_id = model_id_map.get(mapping["model_name"])
                if not model_id:
                    print(f"  [warn] Model not found for default: {mapping['model_name']}")
                    continue

                # Check if mapping already exists (NULL tenant_id = global)
                cur.execute(
                    """
                    SELECT id FROM default_models
                    WHERE tenant_id IS NULL
                      AND task_type = %s
                      AND priority = %s
                    LIMIT 1
                    """,
                    (mapping["task_type"], mapping["priority"]),
                )
                if cur.fetchone():
                    continue

                now = datetime.now(timezone.utc)
                cur.execute(
                    """
                    INSERT INTO default_models (id, task_type, model_id, priority, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()),
                        mapping["task_type"],
                        model_id,
                        mapping["priority"],
                        now,
                    ),
                )
                defaults_created += 1

        conn.commit()

    finally:
        conn.close()

    summary = {
        "models_created": created,
        "models_skipped": skipped,
        "defaults_created": defaults_created,
        "total_models": len(DEFAULT_MODELS),
    }
    return summary


def seed_prompt_versions() -> int:
    """Seed the database with default prompt versions."""
    conn = _get_connection()
    created = 0

    try:
        with conn.cursor() as cur:
            for prompt in DEFAULT_PROMPT_VERSIONS:
                now = datetime.now(timezone.utc)
                cur.execute(
                    """
                    INSERT INTO prompt_versions (id, name, namespace, version, content, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, 'active', %s)
                    ON CONFLICT (namespace, name, version) DO NOTHING
                    """,
                    (
                        str(uuid.uuid4()),
                        prompt["name"],
                        prompt["namespace"],
                        prompt["version"],
                        prompt["content"],
                        now,
                    ),
                )
                if cur.rowcount:
                    created += 1
                    print(f"  [ok]   prompt {prompt['namespace']}/{prompt['name']} v{prompt['version']}")
                else:
                    print(f"  [skip] prompt {prompt['namespace']}/{prompt['name']} already exists")

        conn.commit()

    finally:
        conn.close()

    return created


# ── CLI Entry Point ──────────────────────────────────────────

def main() -> None:
    """Seed all defaults."""
    print("=" * 60)
    print("Nexus Notebook 11 LM — Model Seeding")
    print("=" * 60)

    print("\nSeeding AI models...")
    result = seed_models()
    print(
        f"\nModels: {result['models_created']} created, "
        f"{result['models_skipped']} skipped"
    )
    print(f"Defaults: {result['defaults_created']} task→model mappings created")

    print("\nSeeding prompt versions...")
    prompts_created = seed_prompt_versions()
    print(f"Prompts: {prompts_created} created")

    print("\n" + "=" * 60)
    print("Seeding complete!")


if __name__ == "__main__":
    main()
