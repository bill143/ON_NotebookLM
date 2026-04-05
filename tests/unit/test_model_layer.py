"""
Unit Tests — Nexus Model Layer (Provider-Agnostic Model Abstraction)

Tests cover: enums, data classes, AIFactory routing, concrete providers
(with mocked SDK clients), and ModelManager initialization.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.agents.nexus_model_layer import (
    AIFactory,
    AIResponse,
    AnthropicProvider,
    BaseEmbeddingProvider,
    BaseLLMProvider,
    BaseTTSProvider,
    EmbeddingResponse,
    GoogleProvider,
    ModelConfig,
    ModelManager,
    ModelType,
    OpenAIEmbeddingProvider,
    OpenAIProvider,
    OpenAITTSProvider,
    Provider,
    TTSResponse,
)
from src.exceptions import ModelNotFoundError
from tests.mocks.ai_providers import MockAnthropicClient, MockOpenAIClient

# ── Helpers ──────────────────────────────────────────────────


def _make_config(
    provider: Provider = Provider.OPENAI,
    model_type: ModelType = ModelType.CHAT,
    model_id: str = "gpt-4o",
    **overrides,
) -> ModelConfig:
    defaults = {
        "id": "test-model-1",
        "name": "Test Model",
        "provider": provider,
        "model_type": model_type,
        "model_id_string": model_id,
    }
    defaults.update(overrides)
    return ModelConfig(**defaults)


# ── Enum Tests ───────────────────────────────────────────────


class TestProviderEnum:
    def test_provider_enum_values(self):
        expected = {
            "OPENAI": "openai",
            "ANTHROPIC": "anthropic",
            "GOOGLE": "google",
            "OLLAMA": "ollama",
            "ELEVENLABS": "elevenlabs",
            "EDGE_TTS": "edge_tts",
            "KOKORO": "kokoro",
            "LITELLM": "litellm",
        }
        for member_name, member_value in expected.items():
            assert hasattr(Provider, member_name)
            assert Provider[member_name].value == member_value

    def test_provider_is_str_enum(self):
        assert isinstance(Provider.OPENAI, str)
        assert Provider.OPENAI == "openai"


class TestModelTypeEnum:
    def test_model_type_enum_values(self):
        expected = {
            "CHAT": "chat",
            "EMBEDDING": "embedding",
            "TTS": "tts",
            "STT": "stt",
            "VISION": "vision",
            "RERANKER": "reranker",
        }
        for member_name, member_value in expected.items():
            assert hasattr(ModelType, member_name)
            assert ModelType[member_name].value == member_value


# ── Data Class Tests ─────────────────────────────────────────


class TestModelConfig:
    def test_model_config_defaults(self):
        cfg = _make_config()
        assert cfg.is_local is False
        assert cfg.base_url is None
        assert cfg.max_tokens == 4096
        assert cfg.supports_streaming is True
        assert cfg.supports_function_calling is False
        assert cfg.cost_per_1k_input == 0.0
        assert cfg.cost_per_1k_output == 0.0
        assert cfg.config == {}

    def test_model_config_custom_values(self):
        cfg = _make_config(
            is_local=True,
            base_url="http://localhost:11434/v1",
            max_tokens=2048,
            cost_per_1k_input=0.005,
        )
        assert cfg.is_local is True
        assert cfg.base_url == "http://localhost:11434/v1"
        assert cfg.max_tokens == 2048
        assert cfg.cost_per_1k_input == 0.005


class TestAIResponse:
    def test_ai_response_defaults(self):
        resp = AIResponse(content="hello", model="gpt-4o", provider="openai")
        assert resp.content == "hello"
        assert resp.input_tokens == 0
        assert resp.output_tokens == 0
        assert resp.cached_tokens == 0
        assert resp.latency_ms == 0.0
        assert resp.cost_usd == 0.0
        assert resp.finish_reason == "stop"
        assert resp.metadata == {}


class TestEmbeddingResponse:
    def test_embedding_response_fields(self):
        resp = EmbeddingResponse(
            embeddings=[[0.1, 0.2]],
            model="text-embedding-3-small",
            provider="openai",
        )
        assert resp.token_count == 0
        assert resp.latency_ms == 0.0


class TestTTSResponse:
    def test_tts_response_defaults(self):
        resp = TTSResponse(audio_data=b"audio", model="tts-1", provider="openai")
        assert resp.format == "mp3"
        assert resp.duration_seconds == 0.0
        assert resp.latency_ms == 0.0


# ── AIFactory Tests ──────────────────────────────────────────


class TestAIFactory:
    def test_ai_factory_creates_openai(self):
        cfg = _make_config(provider=Provider.OPENAI)
        provider = AIFactory.create_llm(cfg, api_key="sk-test")
        assert isinstance(provider, OpenAIProvider)
        assert isinstance(provider, BaseLLMProvider)

    def test_ai_factory_creates_anthropic(self):
        cfg = _make_config(provider=Provider.ANTHROPIC, model_id="claude-3-opus")
        provider = AIFactory.create_llm(cfg, api_key="sk-ant-test")
        assert isinstance(provider, AnthropicProvider)

    def test_ai_factory_creates_google(self):
        cfg = _make_config(provider=Provider.GOOGLE, model_id="gemini-1.5-pro")
        provider = AIFactory.create_llm(cfg, api_key="goog-test")
        assert isinstance(provider, GoogleProvider)

    def test_ai_factory_ollama_uses_openai(self):
        cfg = _make_config(
            provider=Provider.OLLAMA,
            model_id="llama3.1:8b",
            base_url="http://localhost:11434/v1",
        )
        provider = AIFactory.create_llm(cfg)
        assert isinstance(provider, OpenAIProvider)

    def test_ai_factory_raises_on_unknown(self):
        cfg = _make_config(provider=Provider.ELEVENLABS, model_id="eleven-mono")
        with pytest.raises(ModelNotFoundError, match="No LLM provider"):
            AIFactory.create_llm(cfg)

    def test_ai_factory_creates_embedding(self):
        cfg = _make_config(
            provider=Provider.OPENAI,
            model_type=ModelType.EMBEDDING,
            model_id="text-embedding-3-small",
        )
        provider = AIFactory.create_embedding(cfg, api_key="sk-test")
        assert isinstance(provider, OpenAIEmbeddingProvider)
        assert isinstance(provider, BaseEmbeddingProvider)

    def test_ai_factory_creates_tts(self):
        cfg = _make_config(
            provider=Provider.OPENAI,
            model_type=ModelType.TTS,
            model_id="tts-1",
        )
        provider = AIFactory.create_tts(cfg, api_key="sk-test")
        assert isinstance(provider, OpenAITTSProvider)
        assert isinstance(provider, BaseTTSProvider)

    def test_ai_factory_embedding_raises_on_unsupported(self):
        cfg = _make_config(provider=Provider.ANTHROPIC, model_type=ModelType.EMBEDDING)
        with pytest.raises(ModelNotFoundError, match="No embedding provider"):
            AIFactory.create_embedding(cfg)

    def test_ai_factory_tts_raises_on_unsupported(self):
        cfg = _make_config(provider=Provider.ANTHROPIC, model_type=ModelType.TTS)
        with pytest.raises(ModelNotFoundError, match="No TTS provider"):
            AIFactory.create_tts(cfg)


# ── Concrete Provider Tests ──────────────────────────────────


class TestOpenAIProviderGenerate:
    @pytest.mark.asyncio
    async def test_openai_provider_generate(self):
        cfg = _make_config(provider=Provider.OPENAI, model_id="gpt-4o")
        provider = OpenAIProvider(cfg, api_key="sk-test")

        mock_client = MockOpenAIClient()

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await provider.generate(
                [{"role": "user", "content": "Say hi"}],
                temperature=0.5,
            )

        assert isinstance(result, AIResponse)
        assert result.content == "This is a mock AI response."
        assert result.model == "gpt-4o"
        assert result.provider == "openai"
        assert result.input_tokens == 50
        assert result.output_tokens == 120
        assert result.finish_reason == "stop"
        assert result.latency_ms > 0


class TestAnthropicProviderGenerate:
    @pytest.mark.asyncio
    async def test_anthropic_provider_generate(self):
        cfg = _make_config(provider=Provider.ANTHROPIC, model_id="claude-3-5-sonnet")
        provider = AnthropicProvider(cfg, api_key="sk-ant-test")

        mock_client = MockAnthropicClient()

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            result = await provider.generate(
                [
                    {"role": "system", "content": "Be helpful."},
                    {"role": "user", "content": "Say hi"},
                ],
                temperature=0.3,
            )

        assert isinstance(result, AIResponse)
        assert result.content == "Mock Anthropic response."
        assert result.model == "claude-3-5-sonnet"
        assert result.provider == "anthropic"
        assert result.input_tokens == 40
        assert result.output_tokens == 100
        assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_anthropic_extracts_system_message(self):
        """System messages are separated and passed via the system kwarg."""
        cfg = _make_config(provider=Provider.ANTHROPIC, model_id="claude-3-5-sonnet")
        provider = AnthropicProvider(cfg, api_key="sk-ant-test")

        mock_client = MockAnthropicClient()

        with patch("anthropic.AsyncAnthropic", return_value=mock_client):
            await provider.generate(
                [
                    {"role": "system", "content": "System prompt"},
                    {"role": "user", "content": "Hello"},
                ],
            )

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs.get("system") == "System prompt"
        passed_messages = call_kwargs.kwargs["messages"]
        assert all(m["role"] != "system" for m in passed_messages)


class TestOpenAIEmbeddingProvider:
    @pytest.mark.asyncio
    async def test_embedding_provider_embed(self):
        cfg = _make_config(
            provider=Provider.OPENAI,
            model_type=ModelType.EMBEDDING,
            model_id="text-embedding-3-small",
        )
        provider = OpenAIEmbeddingProvider(cfg, api_key="sk-test")

        mock_client = MockOpenAIClient()

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await provider.embed(["Hello world"])

        assert isinstance(result, EmbeddingResponse)
        assert len(result.embeddings) == 1
        assert len(result.embeddings[0]) == 1536
        assert result.model == "text-embedding-3-small"
        assert result.provider == "openai"
        assert result.token_count == 10
        assert result.latency_ms > 0


class TestOpenAITTSProvider:
    @pytest.mark.asyncio
    async def test_tts_provider_synthesize(self):
        cfg = _make_config(
            provider=Provider.OPENAI,
            model_type=ModelType.TTS,
            model_id="tts-1",
        )
        provider = OpenAITTSProvider(cfg, api_key="sk-test")

        mock_client = MockOpenAIClient()

        with patch("openai.AsyncOpenAI", return_value=mock_client):
            result = await provider.synthesize("Hello world", voice="alloy")

        assert isinstance(result, TTSResponse)
        assert isinstance(result.audio_data, bytes)
        assert len(result.audio_data) > 0
        assert result.model == "tts-1"
        assert result.provider == "openai"
        assert result.format == "mp3"
        assert result.latency_ms > 0


# ── ModelManager Tests ───────────────────────────────────────


class TestModelManager:
    @patch("src.agents.nexus_model_layer.ModelManager.__init__", return_value=None)
    def test_model_manager_init(self, mock_init):
        ModelManager()
        mock_init.assert_called_once()

    @patch("src.agents.nexus_model_layer.ModelManager.__init__", return_value=None)
    def test_model_manager_has_provision_methods(self, manager_init_mock):
        manager = ModelManager()
        manager_init_mock.assert_called_once()
        assert hasattr(manager, "provision_llm")
        assert hasattr(manager, "provision_embedding")
        assert hasattr(manager, "provision_tts")
        assert hasattr(manager, "get_model")
        assert hasattr(manager, "list_models")
        assert hasattr(manager, "get_default_model")
        assert hasattr(manager, "get_credential")
