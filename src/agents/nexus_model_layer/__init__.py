"""
Nexus Model Layer — Feature 15C: Provider-Agnostic Model Abstraction (ADR-1)
Codename: ESPERANTO

This is THE foundational module. All AI features (1-5) flow through this layer.
No agent calls a provider directly. Every AI call:
  1. Resolves model config from DB (ModelManager)
  2. Injects credentials from vault
  3. Routes to the correct provider via AIFactory
  4. Records usage metrics via CostTracker integration

Source patterns:
  - Repo #7: Esperanto AIFactory (create_language, create_embedding, create_tts, create_stt)
  - Repo #7: ModelManager with DB-backed config and DefaultModels fallback
  - Repo #7: Credential management with per-model linking
  - Repo #9: LLMBackend with Gemini/LiteLLM switching
  - Repo #1: OpenAI-compatible local endpoints (ADR-7)
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, AsyncIterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, cast

from loguru import logger

from src.exceptions import (
    ModelNotFoundError,
    ProviderAuthError,
    ProviderTimeoutError,
    RateLimitError,
    classify_error,
)

# ── Enums ────────────────────────────────────────────────────


class ModelType(str, Enum):
    CHAT = "chat"
    EMBEDDING = "embedding"
    TTS = "tts"
    STT = "stt"
    VISION = "vision"
    RERANKER = "reranker"


class Provider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"
    ELEVENLABS = "elevenlabs"
    EDGE_TTS = "edge_tts"
    KOKORO = "kokoro"
    LITELLM = "litellm"


# ── Data Classes ─────────────────────────────────────────────


@dataclass
class ModelConfig:
    """Configuration for a registered AI model."""

    id: str
    name: str
    provider: Provider
    model_type: ModelType
    model_id_string: str  # e.g. "gpt-4o", "claude-3-opus", "llama3.1:8b"
    is_local: bool = False
    base_url: str | None = None
    max_tokens: int = 4096
    supports_streaming: bool = True
    supports_function_calling: bool = False
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class AIResponse:
    """Standardized response from any AI provider."""

    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    finish_reason: str = "stop"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddingResponse:
    """Standardized embedding response."""

    embeddings: list[list[float]]
    model: str
    provider: str
    token_count: int = 0
    latency_ms: float = 0.0


@dataclass
class TTSResponse:
    """Standardized TTS response."""

    audio_data: bytes
    model: str
    provider: str
    format: str = "mp3"
    duration_seconds: float = 0.0
    latency_ms: float = 0.0


# ── Abstract Provider Interface ──────────────────────────────


class BaseLLMProvider(ABC):
    """Abstract interface for language model providers."""

    def __init__(self, config: ModelConfig, api_key: str | None = None) -> None:
        self.config = config
        self.api_key = api_key

    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
        stop: list[str] | None = None,
        response_format: dict | None = None,
    ) -> AIResponse:
        """Generate a completion from messages."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """Stream a completion token by token."""
        ...


class BaseEmbeddingProvider(ABC):
    """Abstract interface for embedding providers."""

    def __init__(self, config: ModelConfig, api_key: str | None = None) -> None:
        self.config = config
        self.api_key = api_key

    @abstractmethod
    async def embed(self, texts: list[str]) -> EmbeddingResponse:
        """Generate embeddings for a list of texts."""
        ...


class BaseTTSProvider(ABC):
    """Abstract interface for TTS providers (ADR-4)."""

    def __init__(self, config: ModelConfig, api_key: str | None = None) -> None:
        self.config = config
        self.api_key = api_key

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        *,
        voice: str = "default",
        speed: float = 1.0,
        audio_format: str = "mp3",
    ) -> TTSResponse:
        """Synthesize speech from text."""
        ...


# ── Concrete Providers ───────────────────────────────────────


class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT provider (also handles Ollama via OpenAI-compatible API — ADR-7)."""

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
        stop: list[str] | None = None,
        response_format: dict | None = None,
    ) -> AIResponse:
        import openai

        client = openai.AsyncOpenAI(
            api_key=self.api_key or "not-needed",
            base_url=self.config.base_url,
        )

        start = time.perf_counter()
        try:
            kwargs: dict[str, Any] = {
                "model": self.config.model_id_string,
                "messages": cast(Any, messages),
                "max_tokens": max_tokens or self.config.max_tokens,
                "temperature": temperature,
            }
            if stop:
                kwargs["stop"] = stop
            if response_format:
                kwargs["response_format"] = response_format

            response = await client.chat.completions.create(**kwargs)
            latency = (time.perf_counter() - start) * 1000

            choice = response.choices[0]
            usage = response.usage

            return AIResponse(
                content=choice.message.content or "",
                model=self.config.model_id_string,
                provider=self.config.provider.value,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                cached_tokens=getattr(usage, "cached_tokens", 0) if usage else 0,
                latency_ms=latency,
                cost_usd=self._calculate_cost(usage),
                finish_reason=choice.finish_reason or "stop",
            )
        except openai.RateLimitError as e:
            raise RateLimitError(str(e), original_error=e) from e
        except openai.AuthenticationError as e:
            raise ProviderAuthError(str(e), original_error=e) from e
        except openai.APITimeoutError as e:
            raise ProviderTimeoutError(str(e), original_error=e) from e
        except Exception as e:
            error_cls, err_msg = classify_error(e)
            raise error_cls(err_msg, original_error=e) from e

    async def stream(  # type: ignore[override]  # async generator vs ABC async method typing
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        import openai

        client = openai.AsyncOpenAI(
            api_key=self.api_key or "not-needed",
            base_url=self.config.base_url,
        )

        response = await client.chat.completions.create(
            model=self.config.model_id_string,
            messages=cast(Any, messages),
            max_tokens=max_tokens or self.config.max_tokens,
            temperature=temperature,
            stream=True,
        )

        async for chunk in cast(AsyncIterable[Any], response):
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def _calculate_cost(self, usage: Any) -> float:
        if not usage:
            return 0.0
        input_cost = (usage.prompt_tokens / 1000) * self.config.cost_per_1k_input
        output_cost = (usage.completion_tokens / 1000) * self.config.cost_per_1k_output
        return float(round(input_cost + output_cost, 6))


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude provider."""

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
        stop: list[str] | None = None,
        response_format: dict | None = None,
    ) -> AIResponse:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self.api_key)

        # Extract system message
        system_msg = ""
        chat_messages = []
        for message in messages:
            if message["role"] == "system":
                system_msg = message["content"]
            else:
                chat_messages.append(message)

        start = time.perf_counter()
        try:
            kwargs: dict[str, Any] = {
                "model": self.config.model_id_string,
                "messages": chat_messages,
                "max_tokens": max_tokens or self.config.max_tokens,
                "temperature": temperature,
            }
            if system_msg:
                kwargs["system"] = system_msg
            if stop:
                kwargs["stop_sequences"] = stop

            response = await client.messages.create(**kwargs)
            latency = (time.perf_counter() - start) * 1000

            content = ""
            for block in response.content:
                if hasattr(block, "text"):
                    content += block.text

            return AIResponse(
                content=content,
                model=self.config.model_id_string,
                provider="anthropic",
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                latency_ms=latency,
                cost_usd=self._calculate_cost(response.usage),
                finish_reason=response.stop_reason or "stop",
            )
        except anthropic.RateLimitError as e:
            raise RateLimitError(str(e), original_error=e) from e
        except anthropic.AuthenticationError as e:
            raise ProviderAuthError(str(e), original_error=e) from e
        except Exception as e:
            error_cls, err_msg = classify_error(e)
            raise error_cls(err_msg, original_error=e) from e

    async def stream(  # type: ignore[override]  # async generator vs ABC async method typing
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self.api_key)

        system_msg = ""
        chat_messages = []
        for message in messages:
            if message["role"] == "system":
                system_msg = message["content"]
            else:
                chat_messages.append(message)

        kwargs: dict[str, Any] = {
            "model": self.config.model_id_string,
            "messages": chat_messages,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature,
        }
        if system_msg:
            kwargs["system"] = system_msg

        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    def _calculate_cost(self, usage: Any) -> float:
        input_cost = (usage.input_tokens / 1000) * self.config.cost_per_1k_input
        output_cost = (usage.output_tokens / 1000) * self.config.cost_per_1k_output
        return float(round(input_cost + output_cost, 6))


class GoogleProvider(BaseLLMProvider):
    """Google Gemini provider."""

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
        stop: list[str] | None = None,
        response_format: dict | None = None,
    ) -> AIResponse:
        from google import genai

        client = genai.Client(api_key=self.api_key)

        # Convert messages to Gemini format
        system_instruction = None
        contents = []
        for message in messages:
            if message["role"] == "system":
                system_instruction = message["content"]
            else:
                role = "user" if message["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": message["content"]}]})

        start = time.perf_counter()
        try:
            gen_config: dict[str, Any] = {
                "max_output_tokens": max_tokens or self.config.max_tokens,
                "temperature": temperature,
            }
            if stop:
                gen_config["stop_sequences"] = stop
            if system_instruction:
                gen_config["system_instruction"] = system_instruction

            response = await client.aio.models.generate_content(
                model=self.config.model_id_string,
                contents=cast(Any, contents),
                config=cast(Any, gen_config),
            )
            latency = (time.perf_counter() - start) * 1000

            usage_meta = getattr(response, "usage_metadata", None)

            return AIResponse(
                content=response.text or "",
                model=self.config.model_id_string,
                provider="google",
                input_tokens=getattr(usage_meta, "prompt_token_count", 0) if usage_meta else 0,
                output_tokens=getattr(usage_meta, "candidates_token_count", 0) if usage_meta else 0,
                latency_ms=latency,
                finish_reason="stop",
            )
        except Exception as e:
            error_cls, err_msg = classify_error(e)
            raise error_cls(err_msg, original_error=e) from e

    async def stream(  # type: ignore[override]  # async generator vs ABC async method typing
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        from google import genai

        client = genai.Client(api_key=self.api_key)

        system_instruction = None
        contents = []
        for message in messages:
            if message["role"] == "system":
                system_instruction = message["content"]
            else:
                role = "user" if message["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": message["content"]}]})

        stream_config: dict[str, Any] = {
            "max_output_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature,
        }
        if system_instruction:
            stream_config["system_instruction"] = system_instruction

        async for chunk in await client.aio.models.generate_content_stream(
            model=self.config.model_id_string,
            contents=cast(Any, contents),
            config=cast(Any, stream_config),
        ):
            if chunk.text:
                yield chunk.text


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """OpenAI / Ollama embedding provider."""

    async def embed(self, texts: list[str]) -> EmbeddingResponse:
        import openai

        client = openai.AsyncOpenAI(
            api_key=self.api_key or "not-needed",
            base_url=self.config.base_url,
        )

        start = time.perf_counter()
        response = await client.embeddings.create(
            model=self.config.model_id_string,
            input=texts,
        )
        latency = (time.perf_counter() - start) * 1000

        embeddings = [item.embedding for item in response.data]
        token_count = response.usage.total_tokens if response.usage else 0

        return EmbeddingResponse(
            embeddings=embeddings,
            model=self.config.model_id_string,
            provider=self.config.provider.value,
            token_count=token_count,
            latency_ms=latency,
        )


class OpenAITTSProvider(BaseTTSProvider):
    """OpenAI / Kokoro TTS provider (ADR-7 — same interface for local and cloud)."""

    async def synthesize(
        self,
        text: str,
        *,
        voice: str = "alloy",
        speed: float = 1.0,
        audio_format: str = "mp3",
    ) -> TTSResponse:
        import openai

        client = openai.AsyncOpenAI(
            api_key=self.api_key or "not-needed",
            base_url=self.config.base_url,
        )

        start = time.perf_counter()
        response = await client.audio.speech.create(
            model=self.config.model_id_string,
            voice=voice,
            input=text,
            speed=speed,
            response_format=cast(Any, audio_format),
        )
        latency = (time.perf_counter() - start) * 1000

        audio_data = response.content

        return TTSResponse(
            audio_data=audio_data,
            model=self.config.model_id_string,
            provider=self.config.provider.value,
            format=audio_format,
            latency_ms=latency,
        )


# ── AI Factory (The Esperanto Pattern) ───────────────────────


class AIFactory:
    """
    Provider-agnostic AI model factory.

    Source: Repo #7 — esperanto.AIFactory pattern
    Maps Provider enum → concrete provider class.
    Single point of provider instantiation for the entire application.
    """

    _llm_providers: dict[Provider, type[BaseLLMProvider]] = {
        Provider.OPENAI: OpenAIProvider,
        Provider.OLLAMA: OpenAIProvider,  # Same interface, different base_url (ADR-7)
        Provider.ANTHROPIC: AnthropicProvider,
        Provider.GOOGLE: GoogleProvider,
    }

    _embedding_providers: dict[Provider, type[BaseEmbeddingProvider]] = {
        Provider.OPENAI: OpenAIEmbeddingProvider,
        Provider.OLLAMA: OpenAIEmbeddingProvider,
    }

    _tts_providers: dict[Provider, type[BaseTTSProvider]] = {
        Provider.OPENAI: OpenAITTSProvider,
        Provider.KOKORO: OpenAITTSProvider,  # Kokoro exposes OpenAI-compatible API (ADR-7)
    }

    @classmethod
    def create_llm(cls, config: ModelConfig, api_key: str | None = None) -> BaseLLMProvider:
        """Create a language model provider instance."""
        provider_cls = cls._llm_providers.get(config.provider)
        if not provider_cls:
            raise ModelNotFoundError(
                f"No LLM provider implementation for '{config.provider.value}'"
            )
        return provider_cls(config, api_key)

    @classmethod
    def create_embedding(
        cls, config: ModelConfig, api_key: str | None = None
    ) -> BaseEmbeddingProvider:
        """Create an embedding provider instance."""
        provider_cls = cls._embedding_providers.get(config.provider)
        if not provider_cls:
            raise ModelNotFoundError(f"No embedding provider for '{config.provider.value}'")
        return provider_cls(config, api_key)

    @classmethod
    def create_tts(cls, config: ModelConfig, api_key: str | None = None) -> BaseTTSProvider:
        """Create a TTS provider instance."""
        provider_cls = cls._tts_providers.get(config.provider)
        if not provider_cls:
            raise ModelNotFoundError(f"No TTS provider for '{config.provider.value}'")
        return provider_cls(config, api_key)


# ── Model Manager ────────────────────────────────────────────


class ModelManager:
    """
    Database-backed model registration, credential injection, and provisioning.

    Source: Repo #7, open_notebook/ai/models.py — ModelManager pattern
    - Models registered in DB (ai_models table)
    - Credentials stored encrypted (ai_credentials table)
    - DefaultModels for per-task fallback chain
    - Credential injection at provision time
    """

    def __init__(self) -> None:
        from src.infra import nexus_data_persist as db

        self._db = db

    async def get_model(self, model_id: str, tenant_id: str | None = None) -> ModelConfig:
        """Retrieve a registered model configuration."""
        repo = self._db.BaseRepository("ai_models")
        data = await repo.get_by_id(model_id, tenant_id)
        if not data:
            raise ModelNotFoundError(f"Model '{model_id}' not found")
        return self._to_config(data)

    async def list_models(
        self,
        tenant_id: str | None = None,
        model_type: ModelType | None = None,
    ) -> list[ModelConfig]:
        """List available models, optionally filtered by type."""
        repo = self._db.BaseRepository("ai_models")
        filters: dict[str, Any] = {"is_active": True}
        if model_type:
            filters["model_type"] = model_type.value
        rows = await repo.list_all(tenant_id, filters=filters)
        return [self._to_config(row) for row in rows]

    async def get_default_model(
        self,
        task_type: str,
        tenant_id: str | None = None,
    ) -> ModelConfig:
        """
        Get the default model for a task type with fallback chain.

        Fallback: task-specific → chat → first available
        Source: Repo #7, ModelManager.get_defaults()
        """
        from src.infra import nexus_data_persist as db

        query = """
            SELECT am.* FROM default_models dm
            JOIN ai_models am ON dm.model_id = am.id AND am.is_active = true
            WHERE dm.task_type = :task_type
        """
        params: dict[str, Any] = {"task_type": task_type}

        if tenant_id:
            query += " AND (dm.tenant_id = :tenant_id OR dm.tenant_id IS NULL)"
            params["tenant_id"] = tenant_id
        else:
            query += " AND dm.tenant_id IS NULL"

        query += " ORDER BY dm.priority ASC LIMIT 1"

        async with db.get_session(tenant_id) as session:
            from sqlalchemy import text

            result = await session.execute(text(query), params)
            row = result.mappings().first()

        if row:
            return self._to_config(dict(row))

        # Fallback to 'chat' default
        if task_type != "chat":
            logger.warning(
                f"No default model for '{task_type}', falling back to 'chat'",
                task_type=task_type,
            )
            return await self.get_default_model("chat", tenant_id)

        raise ModelNotFoundError(f"No default model configured for task type '{task_type}'")

    async def get_credential(
        self,
        provider: str,
        tenant_id: str | None = None,
    ) -> str | None:
        """Retrieve decrypted API key for a provider."""
        from src.infra import nexus_data_persist as db
        from src.infra.nexus_vault_keys import decrypt_credential

        query = """
            SELECT encrypted_key, argon2_salt FROM ai_credentials
            WHERE provider = :provider AND is_active = true
        """
        params: dict[str, Any] = {"provider": provider}

        if tenant_id:
            query += " AND (tenant_id = :tenant_id OR tenant_id IS NULL)"
            params["tenant_id"] = tenant_id
        else:
            query += " AND tenant_id IS NULL"

        query += " ORDER BY tenant_id DESC NULLS LAST LIMIT 1"

        async with db.get_session(tenant_id) as session:
            from sqlalchemy import text

            result = await session.execute(text(query), params)
            row = result.mappings().first()

        if row:
            salt = row.get("argon2_salt")
            return decrypt_credential(row["encrypted_key"], salt=salt)
        return None

    async def provision_llm(
        self,
        model_id: str | None = None,
        task_type: str = "chat",
        tenant_id: str | None = None,
    ) -> BaseLLMProvider:
        """
        Provision a ready-to-use LLM provider.

        1. Resolve model config (by ID or default for task)
        2. Inject credential from vault
        3. Create provider via AIFactory
        """
        if model_id:
            config = await self.get_model(model_id, tenant_id)
        else:
            config = await self.get_default_model(task_type, tenant_id)

        api_key = await self.get_credential(config.provider.value, tenant_id)

        logger.debug(
            "Provisioned LLM",
            model=config.model_id_string,
            provider=config.provider.value,
            task_type=task_type,
        )

        return AIFactory.create_llm(config, api_key)

    async def provision_embedding(
        self,
        model_id: str | None = None,
        tenant_id: str | None = None,
    ) -> BaseEmbeddingProvider:
        """Provision a ready-to-use embedding provider."""
        if model_id:
            config = await self.get_model(model_id, tenant_id)
        else:
            config = await self.get_default_model("embedding", tenant_id)

        api_key = await self.get_credential(config.provider.value, tenant_id)
        return AIFactory.create_embedding(config, api_key)

    async def provision_tts(
        self,
        model_id: str | None = None,
        tenant_id: str | None = None,
    ) -> BaseTTSProvider:
        """Provision a ready-to-use TTS provider."""
        if model_id:
            config = await self.get_model(model_id, tenant_id)
        else:
            config = await self.get_default_model("tts", tenant_id)

        api_key = await self.get_credential(config.provider.value, tenant_id)
        return AIFactory.create_tts(config, api_key)

    def _to_config(self, data: dict[str, Any]) -> ModelConfig:
        """Convert a DB row to ModelConfig."""
        return ModelConfig(
            id=str(data["id"]),
            name=data.get("name", ""),
            provider=Provider(data["provider"]),
            model_type=ModelType(data["model_type"]),
            model_id_string=data.get("model_id_string", ""),
            is_local=data.get("is_local", False),
            base_url=data.get("base_url"),
            max_tokens=data.get("max_tokens", 4096),
            supports_streaming=data.get("supports_streaming", True),
            supports_function_calling=data.get("supports_function_calling", False),
            cost_per_1k_input=float(data.get("cost_per_1k_input", 0)),
            cost_per_1k_output=float(data.get("cost_per_1k_output", 0)),
            config=data.get("config", {}),
        )


# ── Global Model Manager ────────────────────────────────────

model_manager = ModelManager()
