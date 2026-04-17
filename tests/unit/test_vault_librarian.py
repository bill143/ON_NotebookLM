"""
Unit Tests — Vault Librarian AI (Document Classification Engine)

Tests cover:
- DocumentType enum completeness
- Pydantic model validation (LibrarianDecision, VaultDocument, etc.)
- File content extractors (PDF, CSV, XER, ZIP, images, fallback)
- LibrarianAgent classification with mocked AI responses
- Routing instruction and workflow trigger generation
- Confidence threshold → human review flagging
- Error handling (classification failure → UNKNOWN)
- 10+ document type classification scenarios
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.vault.classifier_prompts import (
    CLASSIFICATION_SYSTEM_PROMPT,
    CONFIDENCE_SCORING_GUIDANCE,
    METADATA_EXTRACTION_BY_TYPE,
    SCOPE_CHANGE_DETECTION_PROMPT,
)
from src.vault.document_types import (
    DocumentStatus,
    DocumentType,
    LibrarianDecision,
    RoutingInstruction,
    VaultApproveRequest,
    VaultDocument,
    VaultDocumentResponse,
    VaultRejectRequest,
    VaultUploadRequest,
    VaultUploadResponse,
    WorkflowTrigger,
)
from src.vault.extractors import extract_content
from src.vault.librarian import LibrarianAgent, librarian_agent


# ── Helpers ─────────────────────────────────────────────────


def _mock_ai_response(content: str) -> MagicMock:
    """Build a mock AIResponse with given content."""
    resp = MagicMock()
    resp.content = content
    resp.input_tokens = 100
    resp.output_tokens = 200
    resp.latency_ms = 50.0
    resp.cost_usd = 0.001
    return resp


def _make_classification_json(
    doc_type: str,
    confidence: float = 0.92,
    title: str = "Test Document",
) -> str:
    """Build a JSON string mimicking the AI classification response."""
    return json.dumps(
        {
            "document_type": doc_type,
            "confidence_score": confidence,
            "title": title,
            "description": f"A {doc_type} document",
            "date": "2026-04-10",
            "project_reference": "ONeill HQ Build",
            "classification_reasoning": f"Identified as {doc_type} based on content analysis",
        }
    )


def _make_metadata_json(metadata: dict) -> str:
    """Build a JSON string mimicking the AI metadata extraction response."""
    return json.dumps(metadata)


async def _run_classification(
    agent: LibrarianAgent,
    filename: str,
    file_content: bytes,
    classification_json: str,
    metadata_json: str = "{}",
    scope_json: str | None = None,
) -> LibrarianDecision:
    """Helper to run a classification with mocked AI provider."""
    mock_provider = MagicMock()

    # Build side_effect list based on expected call count
    responses = [
        _mock_ai_response(classification_json),  # classification call
        _mock_ai_response(metadata_json),  # metadata extraction call
    ]
    if scope_json:
        responses.append(_mock_ai_response(scope_json))  # scope change call

    mock_provider.generate = AsyncMock(side_effect=responses)

    mock_manager = MagicMock()
    mock_manager.provision_llm = AsyncMock(return_value=mock_provider)

    with patch("src.agents.nexus_model_layer.model_manager", mock_manager):
        return await agent.classify(
            file_content,
            filename,
            tenant_id="test-tenant",
            project_id="test-project",
        )


# ── DocumentType Enum Tests ────────────────────────────────


class TestDocumentTypeEnum:
    def test_all_21_types_defined(self):
        expected = {
            "RFI", "SUBMITTAL", "SCHEDULE", "PLANS_DRAWINGS", "SPECIFICATIONS",
            "INVOICE", "CHANGE_ORDER", "PERMIT", "COI", "DAILY_REPORT",
            "SAFETY_DOCUMENT", "PAY_APPLICATION", "LIEN_WAIVER", "MEETING_MINUTES",
            "BIM_MODEL", "PHOTO_PROGRESS", "GEOTECHNICAL", "SURVEY", "CLOSEOUT",
            "TRANSMITTAL", "UNKNOWN",
        }
        actual = {member.name for member in DocumentType}
        assert actual == expected

    def test_document_type_is_str_enum(self):
        assert isinstance(DocumentType.RFI, str)
        assert DocumentType.RFI == "rfi"
        assert DocumentType.CHANGE_ORDER == "change_order"

    def test_document_type_from_string(self):
        assert DocumentType("rfi") == DocumentType.RFI
        assert DocumentType("invoice") == DocumentType.INVOICE
        assert DocumentType("unknown") == DocumentType.UNKNOWN

    def test_invalid_document_type_raises(self):
        with pytest.raises(ValueError):
            DocumentType("not_a_type")


class TestDocumentStatusEnum:
    def test_all_statuses_defined(self):
        expected = {
            "PENDING", "PROCESSING", "CLASSIFIED", "AWAITING_REVIEW",
            "APPROVED", "REJECTED", "ERROR",
        }
        actual = {member.name for member in DocumentStatus}
        assert actual == expected


# ── Pydantic Model Tests ───────────────────────────────────


class TestLibrarianDecision:
    def test_default_decision(self):
        decision = LibrarianDecision()
        assert decision.document_type == DocumentType.UNKNOWN
        assert decision.confidence_score == 0.0
        assert decision.requires_human_review is False
        assert decision.metadata == {}
        assert decision.routing_instructions == []
        assert decision.workflow_triggers == []

    def test_decision_with_values(self):
        decision = LibrarianDecision(
            document_type=DocumentType.RFI,
            confidence_score=0.95,
            metadata={"rfi_number": "RFI-042"},
            requires_human_review=False,
            routing_instructions=[
                RoutingInstruction(destination="rfi_tracker", action="create"),
            ],
            workflow_triggers=[
                WorkflowTrigger(
                    trigger_type="review_cycle",
                    target_roles=["architect"],
                    urgency="high",
                ),
            ],
        )
        assert decision.document_type == DocumentType.RFI
        assert decision.confidence_score == 0.95
        assert len(decision.routing_instructions) == 1
        assert len(decision.workflow_triggers) == 1

    def test_confidence_score_bounds(self):
        with pytest.raises(Exception):
            LibrarianDecision(confidence_score=1.5)
        with pytest.raises(Exception):
            LibrarianDecision(confidence_score=-0.1)


class TestVaultModels:
    def test_vault_upload_request(self):
        req = VaultUploadRequest(project_id="proj-123")
        assert req.project_id == "proj-123"
        assert req.title is None
        assert req.tags == []

    def test_vault_document(self):
        doc = VaultDocument(
            project_id="proj-1",
            tenant_id="tenant-1",
            user_id="user-1",
            filename="test.pdf",
        )
        assert doc.status == DocumentStatus.PENDING
        assert doc.decision is None
        assert doc.id  # UUID generated

    def test_vault_upload_response(self):
        resp = VaultUploadResponse(
            id="doc-1",
            filename="plans.pdf",
            status=DocumentStatus.PENDING,
        )
        assert resp.message == "Document queued for classification"

    def test_vault_approve_request(self):
        req = VaultApproveRequest(document_type_override=DocumentType.RFI, notes="Looks good")
        assert req.document_type_override == DocumentType.RFI

    def test_vault_reject_request(self):
        req = VaultRejectRequest(correct_document_type=DocumentType.INVOICE, notes="Wrong type")
        assert req.correct_document_type == DocumentType.INVOICE

    def test_routing_instruction(self):
        ri = RoutingInstruction(destination="rfi_tracker")
        assert ri.action == "create"
        assert ri.priority == 0

    def test_workflow_trigger(self):
        wt = WorkflowTrigger(trigger_type="review_cycle")
        assert wt.urgency == "normal"
        assert wt.target_roles == []


# ── Extractor Tests ─────────────────────────────────────────


class TestExtractors:
    def test_extract_csv(self):
        csv_data = b"Name,Amount,Date\nJohn,1000,2026-01-01\nJane,2000,2026-02-01"
        result = extract_content(csv_data, "invoice_data.csv")
        assert "Name" in result["content"]
        assert "Amount" in result["content"]
        assert result["file_metadata"]["row_count"] == 2

    def test_extract_xer(self):
        xer_data = (
            b"%T\tPROJECT\n"
            b"%R\tPROJ1\tONeill HQ\tBuild\t2026-04-01\n"
            b"%T\tTASK\n"
            b"%R\ttask1\tExcavation\n"
            b"%R\ttask2\tFoundation\n"
            b"%R\ttask3\tFraming\n"
        )
        result = extract_content(xer_data, "schedule.xer")
        assert "Primavera P6" in result["content"]
        assert result["file_metadata"]["activity_count"] == 3

    def test_extract_image(self):
        result = extract_content(b"\x89PNG\r\n\x1a\n", "site_photo.png")
        assert "Image file" in result["content"]
        assert result["file_metadata"].get("requires_vision") is True

    def test_extract_zip(self):
        import io
        import zipfile

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("drawing_A1.pdf", "fake pdf")
            zf.writestr("specs.docx", "fake docx")
        result = extract_content(buf.getvalue(), "submittal_package.zip")
        assert "drawing_A1.pdf" in result["content"]
        assert result["file_metadata"]["file_count"] == 2

    def test_extract_media(self):
        result = extract_content(b"fake_mp4_data", "drone_flight.mp4")
        assert "Media file" in result["content"]
        assert result["file_metadata"]["file_type"] == "mp4"

    def test_extract_dwg(self):
        result = extract_content(b"binary_dwg_data", "A-101_Floor_Plan.dwg")
        assert "CAD Drawing" in result["content"]

    def test_extract_rvt(self):
        result = extract_content(b"binary_rvt_data", "ARCH-Model.rvt")
        assert "Revit BIM Model" in result["content"]
        assert result["file_metadata"]["discipline"] == "architectural"

    def test_extract_rvt_structural(self):
        result = extract_content(b"data", "STRUCT-Model.rvt")
        assert result["file_metadata"]["discipline"] == "structural"

    def test_extract_geojson(self):
        geo = json.dumps({
            "type": "FeatureCollection",
            "features": [
                {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}},
            ],
        }).encode()
        result = extract_content(geo, "site_survey.geojson")
        assert result["file_metadata"]["feature_count"] == 1

    def test_extract_fallback(self):
        result = extract_content(b"some data", "mystery_file.xyz")
        assert "File: mystery_file.xyz" in result["content"]

    def test_content_cap_at_50k(self):
        # Very long content should be capped
        long_csv = ("a,b\n" + "x,y\n" * 50_000).encode()
        result = extract_content(long_csv, "big.csv")
        assert len(result["content"]) <= 50_000


# ── Classifier Prompts Tests ────────────────────────────────


class TestClassifierPrompts:
    def test_classification_prompt_contains_all_types(self):
        for doc_type in DocumentType:
            assert doc_type.value in CLASSIFICATION_SYSTEM_PROMPT

    def test_metadata_prompts_for_key_types(self):
        key_types = ["rfi", "submittal", "invoice", "change_order", "schedule", "coi", "permit"]
        for t in key_types:
            assert t in METADATA_EXTRACTION_BY_TYPE

    def test_scope_change_prompt_exists(self):
        assert "scope change" in SCOPE_CHANGE_DETECTION_PROMPT.lower()

    def test_confidence_guidance_contains_thresholds(self):
        assert "0.75" in CONFIDENCE_SCORING_GUIDANCE


# ── LibrarianAgent Classification Tests ─────────────────────


class TestLibrarianAgentClassification:
    """10+ document classification scenarios with mocked AI responses."""

    @pytest.mark.asyncio
    async def test_classify_rfi(self):
        """Scenario 1: RFI document with scope change detection."""
        agent = LibrarianAgent()
        decision = await _run_classification(
            agent,
            "RFI-042_Structural_Clarification.pdf",
            b"fake pdf content",
            _make_classification_json("rfi", 0.96, "RFI #042 — Structural Detail Clarification"),
            _make_metadata_json({
                "rfi_number": "RFI-042",
                "subject": "Structural Detail at Grid B-4",
                "submitted_by": "O'Neill Contractors",
                "submitted_to": "Smith Architecture",
                "date_required": "2026-04-20",
                "discipline": "structural",
                "spec_section": "03 30 00",
                "is_scope_change": False,
            }),
            scope_json=json.dumps({
                "is_scope_change": False,
                "scope_change_confidence": 0.15,
                "reasoning": "Standard clarification question",
                "recommended_action": "proceed",
            }),
        )
        assert decision.document_type == DocumentType.RFI
        assert decision.confidence_score == 0.96
        assert decision.requires_human_review is False
        assert decision.metadata["rfi_number"] == "RFI-042"
        assert any(r.destination == "rfi_tracker" for r in decision.routing_instructions)

    @pytest.mark.asyncio
    async def test_classify_submittal(self):
        """Scenario 2: Submittal document."""
        agent = LibrarianAgent()
        decision = await _run_classification(
            agent,
            "SUB-015_HVAC_Equipment.pdf",
            b"fake pdf",
            _make_classification_json("submittal", 0.93, "Submittal #015 — HVAC Equipment Data"),
            _make_metadata_json({
                "submittal_number": "SUB-015",
                "spec_section": "23 00 00",
                "trade": "mechanical",
                "revision": "A",
                "submitted_by": "ABC Mechanical",
                "review_required_by": "2026-05-01",
            }),
        )
        assert decision.document_type == DocumentType.SUBMITTAL
        assert decision.confidence_score == 0.93
        assert decision.metadata["trade"] == "mechanical"
        assert any(r.destination == "submittal_log" for r in decision.routing_instructions)

    @pytest.mark.asyncio
    async def test_classify_invoice(self):
        """Scenario 3: Invoice document."""
        agent = LibrarianAgent()
        decision = await _run_classification(
            agent,
            "INV-2026-0389.pdf",
            b"fake pdf",
            _make_classification_json("invoice", 0.97, "Invoice #2026-0389"),
            _make_metadata_json({
                "invoice_number": "2026-0389",
                "vendor": "Steel Supply Co.",
                "amount": 45750.00,
                "period_of_performance": "March 2026",
                "contract_number": "SC-001",
            }),
        )
        assert decision.document_type == DocumentType.INVOICE
        assert decision.metadata["amount"] == 45750.00
        assert any(r.destination == "cost_control" for r in decision.routing_instructions)

    @pytest.mark.asyncio
    async def test_classify_change_order(self):
        """Scenario 4: Change Order document."""
        agent = LibrarianAgent()
        decision = await _run_classification(
            agent,
            "CO-007_Foundation_Redesign.pdf",
            b"fake pdf",
            _make_classification_json("change_order", 0.91, "Change Order #007"),
            _make_metadata_json({
                "co_number": "CO-007",
                "description": "Foundation redesign due to unforeseen soil conditions",
                "amount": 125000.00,
                "reason_code": "unforeseen condition",
                "is_owner_directed": False,
            }),
        )
        assert decision.document_type == DocumentType.CHANGE_ORDER
        assert decision.metadata["is_owner_directed"] is False
        assert any(
            t.trigger_type == "cost_impact" for t in decision.workflow_triggers
        )

    @pytest.mark.asyncio
    async def test_classify_schedule_xer(self):
        """Scenario 5: Primavera P6 schedule file."""
        agent = LibrarianAgent()
        xer_data = (
            b"%T\tPROJECT\n%R\tP1\tONeill HQ\tDesc\t2026-04-01\n"
            b"%T\tTASK\n%R\tt1\n%R\tt2\n"
        )
        decision = await _run_classification(
            agent,
            "Baseline_Schedule_Rev3.xer",
            xer_data,
            _make_classification_json("schedule", 0.98, "Baseline Schedule Rev 3"),
            _make_metadata_json({
                "schedule_type": "baseline",
                "data_date": "2026-04-01",
                "activity_count": 342,
            }),
        )
        assert decision.document_type == DocumentType.SCHEDULE
        assert decision.confidence_score == 0.98

    @pytest.mark.asyncio
    async def test_classify_plans_drawings(self):
        """Scenario 6: Architectural drawings."""
        agent = LibrarianAgent()
        decision = await _run_classification(
            agent,
            "A-101_Floor_Plans.dwg",
            b"binary dwg data",
            _make_classification_json("plans_drawings", 0.95, "Architectural Floor Plans"),
            _make_metadata_json({
                "discipline": "architectural",
                "sheet_count": 12,
                "revision": "C",
                "drawing_numbers": ["A-101", "A-102", "A-103"],
            }),
        )
        assert decision.document_type == DocumentType.PLANS_DRAWINGS
        assert decision.metadata["discipline"] == "architectural"

    @pytest.mark.asyncio
    async def test_classify_coi(self):
        """Scenario 7: Certificate of Insurance."""
        agent = LibrarianAgent()
        decision = await _run_classification(
            agent,
            "COI_ABCMechanical_2026.pdf",
            b"fake pdf",
            _make_classification_json("coi", 0.94, "Certificate of Insurance — ABC Mechanical"),
            _make_metadata_json({
                "insured_name": "ABC Mechanical, Inc.",
                "policy_number": "GL-2026-45678",
                "expiration_date": "2027-01-15",
                "coverage_types": ["general_liability", "workers_comp", "auto"],
                "coverage_amounts": {"general_liability": "$2,000,000"},
            }),
        )
        assert decision.document_type == DocumentType.COI
        assert "general_liability" in decision.metadata["coverage_types"]
        assert any(
            t.trigger_type == "deadline_tracking" for t in decision.workflow_triggers
        )

    @pytest.mark.asyncio
    async def test_classify_permit(self):
        """Scenario 8: Building permit."""
        agent = LibrarianAgent()
        decision = await _run_classification(
            agent,
            "Building_Permit_2026-BP-1234.pdf",
            b"fake pdf",
            _make_classification_json("permit", 0.96, "Building Permit #2026-BP-1234"),
            _make_metadata_json({
                "permit_number": "2026-BP-1234",
                "issuing_authority": "City of Springfield",
                "permit_type": "building",
                "expiration_date": "2027-04-15",
            }),
        )
        assert decision.document_type == DocumentType.PERMIT
        assert decision.metadata["permit_type"] == "building"

    @pytest.mark.asyncio
    async def test_classify_daily_report(self):
        """Scenario 9: Daily field report."""
        agent = LibrarianAgent()
        csv_data = b"Date,Weather,Workers,Activity\n2026-04-10,Sunny,45,Foundation pour"
        decision = await _run_classification(
            agent,
            "Daily_Report_2026-04-10.csv",
            csv_data,
            _make_classification_json("daily_report", 0.88, "Daily Report — April 10, 2026"),
            _make_metadata_json({
                "report_date": "2026-04-10",
                "weather": "Sunny, 72°F",
                "manpower_count": 45,
                "activities_performed": ["Foundation pour — Section A"],
                "superintendent": "Mike Johnson",
            }),
        )
        assert decision.document_type == DocumentType.DAILY_REPORT
        assert decision.metadata["manpower_count"] == 45

    @pytest.mark.asyncio
    async def test_classify_safety_document(self):
        """Scenario 10: Safety incident report."""
        agent = LibrarianAgent()
        decision = await _run_classification(
            agent,
            "Incident_Report_2026-04-08.pdf",
            b"fake pdf",
            _make_classification_json("safety_document", 0.92, "Safety Incident Report"),
            _make_metadata_json({
                "document_subtype": "incident report",
                "date": "2026-04-08",
                "incident_type": "near miss",
                "location": "Building A, Floor 3",
                "prepared_by": "Tom Safety",
            }),
        )
        assert decision.document_type == DocumentType.SAFETY_DOCUMENT
        assert any(
            t.trigger_type == "notification" for t in decision.workflow_triggers
        )

    @pytest.mark.asyncio
    async def test_classify_pay_application(self):
        """Scenario 11: AIA G702 Pay Application."""
        agent = LibrarianAgent()
        decision = await _run_classification(
            agent,
            "Pay_App_07_AIA_G702.pdf",
            b"fake pdf",
            _make_classification_json("pay_application", 0.97, "Pay Application #7"),
            _make_metadata_json({
                "application_number": "7",
                "period_to": "2026-03-31",
                "contract_sum": 5_200_000.00,
                "total_completed": 2_340_000.00,
                "retainage": 234_000.00,
                "current_payment_due": 580_000.00,
                "form_type": "AIA G702",
            }),
        )
        assert decision.document_type == DocumentType.PAY_APPLICATION
        assert decision.metadata["form_type"] == "AIA G702"

    @pytest.mark.asyncio
    async def test_classify_meeting_minutes(self):
        """Scenario 12: OAC Meeting Minutes."""
        agent = LibrarianAgent()
        decision = await _run_classification(
            agent,
            "OAC_Meeting_Minutes_2026-04-05.docx",
            b"fake docx data",
            _make_classification_json("meeting_minutes", 0.89, "OAC Meeting Minutes — April 5"),
            _make_metadata_json({
                "meeting_type": "OAC",
                "meeting_date": "2026-04-05",
                "attendees": ["Owner", "Architect", "GC"],
                "action_items_count": 8,
            }),
        )
        assert decision.document_type == DocumentType.MEETING_MINUTES


# ── Confidence Threshold Tests ──────────────────────────────


class TestConfidenceThresholds:
    @pytest.mark.asyncio
    async def test_low_confidence_flags_human_review(self):
        """Documents below 0.75 confidence must be flagged."""
        agent = LibrarianAgent()
        decision = await _run_classification(
            agent,
            "ambiguous_document.pdf",
            b"fake pdf",
            _make_classification_json("specifications", 0.65, "Ambiguous Document"),
            _make_metadata_json({}),
        )
        assert decision.requires_human_review is True
        assert decision.confidence_score == 0.65

    @pytest.mark.asyncio
    async def test_high_confidence_no_review(self):
        """Documents at or above 0.75 should not require review."""
        agent = LibrarianAgent()
        decision = await _run_classification(
            agent,
            "clear_invoice.pdf",
            b"fake pdf",
            _make_classification_json("invoice", 0.88, "Clear Invoice"),
            _make_metadata_json({"invoice_number": "INV-001"}),
        )
        assert decision.requires_human_review is False

    @pytest.mark.asyncio
    async def test_unknown_type_always_flags_review(self):
        """UNKNOWN type always requires human review regardless of confidence."""
        agent = LibrarianAgent()
        decision = await _run_classification(
            agent,
            "mystery_file.bin",
            b"binary data",
            _make_classification_json("unknown", 0.80, "Unknown Document"),
        )
        assert decision.document_type == DocumentType.UNKNOWN
        assert decision.requires_human_review is True


# ── Error Handling Tests ────────────────────────────────────


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_classification_failure_returns_unknown(self):
        """AI call failure should return UNKNOWN, not crash."""
        agent = LibrarianAgent()

        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(side_effect=RuntimeError("API timeout"))

        mock_manager = MagicMock()
        mock_manager.provision_llm = AsyncMock(return_value=mock_provider)

        with patch("src.agents.nexus_model_layer.model_manager", mock_manager):
            decision = await agent.classify(
                b"some content",
                "broken_file.pdf",
                tenant_id="test",
            )

        assert decision.document_type == DocumentType.UNKNOWN
        assert decision.confidence_score == 0.0
        assert decision.requires_human_review is True
        assert "error" in decision.metadata

    @pytest.mark.asyncio
    async def test_invalid_json_from_ai_returns_unknown(self):
        """Malformed AI response should degrade gracefully."""
        agent = LibrarianAgent()

        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(
            return_value=_mock_ai_response("Not valid JSON at all!")
        )

        mock_manager = MagicMock()
        mock_manager.provision_llm = AsyncMock(return_value=mock_provider)

        with patch("src.agents.nexus_model_layer.model_manager", mock_manager):
            decision = await agent.classify(
                b"content",
                "test.pdf",
                tenant_id="test",
            )

        # Should not crash — empty JSON parse returns {} → UNKNOWN
        assert decision.document_type == DocumentType.UNKNOWN

    @pytest.mark.asyncio
    async def test_ai_returns_unknown_type_string(self):
        """AI returning an invalid type string should fall back to UNKNOWN."""
        agent = LibrarianAgent()

        bad_json = json.dumps({
            "document_type": "totally_made_up_type",
            "confidence_score": 0.5,
            "title": "Weird doc",
        })

        mock_provider = MagicMock()
        mock_provider.generate = AsyncMock(return_value=_mock_ai_response(bad_json))

        mock_manager = MagicMock()
        mock_manager.provision_llm = AsyncMock(return_value=mock_provider)

        with patch("src.agents.nexus_model_layer.model_manager", mock_manager):
            decision = await agent.classify(b"content", "test.pdf", tenant_id="test")

        assert decision.document_type == DocumentType.UNKNOWN


# ── Routing & Trigger Tests ─────────────────────────────────


class TestRoutingAndTriggers:
    def test_rfi_routing(self):
        agent = LibrarianAgent()
        routing = agent._build_routing(DocumentType.RFI)
        assert len(routing) > 0
        destinations = [r.destination for r in routing]
        assert "rfi_tracker" in destinations

    def test_change_order_triggers(self):
        agent = LibrarianAgent()
        triggers = agent._build_triggers(DocumentType.CHANGE_ORDER)
        assert len(triggers) > 0
        assert any(t.trigger_type == "cost_impact" for t in triggers)

    def test_unknown_type_has_no_routing(self):
        agent = LibrarianAgent()
        routing = agent._build_routing(DocumentType.UNKNOWN)
        assert routing == []

    def test_safety_document_triggers_notification(self):
        agent = LibrarianAgent()
        triggers = agent._build_triggers(DocumentType.SAFETY_DOCUMENT)
        assert any(t.trigger_type == "notification" for t in triggers)
        assert any("safety_officer" in t.target_roles for t in triggers)


# ── JSON Parsing Tests ──────────────────────────────────────


class TestJsonParsing:
    def test_parse_clean_json(self):
        raw = '{"key": "value", "num": 42}'
        result = LibrarianAgent._parse_json_response(raw, "test")
        assert result == {"key": "value", "num": 42}

    def test_parse_json_with_markdown_fences(self):
        raw = '```json\n{"key": "value"}\n```'
        result = LibrarianAgent._parse_json_response(raw, "test")
        assert result == {"key": "value"}

    def test_parse_invalid_json_returns_empty(self):
        raw = "This is not JSON"
        result = LibrarianAgent._parse_json_response(raw, "test")
        assert result == {}

    def test_parse_json_with_whitespace(self):
        raw = '  \n  {"key": "value"}  \n  '
        result = LibrarianAgent._parse_json_response(raw, "test")
        assert result == {"key": "value"}


# ── Global Singleton Test ───────────────────────────────────


class TestSingleton:
    def test_librarian_agent_singleton_exists(self):
        assert librarian_agent is not None
        assert isinstance(librarian_agent, LibrarianAgent)
