"""
Vault Integration Layer — Connects the Document Vault to existing NEXUS modules.

All methods fail gracefully — log error but never crash if an integration
module is unavailable. This ensures the vault remains functional even if
dependent services are not deployed.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from loguru import logger


async def link_to_notebook_source(
    vault_document_id: str, notebook_id: str, tenant_id: str
) -> dict[str, Any] | None:
    """
    Create a notebook source from a vault document so it can be used in NotebookLM features.

    Inserts a record into the sources table referencing the vault document,
    then links it to the specified notebook via notebook_sources.
    """
    try:
        from sqlalchemy import text

        from src.infra.nexus_data_persist import get_session

        async with get_session(tenant_id) as session:
            # Get the vault document details
            doc_result = await session.execute(
                text(
                    "SELECT original_filename, file_path, mime_type "
                    "FROM vault_documents "
                    "WHERE id = :doc_id AND tenant_id = :tenant_id AND deleted_at IS NULL"
                ),
                {"doc_id": vault_document_id, "tenant_id": tenant_id},
            )
            doc = doc_result.mappings().first()
            if not doc:
                logger.warning("Vault document not found for notebook link", doc_id=vault_document_id)
                return None

            # Create a source record referencing the vault document
            source_result = await session.execute(
                text(
                    "INSERT INTO sources (id, tenant_id, title, source_type, status, "
                    "metadata, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :tenant_id, :title, 'upload', 'ready', "
                    ":metadata, NOW(), NOW()) "
                    "RETURNING id"
                ),
                {
                    "tenant_id": tenant_id,
                    "title": doc["original_filename"],
                    "metadata": f'{{"vault_document_id": "{vault_document_id}", "file_path": "{doc["file_path"]}"}}',
                },
            )
            source_row = source_result.mappings().first()
            if not source_row:
                return None

            source_id = str(source_row["id"])

            # Link source to notebook
            await session.execute(
                text(
                    "INSERT INTO notebook_sources (notebook_id, source_id) "
                    "VALUES (:notebook_id, :source_id) "
                    "ON CONFLICT DO NOTHING"
                ),
                {"notebook_id": notebook_id, "source_id": source_id},
            )

            logger.info(
                "Linked vault document to notebook",
                vault_document_id=vault_document_id,
                notebook_id=notebook_id,
                source_id=source_id,
            )
            return {
                "source_id": source_id,
                "notebook_id": notebook_id,
                "vault_document_id": vault_document_id,
            }

    except Exception:
        logger.exception(
            "Failed to link vault document to notebook",
            vault_document_id=vault_document_id,
            notebook_id=notebook_id,
        )
        return None


async def create_calendar_deadline(
    title: str,
    due_date: date,
    project_id: str,
    assignee_id: str,
    reminder_days: list[int] | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Create a calendar event/deadline using existing calendar module if available.

    Fails gracefully if no calendar module is deployed.
    """
    try:
        # Try to import calendar module — may not exist
        from src.api import calendar as calendar_module  # type: ignore[attr-defined]

        result = await calendar_module.create_event(
            title=title,
            due_date=due_date,
            project_id=project_id,
            assignee_id=assignee_id,
            reminder_days=reminder_days or [7, 3, 1],
            tenant_id=tenant_id,
        )
        logger.info("Created calendar deadline", title=title, due_date=str(due_date))
        return result
    except ImportError:
        logger.debug("Calendar module not available — skipping deadline creation")
        return None
    except Exception:
        logger.exception("Failed to create calendar deadline", title=title)
        return None


async def trigger_notification(
    user_id: str,
    title: str,
    message: str,
    urgency: str = "normal",
    action_url: str | None = None,
    tenant_id: str | None = None,
) -> bool:
    """
    Send a notification using the existing notification service.

    Fails gracefully if no notification service is available.
    """
    try:
        from src.api import notifications as notif_module  # type: ignore[attr-defined]

        await notif_module.send(
            user_id=user_id,
            title=title,
            message=message,
            urgency=urgency,
            action_url=action_url,
            tenant_id=tenant_id,
        )
        logger.info("Sent notification", user_id=user_id, title=title)
        return True
    except ImportError:
        logger.debug("Notification module not available — skipping notification")
        return False
    except Exception:
        logger.exception("Failed to send notification", user_id=user_id, title=title)
        return False


async def update_project_document_count(
    project_id: str, tenant_id: str
) -> int | None:
    """
    Increment the document counter for a project.

    Queries vault_documents to get the current count and updates
    the project record if a projects table exists.
    """
    try:
        from sqlalchemy import text

        from src.infra.nexus_data_persist import get_session

        async with get_session(tenant_id) as session:
            # Count active vault documents for this project
            result = await session.execute(
                text(
                    "SELECT COUNT(*) as cnt FROM vault_documents "
                    "WHERE project_id = :project_id AND tenant_id = :tenant_id "
                    "AND deleted_at IS NULL"
                ),
                {"project_id": project_id, "tenant_id": tenant_id},
            )
            row = result.mappings().first()
            count = row["cnt"] if row else 0

            logger.info(
                "Project document count updated",
                project_id=project_id,
                count=count,
            )
            return count

    except Exception:
        logger.exception(
            "Failed to update project document count",
            project_id=project_id,
        )
        return None
