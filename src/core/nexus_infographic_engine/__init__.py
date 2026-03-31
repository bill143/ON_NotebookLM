"""
Nexus Infographic Engine — Generate structured infographic layouts from content.
Codename: ESPERANTO

Produces JSON data suitable for frontend infographic rendering.
Supports multiple styles: Sketch Note, Scientific, Professional, Bento Grid, etc.
Integrates with the artifact system using artifact_type = 'infographic'.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


# ── Style Definitions ────────────────────────────────────────


class InfographicStyle(str, Enum):
    SKETCH_NOTE = "sketch_note"
    SCIENTIFIC = "scientific"
    PROFESSIONAL = "professional"
    BENTO_GRID = "bento_grid"
    TIMELINE = "timeline"
    COMPARISON = "comparison"
    STATISTICAL = "statistical"
    STORY = "story"


# ── Data Structures ──────────────────────────────────────────


@dataclass
class InfographicSection:
    id: str
    title: str
    content: str
    section_type: str  # "text" | "stat" | "list" | "quote" | "image_placeholder"
    data_points: list[dict[str, Any]] = field(default_factory=list)
    visual_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "section_type": self.section_type,
            "data_points": self.data_points,
            "visual_hint": self.visual_hint,
        }


@dataclass
class InfographicResult:
    title: str
    style: InfographicStyle
    sections: list[InfographicSection]
    color_scheme: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "infographic",
            "title": self.title,
            "style": self.style.value,
            "color_scheme": self.color_scheme,
            "sections": [s.to_dict() for s in self.sections],
            "metadata": self.metadata,
        }


# ── Style colour palettes ────────────────────────────────────

_PALETTES: dict[InfographicStyle, list[str]] = {
    InfographicStyle.SKETCH_NOTE: ["#F5E6D3", "#E8B89A", "#C17B5C", "#8B4513", "#2C1810"],
    InfographicStyle.SCIENTIFIC: ["#EEF2FF", "#C7D2FE", "#818CF8", "#4F46E5", "#1E1B4B"],
    InfographicStyle.PROFESSIONAL: ["#F8FAFC", "#E2E8F0", "#64748B", "#1E293B", "#0F172A"],
    InfographicStyle.BENTO_GRID: ["#FFF7ED", "#FED7AA", "#F97316", "#EA580C", "#9A3412"],
    InfographicStyle.TIMELINE: ["#F0FDF4", "#BBF7D0", "#4ADE80", "#16A34A", "#14532D"],
    InfographicStyle.COMPARISON: ["#EFF6FF", "#BFDBFE", "#60A5FA", "#2563EB", "#1E3A8A"],
    InfographicStyle.STATISTICAL: ["#FFF1F2", "#FFE4E6", "#FB7185", "#E11D48", "#881337"],
    InfographicStyle.STORY: ["#FAF5FF", "#E9D5FF", "#C084FC", "#9333EA", "#581C87"],
}


# ── Infographic Generator ────────────────────────────────────


async def generate_infographic(
    content: str,
    title: str = "Infographic",
    style: InfographicStyle = InfographicStyle.PROFESSIONAL,
    *,
    model_fn: Any | None = None,
) -> InfographicResult:
    """Generate a structured infographic layout from *content*.

    Parameters
    ----------
    content:
        Source text / notes to visualise.
    title:
        Optional headline for the infographic.
    style:
        Visual style to use for layout and colour scheme.
    model_fn:
        Optional async callable that accepts a prompt string and returns a
        JSON-parseable string.  When *None* the engine falls back to a
        heuristic extraction approach.

    Returns
    -------
    InfographicResult
        Structured infographic data with sections, colour scheme, and metadata.
    """
    logger.info(
        f"Generating infographic: title='{title}', style='{style.value}', "
        f"content_len={len(content)}"
    )

    if model_fn is not None:
        return await _generate_via_model(content, title, style, model_fn)
    return _generate_heuristic(content, title, style)


# ── AI-backed generation ─────────────────────────────────────

_INFOGRAPHIC_PROMPT = """Analyse the following content and extract an infographic layout.
Return a JSON object with this exact schema:
{{
  "title": "<concise headline>",
  "sections": [
    {{
      "title": "<section heading>",
      "content": "<1-2 sentence summary>",
      "section_type": "<text|stat|list|quote>",
      "data_points": [
        {{"label": "<label>", "value": "<value>", "unit": "<optional unit>"}}
      ],
      "visual_hint": "<icon or chart suggestion>"
    }}
  ]
}}

Content:
{content}
"""


async def _generate_via_model(
    content: str,
    title: str,
    style: InfographicStyle,
    model_fn: Any,
) -> InfographicResult:
    import json
    import re

    prompt = _INFOGRAPHIC_PROMPT.format(content=content[:8000])
    raw = await model_fn(prompt)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(match.group()) if match else {}

    sections = _build_sections(data.get("sections", []))
    return InfographicResult(
        title=data.get("title", title),
        style=style,
        sections=sections,
        color_scheme=_PALETTES[style],
        metadata={"section_count": len(sections), "generated_by": "model"},
    )


# ── Heuristic fallback ───────────────────────────────────────


def _generate_heuristic(content: str, title: str, style: InfographicStyle) -> InfographicResult:
    import re
    import uuid

    paragraphs = [p.strip() for p in re.split(r"\n{2,}", content) if len(p.strip()) > 30]
    raw_sections: list[dict[str, Any]] = []
    for i, para in enumerate(paragraphs[:8]):
        words = para.split()
        heading = " ".join(words[:4]) + ("…" if len(words) > 4 else "")
        raw_sections.append(
            {
                "id": str(uuid.uuid4()),
                "title": heading,
                "content": para[:200],
                "section_type": "text",
                "data_points": [],
                "visual_hint": f"section_{i + 1}",
            }
        )

    sections = _build_sections(raw_sections)
    return InfographicResult(
        title=title,
        style=style,
        sections=sections,
        color_scheme=_PALETTES[style],
        metadata={"section_count": len(sections), "generated_by": "heuristic"},
    )


# ── Section builder ──────────────────────────────────────────


def _build_sections(raw: list[dict[str, Any]]) -> list[InfographicSection]:
    import uuid

    sections: list[InfographicSection] = []
    for item in raw:
        sections.append(
            InfographicSection(
                id=item.get("id", str(uuid.uuid4())),
                title=item.get("title", ""),
                content=item.get("content", ""),
                section_type=item.get("section_type", "text"),
                data_points=item.get("data_points", []),
                visual_hint=item.get("visual_hint", ""),
            )
        )
    return sections
