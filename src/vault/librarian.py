"""
Nexus Vault — Construction Librarian AI Agent
Codename: ESPERANTO

Core intelligence engine for the Intelligent Document Vault.
Accepts uploaded files, extracts content, classifies document type via AI,
and returns a LibrarianDecision with metadata, routing, and workflow triggers.
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

from src.vault.classifier_prompts import (
    CLASSIFICATION_SYSTEM_PROMPT,
    CONFIDENCE_SCORING_GUIDANCE,
    METADATA_EXTRACTION_BY_TYPE,
    METADATA_EXTRACTION_SYSTEM_PROMPT,
    SCOPE_CHANGE_DETECTION_PROMPT,
)
from src.vault.document_types import (
    DocumentType,
    LibrarianDecision,
    RoutingInstruction,
    WorkflowTrigger,
)
from src.vault.extractors import extract_content

# ── Routing Rules ───────────────────────────────────────────

_ROUTING_MAP: dict[str, list[dict[str, Any]]] = {
    "rfi": [
        {"destination": "rfi_tracker", "action": "create", "priority": 1},
        {"destination": "project_manager", "action": "notify", "priority": 0},
    ],
    "submittal": [
        {"destination": "submittal_log", "action": "create", "priority": 1},
        {"destination": "design_team", "action": "notify", "priority": 0},
    ],
    "invoice": [
        {"destination": "cost_control", "action": "create", "priority": 1},
        {"destination": "accounts_payable", "action": "notify", "priority": 0},
    ],
    "change_order": [
        {"destination": "change_order_log", "action": "create", "priority": 2},
        {"destination": "project_manager", "action": "notify", "priority": 1},
        {"destination": "cost_control", "action": "notify", "priority": 0},
    ],
    "schedule": [
        {"destination": "schedule_tracker", "action": "create", "priority": 1},
    ],
    "plans_drawings": [
        {"destination": "drawing_register", "action": "create", "priority": 1},
    ],
    "coi": [
        {"destination": "insurance_tracker", "action": "create", "priority": 1},
        {"destination": "compliance", "action": "notify", "priority": 0},
    ],
    "permit": [
        {"destination": "permit_tracker", "action": "create", "priority": 1},
        {"destination": "compliance", "action": "notify", "priority": 0},
    ],
    "pay_application": [
        {"destination": "cost_control", "action": "create", "priority": 2},
        {"destination": "project_manager", "action": "notify", "priority": 1},
    ],
    "daily_report": [
        {"destination": "field_reports", "action": "create", "priority": 0},
    ],
    "safety_document": [
        {"destination": "safety_log", "action": "create", "priority": 1},
        {"destination": "safety_officer", "action": "notify", "priority": 1},
    ],
    "lien_waiver": [
        {"destination": "lien_waiver_log", "action": "create", "priority": 1},
        {"destination": "accounts_payable", "action": "notify", "priority": 0},
    ],
    "meeting_minutes": [
        {"destination": "meeting_log", "action": "create", "priority": 0},
    ],
    "bim_model": [
        {"destination": "bim_register", "action": "create", "priority": 0},
    ],
    "photo_progress": [
        {"destination": "photo_log", "action": "create", "priority": 0},
    ],
    "closeout": [
        {"destination": "closeout_tracker", "action": "create", "priority": 1},
    ],
    "transmittal": [
        {"destination": "transmittal_log", "action": "create", "priority": 0},
    ],
}

_WORKFLOW_TRIGGERS: dict[str, list[dict[str, Any]]] = {
    "rfi": [
        {
            "trigger_type": "review_cycle",
            "target_roles": ["project_manager", "architect"],
            "urgency": "high",
        },
    ],
    "submittal": [
        {
            "trigger_type": "review_cycle",
            "target_roles": ["architect", "engineer"],
            "urgency": "normal",
        },
    ],
    "change_order": [
        {
            "trigger_type": "cost_impact",
            "target_roles": ["project_manager", "owner_rep"],
            "urgency": "high",
        },
    ],
    "coi": [
        {
            "trigger_type": "deadline_tracking",
            "target_roles": ["compliance"],
            "urgency": "normal",
        },
    ],
    "permit": [
        {
            "trigger_type": "deadline_tracking",
            "target_roles": ["project_manager", "compliance"],
            "urgency": "normal",
        },
    ],
    "pay_application": [
        {
            "trigger_type": "cost_impact",
            "target_roles": ["project_manager", "owner_rep"],
            "urgency": "high",
        },
    ],
    "safety_document": [
        {
            "trigger_type": "notification",
            "target_roles": ["safety_officer", "project_manager"],
            "urgency": "high",
        },
    ],
    "invoice": [
        {
            "trigger_type": "cost_impact",
            "target_roles": ["project_manager", "accounts_payable"],
            "urgency": "normal",
        },
    ],
}


# ── Librarian Agent ─────────────────────────────────────────


class LibrarianAgent:
    """
    Construction Librarian AI — classifies documents and extracts metadata.

    Uses the ESPERANTO model layer (ModelManager) to provision AI providers.
    All AI calls flow through the centralized model registry — never hardcoded.
    """

    CLASSIFICATION_TASK_TYPE = "document_classification"

    async def classify(
        self,
        file_bytes: bytes,
        filename: str,
        *,
        tenant_id: str | None = None,
        project_id: str | None = None,
    ) -> LibrarianDecision:
        """
        Classify a document and extract metadata.

        1. Extract file content using the appropriate extractor
        2. Call AI to classify document type
        3. Call AI to extract type-specific metadata
        4. Build routing instructions and workflow triggers
        5. Return LibrarianDecision

        Never raises — returns UNKNOWN type on any failure.
        """
        logger.info(
            f"Librarian classifying: {filename}",
            file_size=len(file_bytes),
            tenant_id=tenant_id,
        )

        try:
            # Step 1: Extract content
            extraction = extract_content(file_bytes, filename)
            content = extraction["content"]
            file_metadata = extraction["file_metadata"]

            # Step 2: Classify document type
            classification = await self._classify_document(
                content, filename, file_metadata, tenant_id=tenant_id
            )

            doc_type_str = classification.get("document_type", "unknown")
            try:
                doc_type = DocumentType(doc_type_str)
            except ValueError:
                logger.warning(f"AI returned unknown type: {doc_type_str}")
                doc_type = DocumentType.UNKNOWN

            confidence = float(classification.get("confidence_score", 0.0))
            confidence = max(0.0, min(1.0, confidence))

            # Step 3: Extract type-specific metadata
            base_metadata: dict[str, Any] = {
                "title": classification.get("title"),
                "description": classification.get("description"),
                "date": classification.get("date"),
                "project_reference": classification.get("project_reference"),
                "confidence_score": confidence,
                "classification_reasoning": classification.get("classification_reasoning"),
                **file_metadata,
            }

            if doc_type != DocumentType.UNKNOWN and doc_type.value in METADATA_EXTRACTION_BY_TYPE:
                type_metadata = await self._extract_metadata(
                    content, doc_type.value, tenant_id=tenant_id
                )
                base_metadata.update(type_metadata)

            # Step 3b: Scope change detection for RFIs
            if doc_type == DocumentType.RFI:
                scope_result = await self._detect_scope_change(
                    content, tenant_id=tenant_id
                )
                base_metadata["is_scope_change"] = scope_result.get("is_scope_change", False)
                base_metadata["scope_change_confidence"] = scope_result.get(
                    "scope_change_confidence", 0.0
                )

            # Step 4: Build routing and triggers
            routing = self._build_routing(doc_type)
            triggers = self._build_triggers(doc_type)

            # Step 5: Assemble decision
            requires_review = confidence < 0.75 or doc_type == DocumentType.UNKNOWN

            decision = LibrarianDecision(
                document_type=doc_type,
                metadata=base_metadata,
                confidence_score=confidence,
                routing_instructions=routing,
                workflow_triggers=triggers,
                requires_human_review=requires_review,
            )

            logger.info(
                f"Librarian classified {filename} as {doc_type.value}",
                confidence=confidence,
                requires_review=requires_review,
            )

            return decision

        except Exception as e:
            logger.error(f"Librarian classification failed for {filename}: {e}")
            return LibrarianDecision(
                document_type=DocumentType.UNKNOWN,
                metadata={
                    "title": filename,
                    "error": str(e)[:500],
                    "file_size_bytes": len(file_bytes),
                },
                confidence_score=0.0,
                requires_human_review=True,
            )

    # ── AI Calls ────────────────────────────────────────────

    async def _classify_document(
        self,
        content: str,
        filename: str,
        file_metadata: dict[str, Any],
        *,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Call AI to classify the document type."""
        from src.agents.nexus_model_layer import model_manager

        provider = await model_manager.provision_llm(
            task_type=self.CLASSIFICATION_TASK_TYPE,
            tenant_id=tenant_id,
        )

        system_prompt = CLASSIFICATION_SYSTEM_PROMPT + "\n\n" + CONFIDENCE_SCORING_GUIDANCE

        user_message = (
            f"Classify this construction document.\n\n"
            f"Filename: {filename}\n"
            f"File metadata: {json.dumps(file_metadata, default=str)}\n\n"
            f"--- Document Content ---\n{content}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        response = await provider.generate(
            messages,
            temperature=0.1,
            max_tokens=1024,
        )

        return self._parse_json_response(response.content, "classification")

    async def _extract_metadata(
        self,
        content: str,
        document_type: str,
        *,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Call AI to extract type-specific metadata."""
        type_prompt = METADATA_EXTRACTION_BY_TYPE.get(document_type)
        if not type_prompt:
            return {}

        from src.agents.nexus_model_layer import model_manager

        provider = await model_manager.provision_llm(
            task_type=self.CLASSIFICATION_TASK_TYPE,
            tenant_id=tenant_id,
        )

        system_prompt = METADATA_EXTRACTION_SYSTEM_PROMPT + "\n\n" + type_prompt

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Extract metadata from this document:\n\n{content}"},
        ]

        response = await provider.generate(
            messages,
            temperature=0.1,
            max_tokens=1024,
        )

        return self._parse_json_response(response.content, "metadata_extraction")

    async def _detect_scope_change(
        self,
        content: str,
        *,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Call AI to detect potential scope changes in RFIs."""
        from src.agents.nexus_model_layer import model_manager

        provider = await model_manager.provision_llm(
            task_type=self.CLASSIFICATION_TASK_TYPE,
            tenant_id=tenant_id,
        )

        messages = [
            {"role": "system", "content": SCOPE_CHANGE_DETECTION_PROMPT},
            {"role": "user", "content": f"Evaluate this RFI for scope change:\n\n{content}"},
        ]

        response = await provider.generate(
            messages,
            temperature=0.1,
            max_tokens=512,
        )

        return self._parse_json_response(response.content, "scope_change")

    # ── Routing & Triggers ──────────────────────────────────

    def _build_routing(self, doc_type: DocumentType) -> list[RoutingInstruction]:
        """Build routing instructions for a document type."""
        rules = _ROUTING_MAP.get(doc_type.value, [])
        return [RoutingInstruction(**rule) for rule in rules]

    def _build_triggers(self, doc_type: DocumentType) -> list[WorkflowTrigger]:
        """Build workflow triggers for a document type."""
        rules = _WORKFLOW_TRIGGERS.get(doc_type.value, [])
        return [WorkflowTrigger(**rule) for rule in rules]

    # ── JSON Parsing ────────────────────────────────────────

    @staticmethod
    def _parse_json_response(raw: str, context: str) -> dict[str, Any]:
        """Parse AI JSON response, handling common formatting issues."""
        cleaned = raw.strip()

        # Strip markdown code fences if present
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first line (```json or ```) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(
                f"JSON parse failed in {context}: {e}",
                raw_preview=cleaned[:200],
            )
            return {}


# ── Global Singleton ────────────────────────────────────────

librarian_agent = LibrarianAgent()
