"""
Tests — Vault Document Workflow Agents
Minimum 5 test cases per workflow. All external calls mocked.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.vault.workflows.base_workflow import (
    ActionRecord,
    BaseWorkflow,
    LibrarianDecision,
    LogEntry,
    NotificationChannel,
    NotificationRecord,
    ReminderSchedule,
    Urgency,
    WorkflowResult,
)
from src.vault.workflows.notification_service import (
    EmailMessage,
    InAppMessage,
    LetterTemplate,
    NotificationService,
    notification_service,
)
from src.vault.workflows.workflow_router import (
    DOCUMENT_TYPE_TO_WORKFLOW,
    _get_workflow,
    execute_workflow,
)


# ── Fixtures ────────────────────────────────────────────────


@pytest.fixture
def mock_celery():
    """Mock the Celery app so no tasks are actually dispatched."""
    with patch("src.worker.celery_app") as mock_app:
        mock_app.send_task = MagicMock()
        yield mock_app


@pytest.fixture
def mock_notifications():
    """Mock the notification service so no emails/push notifications are sent."""
    with (
        patch.object(notification_service, "send_email", new_callable=AsyncMock) as mock_email,
        patch.object(notification_service, "send_in_app", new_callable=AsyncMock) as mock_in_app,
    ):
        mock_email.return_value = EmailMessage(
            to="test@test.com", subject="Test", body="Test"
        )
        mock_in_app.return_value = InAppMessage(
            user_id="test", title="Test", message="Test"
        )
        yield {"email": mock_email, "in_app": mock_in_app}


def _make_decision(**kwargs) -> LibrarianDecision:
    defaults = {
        "document_type": "UNKNOWN",
        "metadata": {},
        "confidence_score": 0.95,
        "routing_instructions": {},
        "workflow_triggers": [],
        "requires_human_review": False,
    }
    defaults.update(kwargs)
    return LibrarianDecision(**defaults)


def _make_document(**kwargs) -> dict:
    defaults = {"id": str(uuid.uuid4()), "title": "Test Document"}
    defaults.update(kwargs)
    return defaults


# ═══════════════════════════════════════════════════════════════
# 1. Base Workflow & Models Tests
# ═══════════════════════════════════════════════════════════════


class TestBaseWorkflowModels:
    def test_workflow_result_defaults(self):
        result = WorkflowResult(success=True)
        assert result.success is True
        assert result.actions_taken == []
        assert result.notifications_sent == []
        assert result.records_created == []
        assert result.next_steps == []
        assert result.error_message is None

    def test_action_record_timestamp(self):
        record = ActionRecord(action="test")
        assert record.action == "test"
        assert record.timestamp is not None

    def test_notification_record(self):
        record = NotificationRecord(
            recipient="user1",
            channel=NotificationChannel.EMAIL,
            subject="Test",
        )
        assert record.recipient == "user1"
        assert record.urgency == Urgency.NORMAL

    def test_log_entry_auto_id(self):
        entry = LogEntry(
            workflow_type="test",
            document_id="doc1",
            project_id="proj1",
            user_id="user1",
            action="test_action",
        )
        assert entry.id is not None
        assert entry.action == "test_action"

    def test_reminder_schedule(self):
        schedule = ReminderSchedule(
            deadline=datetime.now(UTC),
            recipient="user1",
            message="Test reminder",
            reminder_offsets_days=[7, 2],
            project_id="proj1",
            document_id="doc1",
            document_type="rfi",
        )
        assert len(schedule.reminder_offsets_days) == 2

    def test_librarian_decision(self):
        decision = _make_decision(
            document_type="RFI",
            confidence_score=0.97,
            metadata={"discipline": "structural"},
        )
        assert decision.document_type == "RFI"
        assert decision.confidence_score == 0.97


# ═══════════════════════════════════════════════════════════════
# 2. Notification Service Tests
# ═══════════════════════════════════════════════════════════════


class TestNotificationService:
    @pytest.mark.asyncio
    async def test_send_email(self):
        svc = NotificationService()
        msg = await svc.send_email("test@test.com", "Subject", "Body")
        assert msg.to == "test@test.com"
        assert msg.subject == "Subject"

    @pytest.mark.asyncio
    async def test_send_in_app(self):
        svc = NotificationService()
        msg = await svc.send_in_app("user1", "Title", "Message", "high")
        assert msg.user_id == "user1"
        assert msg.urgency == "high"

    def test_generate_overdue_rfi_letter(self):
        svc = NotificationService()
        letter = svc.generate_formal_letter(
            LetterTemplate.OVERDUE_RFI,
            {
                "project_name": "ONC-2026-001",
                "rfi_number": "RFI-ONC-0001",
                "subject": "Foundation Details",
                "reviewer_name": "John Smith",
                "submitted_date": "2026-03-01",
                "due_date": "2026-03-15",
                "days_overdue": "3",
                "sender_name": "Bill Asmar",
            },
        )
        assert "RFI-ONC-0001" in letter
        assert "John Smith" in letter
        assert "3" in letter

    def test_generate_insurance_expired_letter(self):
        svc = NotificationService()
        letter = svc.generate_formal_letter(
            LetterTemplate.INSURANCE_EXPIRED,
            {
                "project_name": "ONC-2026-001",
                "subcontractor_name": "ABC Plumbing",
                "policy_number": "POL-12345",
                "expiration_date": "2026-04-01",
                "sender_name": "Contracts Admin",
            },
        )
        assert "ABC Plumbing" in letter
        assert "SUSPENDED" in letter

    def test_generate_scope_change_letter(self):
        svc = NotificationService()
        letter = svc.generate_formal_letter(
            LetterTemplate.SCOPE_CHANGE_NOTICE,
            {
                "project_name": "ONC-2026-001",
                "rfi_number": "RFI-ONC-0005",
                "subject": "Wall Modifications",
                "recipient_name": "Owner Rep",
                "change_description": "Additional walls needed",
                "estimated_impact": "$50,000",
                "sender_name": "Bill Asmar",
            },
        )
        assert "RFI-ONC-0005" in letter
        assert "Additional walls needed" in letter

    def test_invalid_template_raises(self):
        svc = NotificationService()
        with pytest.raises(ValueError, match="Unknown letter template"):
            svc.generate_formal_letter("nonexistent", {})  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════
# 3. RFI Workflow Tests
# ═══════════════════════════════════════════════════════════════


class TestRFIWorkflow:
    @pytest.mark.asyncio
    async def test_new_rfi_creates_record(self, mock_celery, mock_notifications):
        from src.vault.workflows.rfi_workflow import RFIWorkflow

        wf = RFIWorkflow()
        doc = _make_document(title="RFI - Foundation Query")
        decision = _make_decision(
            document_type="RFI",
            metadata={
                "project_code": "ONC",
                "rfi_sequence": 42,
                "discipline": "structural",
                "submitter": "contractor_1",
                "distribution_list": ["pm@onc.com", "arch@firm.com"],
                "project_manager": "pm@onc.com",
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        assert any(r.get("rfi_number") == "RFI-ONC-0042" for r in result.records_created)
        assert len(result.notifications_sent) > 0
        assert any("RFI-ONC-0042" in a.details.get("rfi_number", "") for a in result.actions_taken)

    @pytest.mark.asyncio
    async def test_rfi_assigns_correct_discipline_reviewer(self, mock_celery, mock_notifications):
        from src.vault.workflows.rfi_workflow import DISCIPLINE_REVIEWERS, RFIWorkflow

        wf = RFIWorkflow()
        for discipline, expected_reviewer in DISCIPLINE_REVIEWERS.items():
            wf._reset()
            doc = _make_document()
            decision = _make_decision(
                document_type="RFI",
                metadata={"discipline": discipline, "rfi_sequence": 1},
            )
            result = await wf.execute(doc, decision, "proj-001", "user-1")
            assert result.success is True
            rfi_record = next(
                (r for r in result.records_created if r.get("rfi_number")), None
            )
            assert rfi_record is not None
            assert rfi_record["reviewer"] == expected_reviewer

    @pytest.mark.asyncio
    async def test_rfi_due_date_default_14_days(self, mock_celery, mock_notifications):
        from src.vault.workflows.rfi_workflow import RFIWorkflow

        wf = RFIWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="RFI",
            metadata={"rfi_sequence": 1},
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        rfi_record = next((r for r in result.records_created if r.get("rfi_number")), None)
        assert rfi_record is not None
        due = datetime.fromisoformat(rfi_record["due_date"])
        expected = datetime.now(UTC) + timedelta(days=14)
        assert abs((due - expected).total_seconds()) < 60

    @pytest.mark.asyncio
    async def test_rfi_due_date_from_document(self, mock_celery, mock_notifications):
        from src.vault.workflows.rfi_workflow import RFIWorkflow

        wf = RFIWorkflow()
        custom_due = (datetime.now(UTC) + timedelta(days=7)).isoformat()
        doc = _make_document()
        decision = _make_decision(
            document_type="RFI",
            metadata={"rfi_sequence": 1, "due_date": custom_due},
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        rfi_record = next((r for r in result.records_created if r.get("rfi_number")), None)
        assert rfi_record is not None
        assert rfi_record["due_date"][:19] == custom_due[:19]

    @pytest.mark.asyncio
    async def test_rfi_schedules_reminders(self, mock_celery, mock_notifications):
        from src.vault.workflows.rfi_workflow import RFIWorkflow

        wf = RFIWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="RFI",
            metadata={"rfi_sequence": 1, "principal_in_charge": "pic@onc.com"},
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        # Celery send_task should be called for T-2, T-0, T+1, T+7
        assert mock_celery.send_task.call_count >= 4

    @pytest.mark.asyncio
    async def test_rfi_response_updates_status(self, mock_celery, mock_notifications):
        from src.vault.workflows.rfi_workflow import RFIWorkflow

        wf = RFIWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="RFI",
            metadata={
                "rfi_number": "RFI-ONC-0001",
                "rfi_id": "rfi-uuid-123",
                "is_response": True,
                "distribution_list": ["pm@onc.com"],
            },
            workflow_triggers=["response"],
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        status_update = next(
            (r for r in result.records_created if r.get("type") == "rfi_status_update"),
            None,
        )
        assert status_update is not None
        assert status_update["status"] == "RESPONDED"

    @pytest.mark.asyncio
    async def test_rfi_response_detects_scope_change(self, mock_celery, mock_notifications):
        from src.vault.workflows.rfi_workflow import RFIWorkflow

        wf = RFIWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="RFI",
            metadata={
                "rfi_number": "RFI-ONC-0005",
                "is_response": True,
                "scope_change_detected": True,
                "project_manager": "pm@onc.com",
            },
            workflow_triggers=["response"],
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        pco = next(
            (r for r in result.records_created if r.get("type") == "potential_change_order"),
            None,
        )
        assert pco is not None
        assert "Review Potential Change Order" in result.next_steps

    @pytest.mark.asyncio
    async def test_rfi_response_keyword_scope_detection(self, mock_celery, mock_notifications):
        from src.vault.workflows.rfi_workflow import RFIWorkflow

        wf = RFIWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="RFI",
            metadata={
                "rfi_number": "RFI-ONC-0010",
                "is_response": True,
                "response_text": "This requires additional work and scope modification",
                "project_manager": "pm@onc.com",
            },
            workflow_triggers=["response"],
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        pco = next(
            (r for r in result.records_created if r.get("type") == "potential_change_order"),
            None,
        )
        assert pco is not None

    @pytest.mark.asyncio
    async def test_rfi_workflow_error_handled(self, mock_notifications):
        from src.vault.workflows.rfi_workflow import RFIWorkflow

        wf = RFIWorkflow()
        doc = _make_document()
        decision = _make_decision(document_type="RFI", metadata={"rfi_sequence": 1})

        # Force an error by not mocking celery (import will fail gracefully)
        with patch("src.worker.celery_app", side_effect=Exception("Connection refused")):
            # The workflow catches exceptions internally
            result = await wf.execute(doc, decision, "proj-001", "user-1")
            # Should not crash
            assert isinstance(result, WorkflowResult)


# ═══════════════════════════════════════════════════════════════
# 4. Submittal Workflow Tests
# ═══════════════════════════════════════════════════════════════


class TestSubmittalWorkflow:
    @pytest.mark.asyncio
    async def test_new_submittal_creates_record(self, mock_celery, mock_notifications):
        from src.vault.workflows.submittal_workflow import SubmittalWorkflow

        wf = SubmittalWorkflow()
        doc = _make_document(title="Shop Drawing - Steel")
        decision = _make_decision(
            document_type="SUBMITTAL",
            metadata={"spec_section": "0510", "revision": 0, "title": "Steel Beams"},
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        sub = next((r for r in result.records_created if r.get("submittal_number")), None)
        assert sub is not None
        assert sub["submittal_number"] == "SUB-0510-00"
        assert sub["status"] == "SUBMITTED"

    @pytest.mark.asyncio
    async def test_submittal_assigns_correct_reviewer(self, mock_celery, mock_notifications):
        from src.vault.workflows.submittal_workflow import SubmittalWorkflow

        wf = SubmittalWorkflow()
        # Spec section 23 → HVAC → mep_engineer
        doc = _make_document()
        decision = _make_decision(
            document_type="SUBMITTAL",
            metadata={"spec_section": "2300", "revision": 0},
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        sub = next((r for r in result.records_created if r.get("submittal_number")), None)
        assert sub is not None
        assert sub["reviewer"] == "mep_engineer"

    @pytest.mark.asyncio
    async def test_submittal_21_day_review_period(self, mock_celery, mock_notifications):
        from src.vault.workflows.submittal_workflow import SubmittalWorkflow

        wf = SubmittalWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="SUBMITTAL",
            metadata={"spec_section": "0900", "revision": 0},
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        sub = next((r for r in result.records_created if r.get("submittal_number")), None)
        due = datetime.fromisoformat(sub["due_date"])
        expected = datetime.now(UTC) + timedelta(days=21)
        assert abs((due - expected).total_seconds()) < 60

    @pytest.mark.asyncio
    async def test_submittal_approval(self, mock_celery, mock_notifications):
        from src.vault.workflows.submittal_workflow import SubmittalWorkflow

        wf = SubmittalWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="SUBMITTAL",
            metadata={
                "is_review_action": True,
                "submittal_number": "SUB-0510-00",
                "review_action": "APPROVED",
                "submitter": "contractor@test.com",
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        update = next(
            (r for r in result.records_created if r.get("type") == "submittal_status_update"),
            None,
        )
        assert update is not None
        assert update["status"] == "APPROVED"

    @pytest.mark.asyncio
    async def test_submittal_rejection_increments_revision(self, mock_celery, mock_notifications):
        from src.vault.workflows.submittal_workflow import SubmittalWorkflow

        wf = SubmittalWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="SUBMITTAL",
            metadata={
                "is_review_action": True,
                "submittal_number": "SUB-0510-00",
                "review_action": "REVISE_AND_RESUBMIT",
                "revision": 0,
                "submitter": "contractor@test.com",
                "review_comments": "Insufficient detail on connections",
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        rev = next(
            (r for r in result.records_created if r.get("type") == "revision_increment"),
            None,
        )
        assert rev is not None
        assert rev["new_revision"] == 1


# ═══════════════════════════════════════════════════════════════
# 5. Invoice Workflow Tests
# ═══════════════════════════════════════════════════════════════


class TestInvoiceWorkflow:
    @pytest.mark.asyncio
    async def test_invoice_creates_record(self, mock_celery, mock_notifications):
        from src.vault.workflows.invoice_workflow import InvoiceWorkflow

        wf = InvoiceWorkflow()
        doc = _make_document(title="Invoice #1234")
        decision = _make_decision(
            document_type="INVOICE",
            metadata={
                "invoice_number": "INV-1234",
                "vendor": "ABC Electric",
                "amount": 50000.00,
                "accounting_contact": "accounting@onc.com",
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        inv = next((r for r in result.records_created if r.get("invoice_number")), None)
        assert inv is not None
        assert inv["invoice_number"] == "INV-1234"
        assert inv["vendor"] == "ABC Electric"
        assert inv["status"] == "RECEIVED"

    @pytest.mark.asyncio
    async def test_invoice_exceeds_contract_balance(self, mock_celery, mock_notifications):
        from src.vault.workflows.invoice_workflow import InvoiceWorkflow

        wf = InvoiceWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="INVOICE",
            metadata={
                "invoice_number": "INV-5678",
                "vendor": "Steel Co",
                "amount": 200000.00,
                "contract_value": 500000.00,
                "amount_previously_billed": 400000.00,  # Only 100k remaining
                "project_manager": "pm@onc.com",
                "accounting_contact": "accounting@onc.com",
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        inv = next((r for r in result.records_created if r.get("invoice_number")), None)
        assert "EXCEEDS_CONTRACT_BALANCE" in inv.get("flags", [])

    @pytest.mark.asyncio
    async def test_invoice_duplicate_detection(self, mock_celery, mock_notifications):
        from src.vault.workflows.invoice_workflow import InvoiceWorkflow

        wf = InvoiceWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="INVOICE",
            metadata={
                "invoice_number": "INV-DUP",
                "vendor": "Dupe LLC",
                "amount": 1000.00,
                "existing_invoice_numbers": ["INV-DUP", "INV-001"],
                "accounting_contact": "accounting@onc.com",
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        assert any("duplicate" in s.lower() for s in result.next_steps)

    @pytest.mark.asyncio
    async def test_invoice_net30_reminder(self, mock_celery, mock_notifications):
        from src.vault.workflows.invoice_workflow import InvoiceWorkflow

        wf = InvoiceWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="INVOICE",
            metadata={
                "invoice_number": "INV-NET30",
                "vendor": "Test Vendor",
                "amount": 5000.00,
                "accounting_contact": "accounting@onc.com",
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        # Should schedule a reminder
        assert mock_celery.send_task.call_count >= 1

    @pytest.mark.asyncio
    async def test_invoice_g702_detection(self, mock_celery, mock_notifications):
        from src.vault.workflows.invoice_workflow import InvoiceWorkflow

        wf = InvoiceWorkflow()
        doc = _make_document(title="G702 Application for Payment #3")
        decision = _make_decision(
            document_type="INVOICE",
            metadata={
                "invoice_number": "PAY-003",
                "vendor": "GC Inc",
                "amount": 150000.00,
                "is_pay_application": True,
                "accounting_contact": "accounting@onc.com",
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        g702 = next(
            (r for r in result.records_created if r.get("type") == "g702_g703_log_entry"),
            None,
        )
        assert g702 is not None


# ═══════════════════════════════════════════════════════════════
# 6. Change Order Workflow Tests
# ═══════════════════════════════════════════════════════════════


class TestChangeOrderWorkflow:
    @pytest.mark.asyncio
    async def test_new_co_creates_record(self, mock_celery, mock_notifications):
        from src.vault.workflows.change_order_workflow import ChangeOrderWorkflow

        wf = ChangeOrderWorkflow()
        doc = _make_document(title="Change Order #1")
        decision = _make_decision(
            document_type="CHANGE_ORDER",
            metadata={
                "co_sequence": 1,
                "amount": 25000.00,
                "current_contract_value": 1000000.00,
                "project_manager": "pm@onc.com",
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        co = next((r for r in result.records_created if r.get("co_number")), None)
        assert co is not None
        assert co["co_number"] == "CO-001"

    @pytest.mark.asyncio
    async def test_co_owner_directed_classification(self, mock_celery, mock_notifications):
        from src.vault.workflows.change_order_workflow import ChangeOrderWorkflow

        wf = ChangeOrderWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="CHANGE_ORDER",
            metadata={
                "co_sequence": 2,
                "is_owner_directed": True,
                "amount": 50000.00,
                "current_contract_value": 1000000.00,
                "project_manager": "pm@onc.com",
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        co = next((r for r in result.records_created if r.get("co_number")), None)
        assert co["origin"] == "Owner-Directed"

    @pytest.mark.asyncio
    async def test_co_budget_impact_calculation(self, mock_celery, mock_notifications):
        from src.vault.workflows.change_order_workflow import ChangeOrderWorkflow

        wf = ChangeOrderWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="CHANGE_ORDER",
            metadata={
                "co_sequence": 3,
                "amount": 100000.00,
                "current_contract_value": 1000000.00,
                "project_manager": "pm@onc.com",
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        co = next((r for r in result.records_created if r.get("co_number")), None)
        assert co["new_contract_value"] == 1100000.00
        assert co["budget_impact_pct"] == 10.0

    @pytest.mark.asyncio
    async def test_co_execution_updates_contract(self, mock_celery, mock_notifications):
        from src.vault.workflows.change_order_workflow import ChangeOrderWorkflow

        wf = ChangeOrderWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="CHANGE_ORDER",
            metadata={
                "is_execution": True,
                "co_number": "CO-001",
                "amount": 25000.00,
                "current_contract_value": 1000000.00,
                "notification_list": ["pm@onc.com", "owner@client.com"],
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        contract_update = next(
            (r for r in result.records_created if r.get("type") == "contract_value_update"),
            None,
        )
        assert contract_update is not None
        assert contract_update["new_value"] == 1025000.00

    @pytest.mark.asyncio
    async def test_co_routes_to_pm(self, mock_celery, mock_notifications):
        from src.vault.workflows.change_order_workflow import ChangeOrderWorkflow

        wf = ChangeOrderWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="CHANGE_ORDER",
            metadata={
                "co_sequence": 5,
                "amount": 10000.00,
                "current_contract_value": 500000.00,
                "project_manager": "pm@onc.com",
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        assert mock_notifications["email"].called or mock_notifications["in_app"].called


# ═══════════════════════════════════════════════════════════════
# 7. COI Workflow Tests
# ═══════════════════════════════════════════════════════════════


class TestCOIWorkflow:
    @pytest.mark.asyncio
    async def test_coi_creates_record(self, mock_celery, mock_notifications):
        from src.vault.workflows.coi_workflow import COIWorkflow

        wf = COIWorkflow()
        exp_date = (datetime.now(UTC) + timedelta(days=180)).isoformat()
        doc = _make_document(title="COI - ABC Plumbing")
        decision = _make_decision(
            document_type="COI",
            metadata={
                "subcontractor": "ABC Plumbing",
                "policy_number": "POL-12345",
                "insurance_carrier": "State Farm",
                "expiration_date": exp_date,
                "coverage_amounts": {
                    "general_liability": 2000000.0,
                    "auto_liability": 1000000.0,
                    "workers_comp": 500000.0,
                    "umbrella": 5000000.0,
                },
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        coi = next((r for r in result.records_created if r.get("policy_number")), None)
        assert coi is not None
        assert coi["subcontractor"] == "ABC Plumbing"
        assert coi["coverage_adequate"] is True

    @pytest.mark.asyncio
    async def test_coi_flags_insufficient_coverage(self, mock_celery, mock_notifications):
        from src.vault.workflows.coi_workflow import COIWorkflow

        wf = COIWorkflow()
        exp_date = (datetime.now(UTC) + timedelta(days=180)).isoformat()
        doc = _make_document()
        decision = _make_decision(
            document_type="COI",
            metadata={
                "subcontractor": "Cheap LLC",
                "policy_number": "POL-LOW",
                "expiration_date": exp_date,
                "coverage_amounts": {
                    "general_liability": 100000.0,  # Below 1M minimum
                    "auto_liability": 500000.0,  # Below 1M minimum
                },
                "project_manager": "pm@onc.com",
                "contracts_admin": "admin@onc.com",
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        coi = next((r for r in result.records_created if r.get("policy_number")), None)
        assert coi["coverage_adequate"] is False
        assert any("coverage" in s.lower() for s in result.next_steps)

    @pytest.mark.asyncio
    async def test_coi_schedules_expiration_reminders(self, mock_celery, mock_notifications):
        from src.vault.workflows.coi_workflow import COIWorkflow

        wf = COIWorkflow()
        exp_date = (datetime.now(UTC) + timedelta(days=90)).isoformat()
        doc = _make_document()
        decision = _make_decision(
            document_type="COI",
            metadata={
                "subcontractor": "Test Sub",
                "policy_number": "POL-TEST",
                "expiration_date": exp_date,
                "coverage_amounts": {
                    "general_liability": 2000000.0,
                    "auto_liability": 1000000.0,
                    "workers_comp": 500000.0,
                    "umbrella": 5000000.0,
                },
                "contracts_admin": "admin@onc.com",
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        # Should schedule reminders for 60, 30, 14, 7, 0 days (all within 90-day window)
        assert mock_celery.send_task.call_count >= 4

    @pytest.mark.asyncio
    async def test_coi_custom_min_requirements(self, mock_celery, mock_notifications):
        from src.vault.workflows.coi_workflow import COIWorkflow

        wf = COIWorkflow()
        exp_date = (datetime.now(UTC) + timedelta(days=180)).isoformat()
        doc = _make_document()
        decision = _make_decision(
            document_type="COI",
            metadata={
                "subcontractor": "Special Sub",
                "policy_number": "POL-CUSTOM",
                "expiration_date": exp_date,
                "coverage_amounts": {"general_liability": 3000000.0},
                "min_coverage_requirements": {"general_liability": 5000000.0},
                "project_manager": "pm@onc.com",
                "contracts_admin": "admin@onc.com",
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        coi = next((r for r in result.records_created if r.get("policy_number")), None)
        assert coi["coverage_adequate"] is False

    @pytest.mark.asyncio
    async def test_coi_error_handling(self, mock_notifications):
        from src.vault.workflows.coi_workflow import COIWorkflow

        wf = COIWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="COI",
            metadata={
                "subcontractor": "Test",
                "expiration_date": "invalid-date",
            },
        )
        # Invalid date should be caught
        result = await wf.execute(doc, decision, "proj-001", "user-1")
        assert result.success is False
        assert result.error_message is not None


# ═══════════════════════════════════════════════════════════════
# 8. Permit Workflow Tests
# ═══════════════════════════════════════════════════════════════


class TestPermitWorkflow:
    @pytest.mark.asyncio
    async def test_permit_creates_record(self, mock_celery, mock_notifications):
        from src.vault.workflows.permit_workflow import PermitWorkflow

        wf = PermitWorkflow()
        exp_date = (datetime.now(UTC) + timedelta(days=365)).isoformat()
        doc = _make_document(title="Building Permit")
        decision = _make_decision(
            document_type="PERMIT",
            metadata={
                "permit_number": "BP-2026-001",
                "permit_type": "Building",
                "issuing_authority": "City of Hoboken",
                "expiration_date": exp_date,
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        permit = next((r for r in result.records_created if r.get("permit_number")), None)
        assert permit is not None
        assert permit["permit_number"] == "BP-2026-001"
        assert permit["status"] == "ACTIVE"

    @pytest.mark.asyncio
    async def test_permit_links_work_activities(self, mock_celery, mock_notifications):
        from src.vault.workflows.permit_workflow import PermitWorkflow

        wf = PermitWorkflow()
        exp_date = (datetime.now(UTC) + timedelta(days=365)).isoformat()
        doc = _make_document()
        decision = _make_decision(
            document_type="PERMIT",
            metadata={
                "permit_number": "EP-2026-001",
                "permit_type": "Excavation",
                "issuing_authority": "DOT",
                "expiration_date": exp_date,
                "work_activities": ["Foundation Excavation", "Utility Trenching"],
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        links = [r for r in result.records_created if r.get("type") == "permit_activity_link"]
        assert len(links) == 2

    @pytest.mark.asyncio
    async def test_permit_schedules_expiration_reminders(self, mock_celery, mock_notifications):
        from src.vault.workflows.permit_workflow import PermitWorkflow

        wf = PermitWorkflow()
        exp_date = (datetime.now(UTC) + timedelta(days=100)).isoformat()
        doc = _make_document()
        decision = _make_decision(
            document_type="PERMIT",
            metadata={
                "permit_number": "PRM-TEST",
                "expiration_date": exp_date,
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        # 90, 60, 30, 14, 7 day reminders + day-of critical alert
        assert mock_celery.send_task.call_count >= 5

    @pytest.mark.asyncio
    async def test_permit_notifies_pm(self, mock_celery, mock_notifications):
        from src.vault.workflows.permit_workflow import PermitWorkflow

        wf = PermitWorkflow()
        exp_date = (datetime.now(UTC) + timedelta(days=365)).isoformat()
        doc = _make_document()
        decision = _make_decision(
            document_type="PERMIT",
            metadata={
                "permit_number": "PRM-NOTIFY",
                "permit_type": "Demolition",
                "issuing_authority": "City",
                "expiration_date": exp_date,
                "project_manager": "pm@onc.com",
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        assert len(result.notifications_sent) > 0

    @pytest.mark.asyncio
    async def test_permit_error_handling(self, mock_notifications):
        from src.vault.workflows.permit_workflow import PermitWorkflow

        wf = PermitWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="PERMIT",
            metadata={
                "permit_number": "PRM-ERR",
                "expiration_date": "invalid-date",
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")
        assert result.success is False


# ═══════════════════════════════════════════════════════════════
# 9. Schedule Workflow Tests
# ═══════════════════════════════════════════════════════════════


class TestScheduleWorkflow:
    @pytest.mark.asyncio
    async def test_schedule_creates_record(self, mock_celery, mock_notifications):
        from src.vault.workflows.schedule_workflow import ScheduleWorkflow

        wf = ScheduleWorkflow()
        doc = _make_document(title="Project Schedule Update")
        decision = _make_decision(
            document_type="SCHEDULE",
            metadata={
                "data_date": datetime.now(UTC).isoformat(),
                "completion_date": (datetime.now(UTC) + timedelta(days=180)).isoformat(),
                "critical_path": [{"name": "Foundation", "total_float": 0}],
                "milestones": [{"name": "Substantial Completion", "planned_date": "2027-01-01"}],
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        sched = next(
            (r for r in result.records_created if r.get("critical_path_count") is not None),
            None,
        )
        assert sched is not None
        assert sched["critical_path_count"] == 1

    @pytest.mark.asyncio
    async def test_schedule_baseline_comparison(self, mock_celery, mock_notifications):
        from src.vault.workflows.schedule_workflow import ScheduleWorkflow

        wf = ScheduleWorkflow()
        baseline = (datetime.now(UTC) + timedelta(days=180)).isoformat()
        current = (datetime.now(UTC) + timedelta(days=200)).isoformat()
        doc = _make_document()
        decision = _make_decision(
            document_type="SCHEDULE",
            metadata={
                "data_date": datetime.now(UTC).isoformat(),
                "completion_date": current,
                "baseline_completion_date": baseline,
                "project_manager": "pm@onc.com",
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        variance = next(
            (r for r in result.records_created if r.get("type") == "schedule_variance"),
            None,
        )
        assert variance is not None
        assert variance["variance_days"] == 20

    @pytest.mark.asyncio
    async def test_schedule_negative_float_flagged(self, mock_celery, mock_notifications):
        from src.vault.workflows.schedule_workflow import ScheduleWorkflow

        wf = ScheduleWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="SCHEDULE",
            metadata={
                "data_date": datetime.now(UTC).isoformat(),
                "negative_float_activities": [
                    {"name": "Steel Erection", "total_float": -5},
                    {"name": "MEP Rough-In", "total_float": -2},
                ],
                "project_manager": "pm@onc.com",
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        assert any("negative float" in s.lower() for s in result.next_steps)

    @pytest.mark.asyncio
    async def test_schedule_milestone_updates(self, mock_celery, mock_notifications):
        from src.vault.workflows.schedule_workflow import ScheduleWorkflow

        wf = ScheduleWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="SCHEDULE",
            metadata={
                "data_date": datetime.now(UTC).isoformat(),
                "milestones": [
                    {"name": "Topping Out", "planned_date": "2026-09-01"},
                    {"name": "Substantial Completion", "planned_date": "2027-01-15"},
                ],
            },
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        milestone_updates = [
            r for r in result.records_created if r.get("type") == "milestone_update"
        ]
        assert len(milestone_updates) == 2

    @pytest.mark.asyncio
    async def test_schedule_on_track(self, mock_celery, mock_notifications):
        from src.vault.workflows.schedule_workflow import ScheduleWorkflow

        wf = ScheduleWorkflow()
        doc = _make_document()
        decision = _make_decision(
            document_type="SCHEDULE",
            metadata={"data_date": datetime.now(UTC).isoformat()},
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        assert any("on track" in s.lower() for s in result.next_steps)


# ═══════════════════════════════════════════════════════════════
# 10. General Workflow Tests
# ═══════════════════════════════════════════════════════════════


class TestGeneralWorkflow:
    @pytest.mark.asyncio
    async def test_general_files_document(self, mock_celery, mock_notifications):
        from src.vault.workflows.general_workflow import GeneralWorkflow

        wf = GeneralWorkflow()
        doc = _make_document(title="Progress Photo - Week 12")
        decision = _make_decision(document_type="PHOTO_PROGRESS")
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        filed = next((r for r in result.records_created if r.get("folder_path")), None)
        assert filed is not None
        assert "Photos/Progress" in filed["folder_path"]

    @pytest.mark.asyncio
    async def test_general_unknown_flags_review(self, mock_celery, mock_notifications):
        from src.vault.workflows.general_workflow import GeneralWorkflow

        wf = GeneralWorkflow()
        doc = _make_document(title="Misc Document")
        decision = _make_decision(
            document_type="UNKNOWN",
            confidence_score=0.3,
            metadata={"project_manager": "pm@onc.com"},
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert result.success is True
        assert any("human" in s.lower() for s in result.next_steps)

    @pytest.mark.asyncio
    async def test_general_daily_report(self, mock_celery, mock_notifications):
        from src.vault.workflows.general_workflow import GeneralWorkflow

        wf = GeneralWorkflow()
        doc = _make_document(title="Daily Report 2026-04-15")
        decision = _make_decision(document_type="DAILY_REPORT")
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        filed = next((r for r in result.records_created if r.get("folder_path")), None)
        assert "Reports/Daily" in filed["folder_path"]

    @pytest.mark.asyncio
    async def test_general_meeting_minutes(self, mock_celery, mock_notifications):
        from src.vault.workflows.general_workflow import GeneralWorkflow

        wf = GeneralWorkflow()
        doc = _make_document(title="OAC Meeting Minutes #14")
        decision = _make_decision(document_type="MEETING_MINUTES")
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        filed = next((r for r in result.records_created if r.get("folder_path")), None)
        assert "Meeting Minutes" in filed["folder_path"]

    @pytest.mark.asyncio
    async def test_general_requires_human_review(self, mock_celery, mock_notifications):
        from src.vault.workflows.general_workflow import GeneralWorkflow

        wf = GeneralWorkflow()
        doc = _make_document(title="Ambiguous Document")
        decision = _make_decision(
            document_type="TRANSMITTAL",
            requires_human_review=True,
            confidence_score=0.4,
        )
        result = await wf.execute(doc, decision, "proj-001", "user-1")

        assert any("human review" in s.lower() for s in result.next_steps)


# ═══════════════════════════════════════════════════════════════
# 11. Workflow Router Tests
# ═══════════════════════════════════════════════════════════════


class TestWorkflowRouter:
    def test_all_document_types_mapped(self):
        expected_types = [
            "RFI", "SUBMITTAL", "INVOICE", "CHANGE_ORDER", "COI",
            "CERTIFICATE_OF_INSURANCE", "PERMIT", "SCHEDULE",
            "PLANS_DRAWINGS", "SPECIFICATIONS", "PHOTO_PROGRESS",
            "DAILY_REPORT", "MEETING_MINUTES", "CLOSEOUT", "TRANSMITTAL", "UNKNOWN",
        ]
        for doc_type in expected_types:
            assert doc_type in DOCUMENT_TYPE_TO_WORKFLOW

    def test_get_workflow_returns_correct_type(self):
        from src.vault.workflows.rfi_workflow import RFIWorkflow

        wf = _get_workflow("RFI")
        assert isinstance(wf, RFIWorkflow)

    def test_get_workflow_case_insensitive(self):
        from src.vault.workflows.rfi_workflow import RFIWorkflow

        wf = _get_workflow("rfi")
        assert isinstance(wf, RFIWorkflow)

    def test_unknown_type_falls_back_to_general(self):
        from src.vault.workflows.general_workflow import GeneralWorkflow

        wf = _get_workflow("NONEXISTENT_TYPE")
        assert isinstance(wf, GeneralWorkflow)

    @pytest.mark.asyncio
    async def test_execute_workflow_dispatches_correctly(self, mock_celery, mock_notifications):
        doc = _make_document()
        decision = _make_decision(
            document_type="RFI",
            metadata={"rfi_sequence": 99},
        )
        result = await execute_workflow(doc, decision, "proj-001", "user-1")

        assert result.success is True
        assert any(r.get("rfi_number") for r in result.records_created)

    @pytest.mark.asyncio
    async def test_execute_workflow_handles_error_gracefully(self, mock_notifications):
        """Even if a workflow completely crashes, the router returns a result."""
        doc = _make_document()
        decision = _make_decision(document_type="RFI")

        with patch(
            "src.vault.workflows.workflow_router._get_workflow",
            side_effect=Exception("catastrophic failure"),
        ):
            result = await execute_workflow(doc, decision, "proj-001", "user-1")

        assert result.success is False
        assert "catastrophic failure" in (result.error_message or "")


# ═══════════════════════════════════════════════════════════════
# 12. Deadline Tasks Tests
# ═══════════════════════════════════════════════════════════════


class TestDeadlineTasks:
    def test_check_rfi_deadlines_returns_dict(self, mock_celery):
        from src.vault.workflows.deadline_tasks import check_rfi_deadlines

        result = check_rfi_deadlines()
        assert result["task"] == "check_rfi_deadlines"
        assert result["status"] == "completed"

    def test_check_coi_expirations_returns_dict(self, mock_celery):
        from src.vault.workflows.deadline_tasks import check_coi_expirations

        result = check_coi_expirations()
        assert result["task"] == "check_coi_expirations"

    def test_check_permit_expirations_returns_dict(self, mock_celery):
        from src.vault.workflows.deadline_tasks import check_permit_expirations

        result = check_permit_expirations()
        assert result["task"] == "check_permit_expirations"

    def test_check_invoice_due_dates_returns_dict(self, mock_celery):
        from src.vault.workflows.deadline_tasks import check_invoice_due_dates

        result = check_invoice_due_dates()
        assert result["task"] == "check_invoice_due_dates"

    def test_send_reminder_runs(self, mock_celery):
        from src.vault.workflows.deadline_tasks import send_reminder

        with patch("src.vault.workflows.deadline_tasks.run_async"):
            result = send_reminder("user1", "Test reminder", "doc-1", "proj-1")
            assert result["recipient"] == "user1"
