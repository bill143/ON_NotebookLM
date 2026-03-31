"""
Unit Tests — New Generation Engines
Tests for MindMap, Infographic, and DataTable engines.
"""

from __future__ import annotations

import asyncio
import pytest

from src.core.nexus_mindmap_engine import (
    MindMapNode,
    MindMapEdge,
    MindMapResult,
    generate_mind_map,
    _build_tree,
    _generate_heuristic,
)
from src.core.nexus_infographic_engine import (
    InfographicStyle,
    InfographicSection,
    InfographicResult,
    generate_infographic,
    _generate_heuristic as infographic_heuristic,
)
from src.core.nexus_datatable_engine import (
    ColumnType,
    TableColumn,
    DataTableResult,
    extract_data_table,
    _parse_markdown_table,
    _parse_delimiter_list,
    _infer_types,
)


# ── MindMap Engine Tests ─────────────────────────────────────


class TestMindMapEngine:
    """Test mind map generation."""

    def test_build_tree_basic(self):
        """_build_tree should produce a root node with children."""
        branches = [
            {"concept": "Branch A", "description": "Desc A", "sub_concepts": ["Sub A1", "Sub A2"]},
            {"concept": "Branch B", "description": "Desc B", "sub_concepts": []},
        ]
        result = _build_tree("Root Topic", branches)

        assert result.title == "Root Topic"
        assert result.root.label == "Root Topic"
        assert result.root.level == 0
        assert len(result.root.children) == 2

    def test_build_tree_sub_concepts(self):
        """Sub-concepts should be level-2 nodes attached to branch nodes."""
        branches = [
            {"concept": "AI", "description": "", "sub_concepts": ["ML", "DL", "NLP"]},
        ]
        result = _build_tree("Technology", branches)

        branch = result.root.children[0]
        assert branch.label == "AI"
        assert branch.level == 1
        assert len(branch.children) == 3
        assert branch.children[0].level == 2

    def test_build_tree_edges(self):
        """Edges should connect root→branch and branch→sub-concept."""
        branches = [
            {"concept": "B1", "description": "", "sub_concepts": ["S1"]},
        ]
        result = _build_tree("Root", branches)

        # root→B1 and B1→S1
        assert len(result.edges) == 2
        root_id = result.root.id
        branch_id = result.root.children[0].id
        sub_id = result.root.children[0].children[0].id

        edge_ids = [(e.source_id, e.target_id) for e in result.edges]
        assert (root_id, branch_id) in edge_ids
        assert (branch_id, sub_id) in edge_ids

    def test_build_tree_metadata(self):
        """Metadata should include node_count and branch_count."""
        branches = [{"concept": "B", "description": "", "sub_concepts": ["S1", "S2"]}]
        result = _build_tree("Root", branches)

        assert result.metadata["branch_count"] == 1
        # root + 1 branch + 2 sub = 4
        assert result.metadata["node_count"] == 4

    def test_to_dict_structure(self):
        """to_dict() should include artifact_type, nodes, edges, title."""
        result = _build_tree("Test", [{"concept": "C", "description": "", "sub_concepts": []}])
        d = result.to_dict()

        assert d["artifact_type"] == "mind_map"
        assert d["title"] == "Test"
        assert isinstance(d["nodes"], list)
        assert isinstance(d["edges"], list)
        assert len(d["nodes"]) >= 2  # root + branch

    def test_heuristic_generation(self):
        """Heuristic generator should produce a valid result from text."""
        content = (
            "Machine learning is a subset of AI. "
            "Deep learning uses neural networks. "
            "Natural language processing handles text. "
            "Computer vision processes images. "
            "Reinforcement learning trains agents through rewards. "
            "Transfer learning reuses pre-trained models."
        )
        result = _generate_heuristic(content, "AI Overview")

        assert result.title == "AI Overview"
        assert result.root is not None
        assert len(result.root.children) > 0

    @pytest.mark.asyncio
    async def test_generate_mind_map_no_model(self):
        """generate_mind_map without model_fn uses heuristic path."""
        content = "Neural networks learn from data. They use layers of neurons."
        result = await generate_mind_map(content, "Neural Networks")

        assert isinstance(result, MindMapResult)
        assert result.root.label == "Neural Networks"

    @pytest.mark.asyncio
    async def test_generate_mind_map_with_mock_model(self):
        """generate_mind_map with a model function should use AI path."""
        import json

        async def fake_model(prompt: str) -> str:
            return json.dumps({
                "title": "Mock Map",
                "central_concept": "Testing",
                "branches": [
                    {"concept": "Branch 1", "description": "D1", "sub_concepts": ["A", "B"]},
                ],
            })

        result = await generate_mind_map("any content", model_fn=fake_model)

        assert result.title == "Mock Map"
        assert len(result.root.children) == 1
        assert result.root.children[0].label == "Branch 1"

    def test_node_to_dict(self):
        """MindMapNode.to_dict() should include all required fields."""
        node = MindMapNode(id="1", label="Test", level=0, description="Desc")
        d = node.to_dict()
        assert d["id"] == "1"
        assert d["label"] == "Test"
        assert d["level"] == 0
        assert d["description"] == "Desc"
        assert "children" in d


# ── Infographic Engine Tests ─────────────────────────────────


class TestInfographicEngine:
    """Test infographic generation."""

    def test_styles_available(self):
        """All expected infographic styles should be defined."""
        expected = {
            InfographicStyle.SKETCH_NOTE,
            InfographicStyle.SCIENTIFIC,
            InfographicStyle.PROFESSIONAL,
            InfographicStyle.BENTO_GRID,
            InfographicStyle.TIMELINE,
            InfographicStyle.COMPARISON,
            InfographicStyle.STATISTICAL,
            InfographicStyle.STORY,
        }
        assert expected == set(InfographicStyle)

    def test_heuristic_generation_returns_result(self):
        """Heuristic generator produces sections from multi-paragraph text."""
        content = (
            "Artificial intelligence is transforming industries.\n\n"
            "Machine learning enables pattern recognition.\n\n"
            "Deep learning uses layered neural architectures.\n\n"
            "Natural language processing powers chatbots and assistants."
        )
        result = infographic_heuristic(content, "AI Overview", InfographicStyle.PROFESSIONAL)

        assert isinstance(result, InfographicResult)
        assert result.title == "AI Overview"
        assert result.style == InfographicStyle.PROFESSIONAL
        assert len(result.sections) > 0
        assert len(result.color_scheme) > 0

    def test_to_dict_structure(self):
        """to_dict() should include artifact_type and required fields."""
        section = InfographicSection(
            id="s1",
            title="Title",
            content="Content",
            section_type="text",
        )
        result = InfographicResult(
            title="Test",
            style=InfographicStyle.BENTO_GRID,
            sections=[section],
            color_scheme=["#fff"],
        )
        d = result.to_dict()

        assert d["artifact_type"] == "infographic"
        assert d["title"] == "Test"
        assert d["style"] == "bento_grid"
        assert len(d["sections"]) == 1
        assert len(d["color_scheme"]) > 0

    def test_section_to_dict(self):
        """InfographicSection.to_dict() should include all expected fields."""
        section = InfographicSection(
            id="abc",
            title="Header",
            content="Body text",
            section_type="stat",
            data_points=[{"label": "GDP", "value": "3.5T"}],
            visual_hint="bar_chart",
        )
        d = section.to_dict()
        assert d["section_type"] == "stat"
        assert d["visual_hint"] == "bar_chart"
        assert len(d["data_points"]) == 1

    @pytest.mark.asyncio
    async def test_generate_infographic_heuristic(self):
        """generate_infographic without model_fn should succeed."""
        content = "Solar energy is renewable.\n\nWind power is clean.\n\nHydro is reliable."
        result = await generate_infographic(content, "Energy", InfographicStyle.TIMELINE)

        assert isinstance(result, InfographicResult)
        assert result.style == InfographicStyle.TIMELINE

    @pytest.mark.asyncio
    async def test_generate_infographic_with_mock_model(self):
        """generate_infographic with model_fn should use AI path."""
        import json

        async def fake_model(prompt: str) -> str:
            return json.dumps({
                "title": "AI Title",
                "sections": [
                    {
                        "title": "Section 1",
                        "content": "Content 1",
                        "section_type": "text",
                        "data_points": [],
                        "visual_hint": "icon",
                    }
                ],
            })

        result = await generate_infographic("content", model_fn=fake_model)

        assert result.title == "AI Title"
        assert len(result.sections) == 1

    def test_palettes_cover_all_styles(self):
        """Every InfographicStyle should have a colour palette."""
        from src.core.nexus_infographic_engine import _PALETTES
        for style in InfographicStyle:
            assert style in _PALETTES
            assert len(_PALETTES[style]) >= 3


# ── DataTable Engine Tests ────────────────────────────────────


class TestDataTableEngine:
    """Test data table extraction."""

    def test_parse_markdown_table(self):
        """_parse_markdown_table should extract headers and rows."""
        content = (
            "| Name  | Age | Score |\n"
            "|-------|-----|-------|\n"
            "| Alice | 30  | 95    |\n"
            "| Bob   | 25  | 88    |\n"
        )
        result = _parse_markdown_table(content, "Table")

        assert result is not None
        assert len(result.columns) == 3
        assert result.columns[0].name == "Name"
        assert len(result.rows) == 2
        assert result.rows[0]["Name"] == "Alice"

    def test_parse_markdown_table_no_table(self):
        """_parse_markdown_table returns None for plain text."""
        result = _parse_markdown_table("Just some plain text.", "T")
        assert result is None

    def test_parse_delimiter_list_csv(self):
        """_parse_delimiter_list should parse CSV content."""
        content = "Name,Value,Unit\nAlpha,10,kg\nBeta,20,kg\n"
        result = _parse_delimiter_list(content, "CSV Table")

        assert result is not None
        assert len(result.columns) == 3
        assert len(result.rows) == 2
        assert result.rows[0]["Value"] == "10"

    def test_parse_delimiter_list_tsv(self):
        """_parse_delimiter_list should parse tab-separated content."""
        content = "Col1\tCol2\nA\t1\nB\t2\n"
        result = _parse_delimiter_list(content, "TSV")

        assert result is not None
        assert len(result.columns) == 2

    def test_parse_delimiter_list_too_few_columns(self):
        """Single-column delimited content should return None."""
        content = "Alpha\nBeta\nGamma\n"
        result = _parse_delimiter_list(content, "T")
        assert result is None

    def test_infer_types_number(self):
        """_infer_types should detect numeric columns."""
        columns = [TableColumn(name="count"), TableColumn(name="label")]
        rows = [{"count": "10", "label": "foo"}, {"count": "20", "label": "bar"}]
        _infer_types(columns, rows)
        assert columns[0].column_type == ColumnType.NUMBER
        assert columns[1].column_type == ColumnType.TEXT

    def test_infer_types_boolean(self):
        """_infer_types should detect boolean columns."""
        columns = [TableColumn(name="active")]
        rows = [{"active": "true"}, {"active": "false"}]
        _infer_types(columns, rows)
        assert columns[0].column_type == ColumnType.BOOLEAN

    def test_infer_types_url(self):
        """_infer_types should detect URL columns."""
        columns = [TableColumn(name="link")]
        rows = [{"link": "https://example.com"}, {"link": "https://test.org"}]
        _infer_types(columns, rows)
        assert columns[0].column_type == ColumnType.URL

    def test_to_csv(self):
        """DataTableResult.to_csv() should produce valid CSV."""
        columns = [TableColumn(name="x"), TableColumn(name="y")]
        rows = [{"x": "1", "y": "2"}, {"x": "3", "y": "4"}]
        result = DataTableResult(title="T", columns=columns, rows=rows)
        csv_str = result.to_csv()

        lines = [ln.rstrip("\r") for ln in csv_str.strip().split("\n")]
        assert lines[0] == "x,y"
        assert "1,2" in csv_str
        assert "3,4" in csv_str

    def test_to_json(self):
        """DataTableResult.to_json() should include artifact_type."""
        import json
        columns = [TableColumn(name="a")]
        rows = [{"a": "val"}]
        result = DataTableResult(title="T", columns=columns, rows=rows)
        data = json.loads(result.to_json())

        assert data["artifact_type"] == "data_table"
        assert data["title"] == "T"
        assert len(data["rows"]) == 1

    def test_to_dict_structure(self):
        """to_dict() should contain all required top-level keys."""
        result = DataTableResult(
            title="Test",
            columns=[TableColumn(name="col")],
            rows=[{"col": "v"}],
        )
        d = result.to_dict()
        assert d["artifact_type"] == "data_table"
        assert "columns" in d
        assert "rows" in d
        assert "metadata" in d

    @pytest.mark.asyncio
    async def test_extract_data_table_from_markdown(self):
        """extract_data_table should auto-detect a markdown table."""
        content = (
            "Here is the data:\n\n"
            "| Product | Price | Stock |\n"
            "|---------|-------|-------|\n"
            "| Apple   | 1.20  | 100   |\n"
            "| Banana  | 0.50  | 250   |\n"
        )
        result = await extract_data_table(content, "Products")

        assert isinstance(result, DataTableResult)
        assert len(result.columns) == 3
        assert result.columns[0].name == "Product"

    @pytest.mark.asyncio
    async def test_extract_data_table_fallback(self):
        """extract_data_table falls back to key_lines for plain text."""
        content = "Line one\nLine two\nLine three"
        result = await extract_data_table(content)

        assert isinstance(result, DataTableResult)
        assert len(result.rows) == 3

    @pytest.mark.asyncio
    async def test_extract_with_mock_model(self):
        """extract_data_table with model_fn should use AI path."""
        import json

        async def fake_model(prompt: str) -> str:
            return json.dumps({
                "title": "AI Table",
                "columns": [
                    {"name": "Country", "column_type": "text", "description": ""},
                    {"name": "GDP", "column_type": "number", "description": ""},
                ],
                "rows": [
                    {"Country": "USA", "GDP": "26T"},
                    {"Country": "China", "GDP": "18T"},
                ],
            })

        result = await extract_data_table("any content", model_fn=fake_model)

        assert result.title == "AI Table"
        assert len(result.columns) == 2
        assert result.columns[1].column_type == ColumnType.NUMBER
        assert len(result.rows) == 2
