"""
Unit Tests — Nexus Agent Orchestrator (Chain Executor, Registry, State)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.nexus_agent_orchestrator import (
    AgentRegistry,
    AgentResult,
    AgentStatus,
    ChainExecutor,
    ChainState,
    ChainStep,
    CompensationStrategy,
)
from src.exceptions import ChainExecutionError

# ── ChainState ──────────────────────────────────────────────


class TestChainState:
    def test_chain_state_init(self):
        state = ChainState()
        assert state.chain_id == ""
        assert state.trace_id == ""
        assert state.tenant_id == ""
        assert state.user_id == ""
        assert state.current_step == 0
        assert state.total_steps == 0

    def test_chain_state_has_inputs(self):
        state = ChainState(inputs={"source": "file.pdf"})
        assert state.inputs == {"source": "file.pdf"}

    def test_chain_state_has_outputs(self):
        state = ChainState(outputs={"summary": "done"})
        assert state.outputs == {"summary": "done"}

    def test_chain_state_defaults_are_independent(self):
        """Each instance gets its own mutable defaults."""
        a = ChainState()
        b = ChainState()
        a.inputs["x"] = 1
        assert "x" not in b.inputs

    def test_chain_state_tenant_id(self):
        state = ChainState(tenant_id="tenant-42", user_id="user-7")
        assert state.tenant_id == "tenant-42"
        assert state.user_id == "user-7"

    def test_chain_state_agent_results_default_empty(self):
        state = ChainState()
        assert state.agent_results == []

    def test_chain_state_metadata_default_empty(self):
        state = ChainState()
        assert state.metadata == {}


# ── ChainStep ───────────────────────────────────────────────


class TestChainStep:
    def test_chain_step_init(self):
        handler = MagicMock()
        step = ChainStep(agent_id="embedder", handler=handler)
        assert step.agent_id == "embedder"
        assert step.handler is handler
        assert step.timeout_seconds == 300.0
        assert step.max_retries == 2

    def test_chain_step_default_compensation(self):
        step = ChainStep(agent_id="x", handler=MagicMock())
        assert step.compensation == CompensationStrategy.EMIT_PARTIAL

    def test_chain_step_custom_values(self):
        handler = MagicMock()
        step = ChainStep(
            agent_id="slow_agent",
            handler=handler,
            timeout_seconds=600.0,
            compensation=CompensationStrategy.DEAD_LETTER,
            max_retries=5,
            parallel_group="batch_1",
        )
        assert step.timeout_seconds == 600.0
        assert step.compensation == CompensationStrategy.DEAD_LETTER
        assert step.max_retries == 5
        assert step.parallel_group == "batch_1"

    def test_chain_step_depends_on_default_empty(self):
        step = ChainStep(agent_id="x", handler=MagicMock())
        assert step.depends_on == []


# ── CompensationStrategy ────────────────────────────────────


class TestCompensationStrategy:
    def test_compensation_strategy_enum(self):
        assert CompensationStrategy.RETRY == "retry"
        assert CompensationStrategy.ROLLBACK == "rollback"
        assert CompensationStrategy.EMIT_PARTIAL == "emit_partial"
        assert CompensationStrategy.DEAD_LETTER == "dead_letter"

    def test_compensation_strategy_member_count(self):
        assert len(CompensationStrategy) == 4


# ── AgentStatus ─────────────────────────────────────────────


class TestAgentStatus:
    def test_agent_status_values(self):
        assert AgentStatus.PENDING == "pending"
        assert AgentStatus.RUNNING == "running"
        assert AgentStatus.COMPLETED == "completed"
        assert AgentStatus.FAILED == "failed"
        assert AgentStatus.SKIPPED == "skipped"


# ── AgentResult ─────────────────────────────────────────────


class TestAgentResult:
    def test_agent_result_defaults(self):
        r = AgentResult(agent_id="test", status=AgentStatus.COMPLETED)
        assert r.output is None
        assert r.error is None
        assert r.duration_ms == 0.0

    def test_agent_result_with_output(self):
        r = AgentResult(
            agent_id="embedder",
            status=AgentStatus.COMPLETED,
            output={"vectors": 42},
            duration_ms=123.4,
        )
        assert r.output == {"vectors": 42}
        assert r.duration_ms == 123.4


# ── AgentRegistry ───────────────────────────────────────────


class TestAgentRegistry:
    def setup_method(self):
        AgentRegistry._agents = {}

    def test_agent_registry_init(self):
        assert AgentRegistry._agents == {}

    @patch("src.agents.nexus_agent_orchestrator.logger")
    def test_agent_registry_register(self, mock_logger):
        handler = AsyncMock()
        AgentRegistry.register("my_agent", handler, description="test")
        assert "my_agent" in AgentRegistry._agents
        mock_logger.info.assert_called_once()

    @patch("src.agents.nexus_agent_orchestrator.logger")
    def test_agent_registry_get(self, mock_logger):
        handler = AsyncMock()
        AgentRegistry.register("my_agent", handler)
        retrieved = AgentRegistry.get_handler("my_agent")
        assert retrieved is handler

    def test_agent_registry_get_missing_raises(self):
        with pytest.raises(ChainExecutionError, match="not registered"):
            AgentRegistry.get_handler("nonexistent")

    @patch("src.agents.nexus_agent_orchestrator.logger")
    def test_agent_registry_list(self, mock_logger):
        AgentRegistry.register("a", MagicMock(), role="analyzer")
        AgentRegistry.register("b", MagicMock(), role="embedder")
        agents = AgentRegistry.list_agents()
        assert len(agents) == 2
        ids = {a["agent_id"] for a in agents}
        assert ids == {"a", "b"}

    @patch("src.agents.nexus_agent_orchestrator.logger")
    def test_agent_registry_list_includes_metadata(self, mock_logger):
        AgentRegistry.register("x", MagicMock(), tier="premium")
        listed = AgentRegistry.list_agents()
        assert listed[0]["tier"] == "premium"


# ── ChainExecutor ───────────────────────────────────────────


class TestChainExecutor:
    def test_executor_init(self):
        executor = ChainExecutor()
        assert executor.get_dead_letter_count() == 0

    @pytest.mark.asyncio
    @patch("src.agents.nexus_agent_orchestrator.trace_id_var")
    @patch("src.agents.nexus_agent_orchestrator.logger")
    async def test_execute_single_step_success(self, mock_logger, mock_trace_var):
        mock_trace_var.get.return_value = "trace-abc"

        handler = AsyncMock(return_value={"result": "ok"})
        AgentRegistry._agents = {}
        AgentRegistry._agents["test_agent"] = {
            "handler": handler,
            "metadata": {},
            "registered_at": 0,
        }

        step = ChainStep(agent_id="test_agent", handler=handler, max_retries=0)
        state = ChainState(tenant_id="t1", user_id="u1")

        executor = ChainExecutor()
        result = await executor.execute([step], state)

        assert result.total_steps == 1
        assert len(result.agent_results) == 1
        assert result.agent_results[0].status == AgentStatus.COMPLETED

    @pytest.mark.asyncio
    @patch("src.agents.nexus_agent_orchestrator.trace_id_var")
    @patch("src.agents.nexus_agent_orchestrator.logger")
    async def test_execute_step_failure_recorded(self, mock_logger, mock_trace_var):
        mock_trace_var.get.return_value = ""

        handler = AsyncMock(side_effect=RuntimeError("boom"))
        AgentRegistry._agents = {
            "fail_agent": {"handler": handler, "metadata": {}, "registered_at": 0}
        }

        step = ChainStep(
            agent_id="fail_agent",
            handler=handler,
            max_retries=0,
            compensation=CompensationStrategy.EMIT_PARTIAL,
        )
        state = ChainState()
        executor = ChainExecutor()
        result = await executor.execute([step], state)

        assert result.agent_results[0].status == AgentStatus.FAILED
        assert "boom" in result.agent_results[0].error
