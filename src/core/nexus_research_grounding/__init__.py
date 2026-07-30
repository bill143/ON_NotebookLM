"""
Nexus Research Graph — Multi-Turn Research with LangGraph Checkpointing
Codename: ESPERANTO — Feature 2B: Deep Research Mode

Provides:
- Stateful multi-turn research conversations with persistent memory
- LangGraph-style checkpointing for conversation resumption
- Source-grounded reasoning with iterative refinement
- Automatic follow-up question generation
- Research trail tracking (which sources were consulted, when)
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, cast

from loguru import logger

from src.exceptions import ChainExecutionError
from src.infra.nexus_cost_tracker import UsageRecord, cost_tracker
from src.infra.nexus_obs_tracing import traced

# ── Research State Machine ───────────────────────────────────


class ResearchPhase(str, Enum):
    UNDERSTAND = "understand"  # Parsing the question
    RETRIEVE = "retrieve"  # Finding relevant sources
    ANALYZE = "analyze"  # Deep analysis of retrieved context
    SYNTHESIZE = "synthesize"  # Building the final answer
    SUGGEST = "suggest"  # Generating follow-up questions
    COMPLETE = "complete"  # Done


class ResearchProfile(str, Enum):
    """Execution profiles to tune depth, latency, and token usage."""

    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"
    AUTO = "auto"


PROFILE_SETTINGS: dict[ResearchProfile, dict[str, float | int]] = {
    # Fast/cheap: smaller retrieval and shorter synthesis.
    ResearchProfile.QUICK: {
        "search_query_limit": 2,
        "retrieve_limit": 5,
        "context_chars_per_chunk": 1200,
        "synthesis_max_tokens": 1800,
        "follow_up_count": 2,
    },
    # Balanced default.
    ResearchProfile.STANDARD: {
        "search_query_limit": 4,
        "retrieve_limit": 10,
        "context_chars_per_chunk": 2000,
        "synthesis_max_tokens": 4096,
        "follow_up_count": 3,
    },
    # Highest quality/depth.
    ResearchProfile.DEEP: {
        "search_query_limit": 6,
        "retrieve_limit": 16,
        "context_chars_per_chunk": 3000,
        "synthesis_max_tokens": 6144,
        "follow_up_count": 5,
    },
    # Resolved to QUICK/STANDARD/DEEP after query understanding.
    ResearchProfile.AUTO: {
        "search_query_limit": 4,
        "retrieve_limit": 10,
        "context_chars_per_chunk": 2000,
        "synthesis_max_tokens": 4096,
        "follow_up_count": 3,
    },
}


@dataclass
class SourceReference:
    """A reference to a specific source chunk used in research."""

    source_id: str
    source_title: str
    chunk_index: int
    content_preview: str
    relevance_score: float
    consulted_at: float = field(default_factory=time.time)


@dataclass
class ResearchTurn:
    """A single turn in a multi-turn research conversation."""

    turn_id: str
    query: str
    answer: str
    phase: ResearchPhase
    sources_consulted: list[SourceReference] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    model_used: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class ResearchCheckpoint:
    """
    Full state of a research session — persistable for resumption.
    This is the LangGraph "state" object that flows through the graph.
    """

    session_id: str = ""
    notebook_id: str = ""
    tenant_id: str = ""
    user_id: str = ""
    title: str = ""

    # Conversation history
    turns: list[ResearchTurn] = field(default_factory=list)

    # Accumulated context — grows across turns
    accumulated_context: dict[str, str] = field(default_factory=dict)
    source_ids_consulted: set[str] = field(default_factory=set)

    # Research metadata
    current_phase: ResearchPhase = ResearchPhase.UNDERSTAND
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize checkpoint for database storage."""
        return {
            "session_id": self.session_id,
            "notebook_id": self.notebook_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "title": self.title,
            "turns": [
                {
                    "turn_id": t.turn_id,
                    "query": t.query,
                    "answer": t.answer,
                    "phase": t.phase.value,
                    "sources_consulted": [
                        {
                            "source_id": s.source_id,
                            "source_title": s.source_title,
                            "chunk_index": s.chunk_index,
                            "content_preview": s.content_preview,
                            "relevance_score": s.relevance_score,
                        }
                        for s in t.sources_consulted
                    ],
                    "follow_up_questions": t.follow_up_questions,
                    "model_used": t.model_used,
                    "input_tokens": t.input_tokens,
                    "output_tokens": t.output_tokens,
                    "latency_ms": t.latency_ms,
                    "timestamp": t.timestamp,
                }
                for t in self.turns
            ],
            "accumulated_context": self.accumulated_context,
            "source_ids_consulted": list(self.source_ids_consulted),
            "current_phase": self.current_phase.value,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchCheckpoint:
        """Restore checkpoint from database."""
        cp = cls(
            session_id=data["session_id"],
            notebook_id=data.get("notebook_id", ""),
            tenant_id=data.get("tenant_id", ""),
            user_id=data.get("user_id", ""),
            title=data.get("title", ""),
            accumulated_context=data.get("accumulated_context", {}),
            source_ids_consulted=set(data.get("source_ids_consulted", [])),
            current_phase=ResearchPhase(data.get("current_phase", "understand")),
            total_tokens=data.get("total_tokens", 0),
            total_cost_usd=data.get("total_cost_usd", 0.0),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
        )
        for turn_data in data.get("turns", []):
            turn = ResearchTurn(
                turn_id=turn_data["turn_id"],
                query=turn_data["query"],
                answer=turn_data["answer"],
                phase=ResearchPhase(turn_data.get("phase", "complete")),
                follow_up_questions=turn_data.get("follow_up_questions", []),
                model_used=turn_data.get("model_used", ""),
                input_tokens=turn_data.get("input_tokens", 0),
                output_tokens=turn_data.get("output_tokens", 0),
                latency_ms=turn_data.get("latency_ms", 0.0),
                timestamp=turn_data.get("timestamp", time.time()),
            )
            for src in turn_data.get("sources_consulted", []):
                turn.sources_consulted.append(
                    SourceReference(
                        source_id=src["source_id"],
                        source_title=src["source_title"],
                        chunk_index=src.get("chunk_index", 0),
                        content_preview=src.get("content_preview", ""),
                        relevance_score=src.get("relevance_score", 0.0),
                    )
                )
            cp.turns.append(turn)
        return cp


# ── Checkpoint Store ─────────────────────────────────────────


class CheckpointStore:
    """
    Persistent checkpoint storage — saves/restores research state.
    Source: LangGraph MemorySaver pattern, adapted for PostgreSQL.
    """

    @traced("checkpoint.save")
    async def save(self, checkpoint: ResearchCheckpoint) -> None:
        """Persist checkpoint to database."""
        from sqlalchemy import text

        from src.infra.nexus_data_persist import get_session

        checkpoint.updated_at = time.time()

        async with get_session(checkpoint.tenant_id) as session:
            # Upsert checkpoint
            await session.execute(
                text("""
                    INSERT INTO sessions (id, tenant_id, user_id, notebook_id,
                        session_type, title, checkpoint_data, updated_at)
                    VALUES (:id, :tid, :uid, :nid, 'research', :title, :data::jsonb, NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        checkpoint_data = :data::jsonb,
                        title = :title,
                        updated_at = NOW()
                """),
                {
                    "id": checkpoint.session_id,
                    "tid": checkpoint.tenant_id,
                    "uid": checkpoint.user_id,
                    "nid": checkpoint.notebook_id,
                    "title": checkpoint.title,
                    "data": json.dumps(checkpoint.to_dict()),
                },
            )

        logger.debug(
            f"Checkpoint saved: {checkpoint.session_id}",
            turns=len(checkpoint.turns),
            total_tokens=checkpoint.total_tokens,
        )

    @traced("checkpoint.load")
    async def load(self, session_id: str, tenant_id: str) -> ResearchCheckpoint | None:
        """Load checkpoint from database."""
        from sqlalchemy import text

        from src.infra.nexus_data_persist import get_session

        async with get_session(tenant_id) as session:
            result = await session.execute(
                text("""
                    SELECT checkpoint_data FROM sessions
                    WHERE id = :id AND tenant_id = :tid AND session_type = 'research'
                """),
                {"id": session_id, "tid": tenant_id},
            )
            row = result.mappings().first()

        if not row or not row["checkpoint_data"]:
            return None

        data = row["checkpoint_data"]
        if isinstance(data, str):
            data = json.loads(data)

        return ResearchCheckpoint.from_dict(data)

    @traced("checkpoint.list")
    async def list_sessions(
        self,
        tenant_id: str,
        user_id: str,
        notebook_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List research sessions for a user."""
        from sqlalchemy import text

        from src.infra.nexus_data_persist import get_session

        query = """
            SELECT id, title, notebook_id, created_at, updated_at,
                   (checkpoint_data->>'total_tokens')::int as total_tokens,
                   jsonb_array_length(checkpoint_data->'turns') as turn_count
            FROM sessions
            WHERE tenant_id = :tid AND user_id = :uid AND session_type = 'research'
        """
        params: dict[str, Any] = {"tid": tenant_id, "uid": user_id}

        if notebook_id:
            query += " AND notebook_id = :nid"
            params["nid"] = notebook_id

        query += " ORDER BY updated_at DESC LIMIT :limit"
        params["limit"] = limit

        async with get_session(tenant_id) as session:
            result = await session.execute(text(query), params)
            return [dict(row) for row in result.mappings().all()]


# ── Research Graph Engine ────────────────────────────────────


class ResearchGraph:
    """
    Multi-turn research engine with LangGraph-style state management.

    Pipeline per turn:
    UNDERSTAND → RETRIEVE → ANALYZE → SYNTHESIZE → SUGGEST → COMPLETE

    Each phase can be conditionally skipped based on the query type.
    """

    def __init__(self) -> None:
        self.checkpoint_store = CheckpointStore()

    @traced("research.execute_turn")
    async def execute_turn(
        self,
        query: str,
        *,
        session_id: str | None = None,
        notebook_id: str = "",
        tenant_id: str = "",
        user_id: str = "",
        profile: str = ResearchProfile.STANDARD.value,
        max_follow_ups: int | None = None,
    ) -> dict[str, Any]:
        """Execute a single research turn, creating or resuming a session."""
        try:
            resolved_profile = ResearchProfile(profile)
        except ValueError:
            resolved_profile = ResearchProfile.STANDARD

        settings = PROFILE_SETTINGS[resolved_profile]

        # 1. Load or create checkpoint
        checkpoint: ResearchCheckpoint | None = None
        if session_id:
            checkpoint = await self.checkpoint_store.load(session_id, tenant_id)

        if not checkpoint:
            checkpoint = ResearchCheckpoint(
                session_id=session_id or str(uuid.uuid4()),
                notebook_id=notebook_id,
                tenant_id=tenant_id,
                user_id=user_id,
                title=query[:100],
            )

        turn_id = str(uuid.uuid4())[:12]
        start_time = time.perf_counter()

        # 2. Run the research pipeline
        try:
            checkpoint.current_phase = ResearchPhase.UNDERSTAND
            query_analysis = await self._understand(query, checkpoint)

            if resolved_profile == ResearchProfile.AUTO:
                depth = str(query_analysis.get("depth", "")).lower()
                if depth == "quick_answer":
                    resolved_profile = ResearchProfile.QUICK
                elif depth == "deep_research":
                    resolved_profile = ResearchProfile.DEEP
                else:
                    resolved_profile = ResearchProfile.STANDARD
                settings = PROFILE_SETTINGS[resolved_profile]

            follow_up_count = (
                max_follow_ups if max_follow_ups is not None else int(settings["follow_up_count"])
            )

            checkpoint.current_phase = ResearchPhase.RETRIEVE
            retrieved = await self._retrieve(
                query,
                checkpoint,
                query_analysis,
                settings=settings,
            )

            # Web search augmentation (Feature 2A)
            web_results = await self._web_search(
                query,
                query_analysis,
                settings=settings,
            )
            if web_results:
                retrieved = self._merge_web_results(retrieved, web_results)

            checkpoint.current_phase = ResearchPhase.ANALYZE
            analysis = await self._analyze(query, checkpoint, retrieved)

            checkpoint.current_phase = ResearchPhase.SYNTHESIZE
            answer, model_used, tokens = await self._synthesize(
                query,
                checkpoint,
                analysis,
                settings=settings,
            )

            checkpoint.current_phase = ResearchPhase.SUGGEST
            follow_ups = await self._suggest_follow_ups(
                query,
                answer,
                checkpoint,
                follow_up_count=follow_up_count,
            )

            checkpoint.current_phase = ResearchPhase.COMPLETE

        except Exception as e:
            logger.error(f"Research turn failed: {e}")
            raise ChainExecutionError(
                f"Research pipeline failed at {checkpoint.current_phase.value}: {e}",
                failed_agent="research_graph",
            ) from e

        latency_ms = (time.perf_counter() - start_time) * 1000

        # 3. Create turn record
        turn = ResearchTurn(
            turn_id=turn_id,
            query=query,
            answer=answer,
            phase=ResearchPhase.COMPLETE,
            sources_consulted=retrieved.get("references", []),
            follow_up_questions=follow_ups,
            model_used=model_used,
            input_tokens=int(tokens.get("input", 0)),
            output_tokens=int(tokens.get("output", 0)),
            latency_ms=latency_ms,
        )

        checkpoint.turns.append(turn)
        checkpoint.total_tokens += int(tokens.get("input", 0)) + int(tokens.get("output", 0))

        # 4. Persist checkpoint
        await self.checkpoint_store.save(checkpoint)

        # 5. Record usage
        await cost_tracker.record_usage(
            UsageRecord(
                tenant_id=tenant_id,
                user_id=user_id,
                model_name=model_used,
                provider="",
                feature_id="2B",
                agent_id="research_graph",
                input_tokens=int(tokens.get("input", 0)),
                output_tokens=int(tokens.get("output", 0)),
                cost_usd=float(tokens.get("cost", 0.0)),
                latency_ms=latency_ms,
            )
        )

        logger.info(
            "Research turn completed",
            session_id=checkpoint.session_id,
            turn=len(checkpoint.turns),
            latency_ms=round(latency_ms, 2),
        )

        return {
            "session_id": checkpoint.session_id,
            "turn_id": turn_id,
            "turn_number": len(checkpoint.turns),
            "answer": answer,
            "citations": [
                {
                    "source_id": r.source_id,
                    "source_title": r.source_title,
                    "cited_text": r.content_preview,
                    "relevance_score": r.relevance_score,
                }
                for r in turn.sources_consulted
            ],
            "follow_up_questions": follow_ups,
            "model_used": model_used,
            "latency_ms": round(latency_ms, 2),
            "total_turns": len(checkpoint.turns),
            "profile_used": resolved_profile.value,
        }

    # ── Pipeline Phases ──────────────────────────────

    async def _understand(
        self,
        query: str,
        checkpoint: ResearchCheckpoint,
    ) -> dict[str, Any]:
        """Phase 1: Understand the query intent and required depth."""
        from src.agents.nexus_model_layer import model_manager

        # Build context from previous turns
        history_context = ""
        if checkpoint.turns:
            recent = checkpoint.turns[-3:]  # Last 3 turns for context
            history_context = "\n".join(
                f"Q{i + 1}: {t.query}\nA{i + 1}: {t.answer[:500]}" for i, t in enumerate(recent)
            )

        prompt = f"""Analyze this research query and determine:
1. The core question being asked
2. Key concepts to search for
3. Whether this is a follow-up to previous research
4. Required depth: "quick_answer", "detailed_analysis", or "deep_research"

{"Previous research context:" + chr(10) + history_context if history_context else "This is the first question in a new research session."}

Query: {query}

Respond as JSON with keys: core_question, search_terms, is_follow_up, depth"""

        llm = await model_manager.provision_llm(
            task_type="research",
            tenant_id=checkpoint.tenant_id,
        )
        response = await llm.generate(
            [{"role": "system", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        try:
            return cast(dict[str, Any], json.loads(response.content))
        except json.JSONDecodeError:
            return {
                "core_question": query,
                "search_terms": [query],
                "is_follow_up": bool(checkpoint.turns),
                "depth": "detailed_analysis",
            }

    @traced("research.web_search")
    async def _web_search(
        self,
        query: str,
        analysis: dict[str, Any],
        *,
        settings: dict[str, float | int],
    ) -> list[dict[str, Any]]:
        """
        Feature 2A: Live web search retrieval.
        Uses Tavily (primary) or DuckDuckGo (fallback).
        Returns empty list if no web search provider is configured.
        """
        from src.config import get_settings

        app_settings = get_settings()
        search_terms = [query] + analysis.get("search_terms", [])[:2]
        results: list[dict[str, Any]] = []

        # Try Tavily first
        tavily_key = getattr(app_settings, "tavily_api_key", "") or ""
        if tavily_key:
            try:
                import httpx

                async with httpx.AsyncClient(timeout=15.0) as client:
                    for term in search_terms[:2]:
                        resp = await client.post(
                            "https://api.tavily.com/search",
                            json={
                                "api_key": tavily_key,
                                "query": term,
                                "search_depth": "basic",
                                "max_results": 3,
                                "include_answer": True,
                            },
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            for r in data.get("results", []):
                                results.append(
                                    {
                                        "source_id": f"web:{r.get('url', '')}",
                                        "source_title": r.get("title", "Web Result"),
                                        "content": r.get("content", ""),
                                        "url": r.get("url", ""),
                                        "score": r.get("score", 0.5),
                                        "is_web": True,
                                    }
                                )
                logger.info(f"Tavily returned {len(results)} web results")
                return results
            except Exception as e:
                logger.warning(f"Tavily search failed: {e}")

        # Fallback: DuckDuckGo (no API key needed)
        try:
            from duckduckgo_search import DDGS

            with DDGS() as ddgs:
                for term in search_terms[:2]:
                    for r in ddgs.text(term, max_results=3):
                        results.append(
                            {
                                "source_id": f"web:{r.get('href', '')}",
                                "source_title": r.get("title", "Web Result"),
                                "content": r.get("body", ""),
                                "url": r.get("href", ""),
                                "score": 0.5,
                                "is_web": True,
                            }
                        )
            logger.info(f"DuckDuckGo returned {len(results)} web results")
        except ImportError:
            logger.debug("No web search provider available (install duckduckgo-search)")
        except Exception as e:
            logger.warning(f"DuckDuckGo search failed: {e}")

        return results

    def _merge_web_results(
        self,
        retrieved: dict[str, Any],
        web_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Merge web search results into the retrieval output."""
        context = retrieved.get("context", "")
        references = list(retrieved.get("references", []))

        web_context_parts = []
        for wr in web_results[:5]:
            web_context_parts.append(f"[Web: {wr['source_title']}]\n{wr['content'][:2000]}")
            references.append(
                SourceReference(
                    source_id=wr["source_id"],
                    source_title=f"[Web] {wr['source_title']}",
                    chunk_index=0,
                    content_preview=wr["content"][:250],
                    relevance_score=wr.get("score", 0.5),
                )
            )

        if web_context_parts:
            web_section = "\n\n---\n\n".join(web_context_parts)
            context = f"{context}\n\n=== WEB SEARCH RESULTS ===\n\n{web_section}"

        return {"context": context, "references": references}

    async def _retrieve(
        self,
        query: str,
        checkpoint: ResearchCheckpoint,
        analysis: dict[str, Any],
        settings: dict[str, float | int],
    ) -> dict[str, Any]:
        """Phase 2: Retrieve relevant source chunks via vector search."""
        from sqlalchemy import text

        from src.agents.nexus_model_layer import model_manager
        from src.infra.nexus_data_persist import get_session, sources_repo

        source_ids = []
        if checkpoint.notebook_id:
            async with get_session(checkpoint.tenant_id) as session:
                result = await session.execute(
                    text("SELECT source_id FROM notebook_sources WHERE notebook_id = :nid"),
                    {"nid": checkpoint.notebook_id},
                )
                source_ids = [row["source_id"] for row in result.mappings().all()]

        if not source_ids:
            return {"context": "", "references": []}

        # Embed query + search terms
        search_query_limit = int(settings["search_query_limit"])
        search_queries = [query] + analysis.get("search_terms", [])[
            : max(0, search_query_limit - 1)
        ]
        embedding_provider = await model_manager.provision_embedding(tenant_id=checkpoint.tenant_id)

        all_chunks = []
        seen_chunk_ids = set()

        for sq in search_queries:
            embedding_result = await embedding_provider.embed([sq])
            chunks = await sources_repo.vector_search(
                query_embedding=embedding_result.embeddings[0],
                source_ids=source_ids,
                tenant_id=checkpoint.tenant_id,
                limit=int(settings["retrieve_limit"]),
                min_score=0.35,
            )
            for chunk in chunks:
                chunk_key = f"{chunk.get('source_id', '')}:{chunk.get('chunk_index', 0)}"
                if chunk_key not in seen_chunk_ids:
                    seen_chunk_ids.add(chunk_key)
                    all_chunks.append(chunk)

        # Sort by relevance and take profile-tuned number of chunks.
        all_chunks.sort(key=lambda c: c.get("score", 0), reverse=True)
        top_chunks = all_chunks[: int(settings["retrieve_limit"])]

        # Build references
        references: list[SourceReference] = []
        context_parts = []

        for chunk in top_chunks:
            source_data = await sources_repo.get_by_id(chunk["source_id"], checkpoint.tenant_id)
            title = source_data.get("title", "Unknown") if source_data else "Unknown"

            ref = SourceReference(
                source_id=chunk["source_id"],
                source_title=title,
                chunk_index=chunk.get("chunk_index", 0),
                content_preview=chunk["content"][:250],
                relevance_score=chunk.get("score", 0.0),
            )
            references.append(ref)
            max_context_chars = int(settings["context_chars_per_chunk"])
            context_parts.append(f"[Source: {title}]\n{chunk['content'][:max_context_chars]}")

            checkpoint.source_ids_consulted.add(chunk["source_id"])

        context = "\n\n---\n\n".join(context_parts)

        # Add to accumulated context for multi-turn awareness
        checkpoint.accumulated_context[query[:50]] = context[:2000]

        return {"context": context, "references": references}

    async def _analyze(
        self,
        query: str,
        checkpoint: ResearchCheckpoint,
        retrieved: dict[str, Any],
    ) -> str:
        """Phase 3: Analyze retrieved context for relevance and gaps."""
        context = retrieved.get("context", "")
        if not context:
            return "No relevant source material found for this query."

        # For detailed analysis, check what the previous turns have covered
        covered_topics: list[str] = []
        for turn in checkpoint.turns[-3:]:
            covered_topics.extend(s.source_title for s in turn.sources_consulted)

        return str(context)  # Pass through for synthesis — analysis is integrated

    async def _synthesize(
        self,
        query: str,
        checkpoint: ResearchCheckpoint,
        context: str,
        settings: dict[str, float | int],
    ) -> tuple[str, str, dict[str, float | int]]:
        """Phase 4: Synthesize a grounded answer from context."""
        from src.agents.nexus_model_layer import model_manager
        from src.infra.nexus_prompt_registry import prompt_registry

        # Build conversation history for multi-turn awareness
        history_messages = []
        for turn in checkpoint.turns[-5:]:
            history_messages.append({"role": "user", "content": turn.query})
            history_messages.append({"role": "assistant", "content": turn.answer[:2000]})

        # Get grounding prompt
        try:
            system_prompt = await prompt_registry.resolve(
                "research",
                "grounding",
                variables={"sources": []},
            )
            system_content = str(system_prompt)
        except Exception:
            system_content = (
                "You are a research analyst. Answer questions using ONLY "
                "the provided source context. Cite sources inline as [Source: Title]."
            )

        messages = [
            {"role": "system", "content": system_content},
            *history_messages,
            {
                "role": "user",
                "content": f"Source Context:\n{context}\n\n"
                f"Research Question: {query}\n\n"
                "Provide a thorough, well-cited answer.",
            },
        ]

        llm = await model_manager.provision_llm(
            task_type="research",
            tenant_id=checkpoint.tenant_id,
        )
        response = await llm.generate(
            messages,
            temperature=0.3,
            max_tokens=int(settings["synthesis_max_tokens"]),
        )

        tokens = {
            "input": response.input_tokens,
            "output": response.output_tokens,
            "cost": response.cost_usd,
        }

        return response.content, response.model, tokens

    async def _suggest_follow_ups(
        self,
        query: str,
        answer: str,
        checkpoint: ResearchCheckpoint,
        follow_up_count: int = 3,
    ) -> list[str]:
        """Phase 5: Generate follow-up questions based on the answer."""
        from src.agents.nexus_model_layer import model_manager

        try:
            llm = await model_manager.provision_llm(
                task_type="transformation",
                tenant_id=checkpoint.tenant_id,
            )
            response = await llm.generate(
                [
                    {
                        "role": "system",
                        "content": (
                            f"Based on this Q&A exchange, suggest {follow_up_count} natural "
                            "follow-up questions the researcher might ask next. "
                            "Return as a JSON array of strings."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Question: {query}\n\nAnswer: {answer[:1500]}",
                    },
                ],
                temperature=0.6,
                max_tokens=300,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.content)
            if isinstance(result, dict):
                questions = result.get("questions") or result.get("follow_ups") or []
                if not isinstance(questions, list):
                    return []
                return [str(q) for q in questions[:follow_up_count]]
            if isinstance(result, list):
                return [str(q) for q in result[:follow_up_count]]
            return []
        except Exception:
            return []

    # ── Session Management ───────────────────────────

    async def get_session(
        self,
        session_id: str,
        tenant_id: str,
    ) -> dict[str, Any] | None:
        """Get research session details."""
        checkpoint = await self.checkpoint_store.load(session_id, tenant_id)
        if not checkpoint:
            return None
        return cast(dict[str, Any], checkpoint.to_dict())

    async def list_sessions(
        self,
        tenant_id: str,
        user_id: str,
        notebook_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List research sessions."""
        rows = await self.checkpoint_store.list_sessions(tenant_id, user_id, notebook_id)
        return cast(list[dict[str, Any]], rows)


# Global singleton
research_graph = ResearchGraph()
