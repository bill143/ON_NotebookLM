"""
Nexus Agent Content — Content Generation Agent
Source: Repo #9 (content_generator.py), Repo #7 (transformations), Repo #1 (transcript generation)

Handles: reports, summaries, quizzes, podcast scripts, flashcard generation.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from src.infra.nexus_obs_tracing import traced
from src.infra.nexus_cost_tracker import cost_tracker, UsageRecord


@traced("agent.content.generate_summary")
async def generate_summary(state: Any) -> dict[str, Any]:
    """Generate a summary from source content."""
    from src.agents.nexus_model_layer import model_manager
    from src.infra.nexus_prompt_registry import prompt_registry

    source_content = state.inputs.get("source_content", "")
    tenant_id = state.tenant_id

    prompt = await prompt_registry.resolve(
        "studio", "summary",
        variables={"source_content": source_content[:50000]},
    )

    llm = await model_manager.provision_llm(task_type="transformation", tenant_id=tenant_id)
    response = await llm.generate(
        [{"role": "system", "content": str(prompt)}],
        temperature=0.3,
    )

    await cost_tracker.record_usage(UsageRecord(
        tenant_id=tenant_id,
        user_id=state.user_id,
        model_name=response.model,
        provider=response.provider,
        feature_id="1A",
        agent_id="content_generator",
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cost_usd=response.cost_usd,
        latency_ms=response.latency_ms,
    ))

    return {"summary": response.content, "model": response.model}


@traced("agent.content.generate_quiz")
async def generate_quiz(state: Any) -> dict[str, Any]:
    """Generate quiz questions from source material."""
    from src.agents.nexus_model_layer import model_manager
    from src.infra.nexus_prompt_registry import prompt_registry
    import json

    source_content = state.inputs.get("source_content", "")
    num_questions = state.inputs.get("num_questions", 10)
    tenant_id = state.tenant_id

    prompt = await prompt_registry.resolve(
        "studio", "quiz_generator",
        variables={
            "source_content": source_content[:30000],
            "num_questions": num_questions,
        },
    )

    llm = await model_manager.provision_llm(task_type="transformation", tenant_id=tenant_id)
    response = await llm.generate(
        [{"role": "system", "content": str(prompt)}],
        temperature=0.5,
        response_format={"type": "json_object"},
    )

    try:
        questions = json.loads(response.content)
    except json.JSONDecodeError:
        questions = {"questions": [], "raw": response.content}

    return {"quiz": questions, "model": response.model}


@traced("agent.content.generate_script")
async def generate_podcast_script(state: Any) -> dict[str, Any]:
    """
    Generate a multi-speaker podcast script.
    Source: Repo #1 (character generation), Repo #9 (conversation config)
    """
    from src.agents.nexus_model_layer import model_manager
    from src.infra.nexus_prompt_registry import prompt_registry

    source_content = state.inputs.get("source_content", "")
    config = state.inputs.get("generation_config", {})
    tenant_id = state.tenant_id

    num_speakers = config.get("num_speakers", 2)
    tone = config.get("tone", "conversational")
    length = config.get("length", "medium")

    # Default speaker definitions
    speakers = config.get("speakers", [
        {"name": "Alex", "expertise": "Subject matter expert", "style": "analytical"},
        {"name": "Jordan", "expertise": "Curious learner", "style": "engaging"},
    ])

    prompt = await prompt_registry.resolve(
        "podcast", "script_generator",
        variables={
            "source_content": source_content[:40000],
            "num_speakers": num_speakers,
            "speakers": speakers,
            "tone": tone,
            "length": length,
        },
    )

    llm = await model_manager.provision_llm(task_type="transformation", tenant_id=tenant_id)
    response = await llm.generate(
        [{"role": "system", "content": str(prompt)}],
        max_tokens=8192,
        temperature=0.8,
    )

    await cost_tracker.record_usage(UsageRecord(
        tenant_id=tenant_id,
        user_id=state.user_id,
        model_name=response.model,
        provider=response.provider,
        feature_id="3A",
        agent_id="script_generator",
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cost_usd=response.cost_usd,
        latency_ms=response.latency_ms,
    ))

    return {"script": response.content, "speakers": speakers, "model": response.model}


@traced("agent.content.generate_flashcards")
async def generate_flashcards(state: Any) -> dict[str, Any]:
    """Generate flashcards from source material (Feature 5A)."""
    from src.agents.nexus_model_layer import model_manager
    import json

    source_content = state.inputs.get("source_content", "")
    num_cards = state.inputs.get("num_cards", 20)
    tenant_id = state.tenant_id

    system_prompt = f"""Generate {num_cards} flashcards from the following content.
Return as JSON array with format: [{{"front": "question", "back": "answer", "tags": ["tag1"]}}]
Focus on key concepts, definitions, and important relationships.
Content:
{source_content[:30000]}"""

    llm = await model_manager.provision_llm(task_type="transformation", tenant_id=tenant_id)
    response = await llm.generate(
        [{"role": "system", "content": system_prompt}],
        temperature=0.4,
        response_format={"type": "json_object"},
    )

    try:
        cards = json.loads(response.content)
        if isinstance(cards, dict) and "flashcards" in cards:
            cards = cards["flashcards"]
    except json.JSONDecodeError:
        cards = []

    return {"flashcards": cards, "count": len(cards), "model": response.model}


@traced("agent.content.generate_insights")
async def generate_insights(state: Any) -> dict[str, Any]:
    """Generate source insights (key takeaways, topics, entities)."""
    from src.agents.nexus_model_layer import model_manager
    import json

    source_content = state.inputs.get("source_content", "")
    tenant_id = state.tenant_id

    system_prompt = f"""Analyze this content and extract:
1. Key takeaways (3-5 bullet points)
2. Main topics (list of topic names)
3. Named entities (people, organizations, concepts)
4. Questions this content answers
Return as JSON with keys: takeaways, topics, entities, questions
Content:
{source_content[:30000]}"""

    llm = await model_manager.provision_llm(task_type="transformation", tenant_id=tenant_id)
    response = await llm.generate(
        [{"role": "system", "content": system_prompt}],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    try:
        insights = json.loads(response.content)
    except json.JSONDecodeError:
        insights = {"takeaways": [], "topics": [], "entities": [], "questions": []}

    return {"insights": insights, "model": response.model}
