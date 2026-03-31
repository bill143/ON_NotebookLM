"""
Nexus Data Table Engine — Extract structured tabular data from source content.
Codename: ESPERANTO

Identifies and parses tables, lists, and structured information from PDFs,
plain text, and web pages using AI-assisted extraction.
Supports export to CSV/JSON.
Integrates with the artifact system using artifact_type = 'data_table'.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger


# ── Column Type Enum ─────────────────────────────────────────


class ColumnType(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"
    URL = "url"
    UNKNOWN = "unknown"


# ── Data Structures ──────────────────────────────────────────


@dataclass
class TableColumn:
    name: str
    column_type: ColumnType = ColumnType.TEXT
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "column_type": self.column_type.value,
            "description": self.description,
        }


@dataclass
class DataTableResult:
    title: str
    columns: list[TableColumn]
    rows: list[dict[str, Any]]
    source_type: str = "extracted"
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── Serialisation ────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "data_table",
            "title": self.title,
            "columns": [c.to_dict() for c in self.columns],
            "rows": self.rows,
            "source_type": self.source_type,
            "metadata": self.metadata,
        }

    def to_csv(self) -> str:
        """Export as CSV string."""
        if not self.columns:
            return ""
        output = io.StringIO()
        headers = [c.name for c in self.columns]
        writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(self.rows)
        return output.getvalue()

    def to_json(self) -> str:
        """Export as compact JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ── Data Table Extractor ─────────────────────────────────────


async def extract_data_table(
    content: str,
    title: str = "Extracted Table",
    *,
    model_fn: Any | None = None,
) -> DataTableResult:
    """Extract structured tabular data from *content*.

    Parameters
    ----------
    content:
        Raw text from a PDF, web page, or user upload.
    title:
        Descriptive name for the resulting table.
    model_fn:
        Optional async callable that accepts a prompt string and returns a
        JSON-parseable string.  When *None* the engine falls back to a
        heuristic markdown-table and list parser.

    Returns
    -------
    DataTableResult
        Parsed table with typed columns, rows, and export helpers.
    """
    logger.info(f"Extracting data table: title='{title}', content_len={len(content)}")

    if model_fn is not None:
        return await _extract_via_model(content, title, model_fn)
    return _extract_heuristic(content, title)


# ── AI-backed extraction ─────────────────────────────────────

_TABLE_PROMPT = """Extract all structured tabular data from the following content.
Return a JSON object with this exact schema:
{{
  "title": "<descriptive table name>",
  "columns": [
    {{"name": "<column name>", "column_type": "<text|number|date|boolean|url>", "description": ""}}
  ],
  "rows": [
    {{"<column name>": "<value>", ...}}
  ]
}}
If multiple tables are present, return the most prominent one.

Content:
{content}
"""


async def _extract_via_model(content: str, title: str, model_fn: Any) -> DataTableResult:
    import re

    prompt = _TABLE_PROMPT.format(content=content[:8000])
    raw = await model_fn(prompt)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(match.group()) if match else {}

    columns = [
        TableColumn(
            name=c.get("name", ""),
            column_type=_safe_column_type(c.get("column_type", "text")),
            description=c.get("description", ""),
        )
        for c in data.get("columns", [])
    ]
    rows: list[dict[str, Any]] = data.get("rows", [])
    _infer_types(columns, rows)

    return DataTableResult(
        title=data.get("title", title),
        columns=columns,
        rows=rows,
        source_type="model",
        metadata={"row_count": len(rows), "column_count": len(columns)},
    )


# ── Heuristic markdown-table parser ─────────────────────────


def _extract_heuristic(content: str, title: str) -> DataTableResult:
    """Parse markdown-style tables and delimiter-separated lists."""
    result = _parse_markdown_table(content, title)
    if result is not None:
        return result

    result = _parse_delimiter_list(content, title)
    if result is not None:
        return result

    # Last resort: single-column extraction of key lines
    return _parse_key_lines(content, title)


def _parse_markdown_table(content: str, title: str) -> DataTableResult | None:
    """Extract the first markdown table found in *content*."""
    import re

    pattern = re.compile(
        r"(?m)^(\|.+\|)\n(\|[-| :]+\|)\n((?:\|.+\|\n?)+)"
    )
    m = pattern.search(content)
    if not m:
        return None

    header_cells = [c.strip() for c in m.group(1).split("|") if c.strip()]
    body_lines = m.group(3).strip().split("\n")

    columns = [TableColumn(name=h) for h in header_cells]
    rows: list[dict[str, Any]] = []
    for line in body_lines:
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) == len(columns):
            rows.append(dict(zip(header_cells, cells)))

    _infer_types(columns, rows)
    return DataTableResult(
        title=title,
        columns=columns,
        rows=rows,
        source_type="markdown_table",
        metadata={"row_count": len(rows), "column_count": len(columns)},
    )


def _parse_delimiter_list(content: str, title: str) -> DataTableResult | None:
    """Parse CSV-like delimiter-separated content."""
    import re

    lines = [ln for ln in content.split("\n") if ln.strip()]
    if not lines:
        return None

    # Detect delimiter (tab or comma) from first line
    first = lines[0]
    if "\t" in first:
        delim = "\t"
    elif "," in first:
        delim = ","
    else:
        return None

    # Require at least 2 lines and consistent column count
    header_cells = first.split(delim)
    if len(header_cells) < 2:
        return None

    rows: list[dict[str, Any]] = []
    for line in lines[1:]:
        cells = line.split(delim)
        if len(cells) == len(header_cells):
            rows.append(dict(zip(header_cells, cells)))

    if not rows:
        return None

    columns = [TableColumn(name=h.strip()) for h in header_cells]
    _infer_types(columns, rows)
    return DataTableResult(
        title=title,
        columns=columns,
        rows=rows,
        source_type="delimiter_list",
        metadata={"row_count": len(rows), "column_count": len(columns)},
    )


def _parse_key_lines(content: str, title: str) -> DataTableResult:
    """Fallback: treat each non-empty line as a row with a single 'value' column."""
    lines = [ln.strip() for ln in content.split("\n") if ln.strip()][:100]
    columns = [TableColumn(name="value", column_type=ColumnType.TEXT)]
    rows = [{"value": ln} for ln in lines]
    return DataTableResult(
        title=title,
        columns=columns,
        rows=rows,
        source_type="key_lines",
        metadata={"row_count": len(rows), "column_count": 1},
    )


# ── Type inference helpers ───────────────────────────────────


def _infer_types(columns: list[TableColumn], rows: list[dict[str, Any]]) -> None:
    """Refine column types by sampling the first 20 rows."""
    import re

    _NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?([eE][+-]?\d+)?%?$")
    _DATE_RE = re.compile(r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}")
    _URL_RE = re.compile(r"^https?://")
    _BOOL_VALUES = {"true", "false", "yes", "no", "1", "0"}

    for col in columns:
        if col.column_type != ColumnType.TEXT:
            continue
        sample = [str(row.get(col.name, "")).strip() for row in rows[:20] if row.get(col.name)]
        if not sample:
            continue

        if all(_NUMBER_RE.match(v) for v in sample):
            col.column_type = ColumnType.NUMBER
        elif all(_DATE_RE.search(v) for v in sample):
            col.column_type = ColumnType.DATE
        elif all(v.lower() in _BOOL_VALUES for v in sample):
            col.column_type = ColumnType.BOOLEAN
        elif all(_URL_RE.match(v) for v in sample):
            col.column_type = ColumnType.URL


def _safe_column_type(value: str) -> ColumnType:
    try:
        return ColumnType(value)
    except ValueError:
        return ColumnType.UNKNOWN
