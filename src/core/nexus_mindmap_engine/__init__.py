"""
Nexus Mind Map Engine — Generate structured mind maps from source content.
Codename: ESPERANTO

Produces a JSON tree structure (nodes + edges) suitable for frontend
graph/mind-map rendering libraries.  Integrates with the artifact system
using artifact_type = 'mind_map'.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from loguru import logger


# ── Data Structures ──────────────────────────────────────────


@dataclass
class MindMapNode:
    id: str
    label: str
    level: int
    parent_id: str | None = None
    description: str = ""
    children: list["MindMapNode"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "level": self.level,
            "parent_id": self.parent_id,
            "description": self.description,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class MindMapEdge:
    source_id: str
    target_id: str
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source_id, "target": self.target_id, "label": self.label}


@dataclass
class MindMapResult:
    title: str
    root: MindMapNode
    edges: list[MindMapEdge]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        _collect_nodes(self.root, nodes)
        return {
            "artifact_type": "mind_map",
            "title": self.title,
            "root": self.root.to_dict(),
            "nodes": nodes,
            "edges": [e.to_dict() for e in self.edges],
            "metadata": self.metadata,
        }


def _collect_nodes(node: MindMapNode, out: list[dict[str, Any]]) -> None:
    out.append(
        {
            "id": node.id,
            "label": node.label,
            "level": node.level,
            "parent_id": node.parent_id,
            "description": node.description,
        }
    )
    for child in node.children:
        _collect_nodes(child, out)


# ── Mind Map Generator ───────────────────────────────────────


async def generate_mind_map(
    content: str,
    title: str = "Mind Map",
    *,
    model_fn: Any | None = None,
) -> MindMapResult:
    """Generate a structured mind map from *content*.

    Parameters
    ----------
    content:
        Source text / notes to analyse.
    title:
        Optional title for the mind map.
    model_fn:
        Optional async callable that accepts a prompt string and returns a
        JSON-parseable string.  When *None* the engine falls back to a
        heuristic extraction approach.

    Returns
    -------
    MindMapResult
        Structured mind map with nodes, edges, and metadata.
    """
    logger.info(f"Generating mind map: title='{title}', content_len={len(content)}")

    if model_fn is not None:
        return await _generate_via_model(content, title, model_fn)
    return _generate_heuristic(content, title)


# ── AI-backed generation ─────────────────────────────────────

_MIND_MAP_PROMPT = """Analyse the following content and extract a structured mind map.
Return a JSON object with this exact schema:
{{
  "title": "<concise title>",
  "central_concept": "<main topic>",
  "branches": [
    {{
      "concept": "<branch label>",
      "description": "<1-sentence description>",
      "sub_concepts": ["<sub-concept>", ...]
    }}
  ]
}}

Content:
{content}
"""


async def _generate_via_model(content: str, title: str, model_fn: Any) -> MindMapResult:
    import json

    prompt = _MIND_MAP_PROMPT.format(content=content[:8000])
    raw = await model_fn(prompt)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Attempt to extract JSON block from response
        import re

        match = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(match.group()) if match else {}

    return _build_tree(data.get("title", title), data.get("branches", []))


# ── Heuristic fallback ───────────────────────────────────────


def _generate_heuristic(content: str, title: str) -> MindMapResult:
    """Simple sentence-based extraction when no model is available."""
    import re

    sentences = [s.strip() for s in re.split(r"[.!?\n]+", content) if len(s.strip()) > 20]
    # Group sentences into pseudo-branches (up to 6 branches, 3 sub-concepts each)
    branches: list[dict[str, Any]] = []
    chunk_size = max(1, len(sentences) // 6)
    for i in range(0, min(len(sentences), 18), chunk_size):
        chunk = sentences[i : i + chunk_size]
        if not chunk:
            continue
        branches.append(
            {
                "concept": _summarise_sentence(chunk[0]),
                "description": chunk[0],
                "sub_concepts": [_summarise_sentence(s) for s in chunk[1:4]],
            }
        )
    return _build_tree(title, branches)


def _summarise_sentence(sentence: str, max_words: int = 5) -> str:
    words = sentence.split()
    return " ".join(words[:max_words]) + ("…" if len(words) > max_words else "")


# ── Tree builder ─────────────────────────────────────────────


def _build_tree(title: str, branches: list[dict[str, Any]]) -> MindMapResult:
    root_id = str(uuid.uuid4())
    root = MindMapNode(id=root_id, label=title, level=0)
    edges: list[MindMapEdge] = []

    for branch in branches:
        branch_id = str(uuid.uuid4())
        branch_node = MindMapNode(
            id=branch_id,
            label=branch.get("concept", ""),
            level=1,
            parent_id=root_id,
            description=branch.get("description", ""),
        )
        root.children.append(branch_node)
        edges.append(MindMapEdge(source_id=root_id, target_id=branch_id))

        for sub in branch.get("sub_concepts", []):
            sub_id = str(uuid.uuid4())
            sub_node = MindMapNode(
                id=sub_id,
                label=sub,
                level=2,
                parent_id=branch_id,
            )
            branch_node.children.append(sub_node)
            edges.append(MindMapEdge(source_id=branch_id, target_id=sub_id))

    return MindMapResult(
        title=title,
        root=root,
        edges=edges,
        metadata={"node_count": sum(1 for _ in _iter_nodes(root)), "branch_count": len(branches)},
    )


def _iter_nodes(node: MindMapNode) -> "Iterator[MindMapNode]":
    from collections.abc import Iterator  # noqa: F401 (used in annotation at runtime)
    yield node
    for child in node.children:
        yield from _iter_nodes(child)
