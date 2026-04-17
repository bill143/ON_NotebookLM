"""
Nexus Vault — Document Workflow Agents
Codename: ESPERANTO

Specialized workflow processors for construction document types:
- RFI, Submittal, Invoice, Change Order, COI, Permit, Schedule, General
Each workflow receives a LibrarianDecision and executes domain-specific logic.
"""

from src.vault.workflows.workflow_router import execute_workflow

__all__ = ["execute_workflow"]
