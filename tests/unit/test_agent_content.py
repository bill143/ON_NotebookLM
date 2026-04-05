"""Unit tests for nexus_agent_content — summary, quiz, podcast, flashcards, insights."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.nexus_agent_content import (
    generate_flashcards,
    generate_insights,
    generate_podcast_script,
    generate_quiz,
    generate_summary,
)


def _make_state(overrides=None):
    state = MagicMock()
    state.inputs = {
        "source_content": "Test content about AI and machine learning.",
        "generation_config": {},
        "num_questions": 5,
        "num_cards": 10,
    }
    if overrides:
        state.inputs.update(overrides)
    state.tenant_id = "test-tenant"
    state.user_id = "test-user"
    state.outputs = {}
    return state


def _mock_llm_response(content="Generated content", model="gpt-4o"):
    resp = MagicMock()
    resp.content = content
    resp.model = model
    resp.provider = "openai"
    resp.input_tokens = 100
    resp.output_tokens = 50
    resp.cost_usd = 0.003
    resp.latency_ms = 500
    return resp


def _mock_prompt_result(content="rendered prompt"):
    pr = MagicMock()
    pr.__str__ = MagicMock(return_value=content)
    pr.content = content
    return pr


# ── generate_summary ─────────────────────────────────────────


class TestGenerateSummary:
    @pytest.mark.asyncio
    async def test_returns_summary_and_model(self):
        state = _make_state()
        llm_resp = _mock_llm_response("A concise summary.", "gpt-4o")

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value=llm_resp)
        mock_model_manager = MagicMock()
        mock_model_manager.provision_llm = AsyncMock(return_value=mock_llm)

        mock_prompt = _mock_prompt_result()
        mock_registry = MagicMock()
        mock_registry.resolve = AsyncMock(return_value=mock_prompt)

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            with patch("src.infra.nexus_prompt_registry.prompt_registry", mock_registry):
                with patch("src.infra.nexus_cost_tracker.cost_tracker") as mock_cost:
                    mock_cost.record_usage = AsyncMock()
                    result = await generate_summary(state)

        assert "summary" in result
        assert result["summary"] == "A concise summary."
        assert result["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_calls_prompt_registry_with_studio_summary(self):
        state = _make_state()
        llm_resp = _mock_llm_response()

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value=llm_resp)
        mock_model_manager = MagicMock()
        mock_model_manager.provision_llm = AsyncMock(return_value=mock_llm)

        mock_registry = MagicMock()
        mock_registry.resolve = AsyncMock(return_value=_mock_prompt_result())

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            with patch("src.infra.nexus_prompt_registry.prompt_registry", mock_registry):
                with patch("src.infra.nexus_cost_tracker.cost_tracker") as mock_cost:
                    mock_cost.record_usage = AsyncMock()
                    await generate_summary(state)

        mock_registry.resolve.assert_called_once()
        call_args = mock_registry.resolve.call_args
        assert call_args[0] == ("studio", "summary")

    @pytest.mark.asyncio
    async def test_records_usage(self):
        state = _make_state()
        llm_resp = _mock_llm_response()

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value=llm_resp)
        mock_model_manager = MagicMock()
        mock_model_manager.provision_llm = AsyncMock(return_value=mock_llm)

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            with patch("src.infra.nexus_prompt_registry.prompt_registry") as mock_reg:
                mock_reg.resolve = AsyncMock(return_value=_mock_prompt_result())
                with patch("src.agents.nexus_agent_content.cost_tracker") as mock_cost:
                    mock_cost.record_usage = AsyncMock()
                    await generate_summary(state)

        mock_cost.record_usage.assert_called_once()


# ── generate_quiz ────────────────────────────────────────────


class TestGenerateQuiz:
    @pytest.mark.asyncio
    async def test_returns_quiz_and_model(self):
        state = _make_state()
        quiz_json = json.dumps(
            {"questions": [{"q": "What is AI?", "a": "Artificial Intelligence"}]}
        )
        llm_resp = _mock_llm_response(quiz_json, "gpt-4o")

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value=llm_resp)
        mock_model_manager = MagicMock()
        mock_model_manager.provision_llm = AsyncMock(return_value=mock_llm)

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            with patch("src.infra.nexus_prompt_registry.prompt_registry") as mock_reg:
                mock_reg.resolve = AsyncMock(return_value=_mock_prompt_result())
                with patch("src.infra.nexus_cost_tracker.cost_tracker") as mock_cost:
                    mock_cost.record_usage = AsyncMock()
                    result = await generate_quiz(state)

        assert "quiz" in result
        assert "model" in result
        assert isinstance(result["quiz"], dict)
        assert "questions" in result["quiz"]

    @pytest.mark.asyncio
    async def test_invalid_json_falls_back(self):
        state = _make_state()
        llm_resp = _mock_llm_response("not valid json {{{", "gpt-4o")

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value=llm_resp)
        mock_model_manager = MagicMock()
        mock_model_manager.provision_llm = AsyncMock(return_value=mock_llm)

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            with patch("src.infra.nexus_prompt_registry.prompt_registry") as mock_reg:
                mock_reg.resolve = AsyncMock(return_value=_mock_prompt_result())
                with patch("src.infra.nexus_cost_tracker.cost_tracker") as mock_cost:
                    mock_cost.record_usage = AsyncMock()
                    result = await generate_quiz(state)

        assert "quiz" in result
        assert "raw" in result["quiz"]


# ── generate_podcast_script ──────────────────────────────────


class TestGeneratePodcastScript:
    @pytest.mark.asyncio
    async def test_returns_script_speakers_model_config(self):
        state = _make_state()
        llm_resp = _mock_llm_response("<Person1>Hello</Person1><Person2>Hi</Person2>", "gpt-4o")

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value=llm_resp)
        mock_model_manager = MagicMock()
        mock_model_manager.provision_llm = AsyncMock(return_value=mock_llm)

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            with patch("src.infra.nexus_prompt_registry.prompt_registry") as mock_reg:
                mock_reg.resolve = AsyncMock(return_value=_mock_prompt_result())
                with patch("src.infra.nexus_cost_tracker.cost_tracker") as mock_cost:
                    mock_cost.record_usage = AsyncMock()
                    result = await generate_podcast_script(state)

        assert "script" in result
        assert "speakers" in result
        assert "model" in result
        assert "podcast_config" in result
        assert isinstance(result["speakers"], list)

    @pytest.mark.asyncio
    async def test_longform_normalized_to_long(self):
        state = _make_state({"generation_config": {"length": "longform"}})
        llm_resp = _mock_llm_response("Script", "gpt-4o")

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value=llm_resp)
        mock_model_manager = MagicMock()
        mock_model_manager.provision_llm = AsyncMock(return_value=mock_llm)

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            with patch("src.infra.nexus_prompt_registry.prompt_registry") as mock_reg:
                mock_reg.resolve = AsyncMock(return_value=_mock_prompt_result())
                with patch("src.infra.nexus_cost_tracker.cost_tracker") as mock_cost:
                    mock_cost.record_usage = AsyncMock()
                    await generate_podcast_script(state)

        resolve_call = mock_reg.resolve.call_args
        assert resolve_call[1]["variables"]["length"] == "long"


# ── generate_flashcards ─────────────────────────────────────


class TestGenerateFlashcards:
    @pytest.mark.asyncio
    async def test_returns_flashcards_count_model(self):
        state = _make_state()
        cards = [{"front": "Q1", "back": "A1", "tags": ["ai"]}]
        llm_resp = _mock_llm_response(json.dumps({"flashcards": cards}), "gpt-4o")

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value=llm_resp)
        mock_model_manager = MagicMock()
        mock_model_manager.provision_llm = AsyncMock(return_value=mock_llm)

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            result = await generate_flashcards(state)

        assert "flashcards" in result
        assert "count" in result
        assert "model" in result
        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_flashcards_unwraps_dict(self):
        state = _make_state()
        cards = [{"front": "Q", "back": "A", "tags": []}]
        llm_resp = _mock_llm_response(json.dumps({"flashcards": cards}), "gpt-4o")

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value=llm_resp)
        mock_model_manager = MagicMock()
        mock_model_manager.provision_llm = AsyncMock(return_value=mock_llm)

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            result = await generate_flashcards(state)

        assert isinstance(result["flashcards"], list)

    @pytest.mark.asyncio
    async def test_flashcards_invalid_json(self):
        state = _make_state()
        llm_resp = _mock_llm_response("not json", "gpt-4o")

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value=llm_resp)
        mock_model_manager = MagicMock()
        mock_model_manager.provision_llm = AsyncMock(return_value=mock_llm)

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            result = await generate_flashcards(state)

        assert result["flashcards"] == []
        assert result["count"] == 0


# ── generate_insights ────────────────────────────────────────


class TestGenerateInsights:
    @pytest.mark.asyncio
    async def test_returns_insights_and_model(self):
        state = _make_state()
        insights = {"takeaways": ["point1"], "topics": ["AI"], "entities": [], "questions": []}
        llm_resp = _mock_llm_response(json.dumps(insights), "gpt-4o")

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value=llm_resp)
        mock_model_manager = MagicMock()
        mock_model_manager.provision_llm = AsyncMock(return_value=mock_llm)

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            result = await generate_insights(state)

        assert "insights" in result
        assert "model" in result
        assert result["insights"]["takeaways"] == ["point1"]

    @pytest.mark.asyncio
    async def test_insights_invalid_json_fallback(self):
        state = _make_state()
        llm_resp = _mock_llm_response("bad json }", "gpt-4o")

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value=llm_resp)
        mock_model_manager = MagicMock()
        mock_model_manager.provision_llm = AsyncMock(return_value=mock_llm)

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            result = await generate_insights(state)

        assert result["insights"]["takeaways"] == []
        assert result["insights"]["topics"] == []
        assert result["insights"]["entities"] == []
        assert result["insights"]["questions"] == []
