"""
Schedule Workflow — Schedule Processing Agent.

Handles construction schedule file lifecycle:
- XER (Primavera P6) parsing
- Critical path and float analysis
- Baseline comparison
- Negative float flagging
- Milestone date update tracking
- PM notification on completion date changes
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from src.vault.workflows.base_workflow import (
    BaseWorkflow,
    LibrarianDecision,
    NotificationChannel,
    Urgency,
    WorkflowResult,
)


class ScheduleWorkflow(BaseWorkflow):
    """Workflow agent for construction schedule documents (XER, MPP, etc.)."""

    workflow_name = "schedule"

    async def execute(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        self._reset()

        try:
            return await self._process_schedule(document, decision, project_id, user_id)
        except Exception as e:
            logger.error(f"Schedule workflow failed: {e}", document_id=document.get("id"))
            self._record_action("workflow_error", {"error": str(e)})
            return self._build_result(
                success=False,
                error_message=str(e),
                next_steps=["Flag document for human review"],
            )

    async def _process_schedule(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        metadata = decision.metadata
        next_steps: list[str] = []

        # 1. Parse schedule data (metadata extracted by Librarian)
        data_date_str = metadata.get("data_date", "")
        data_date = (
            datetime.fromisoformat(data_date_str).replace(tzinfo=UTC)
            if data_date_str
            else datetime.now(UTC)
        )

        critical_path_activities: list[dict[str, Any]] = metadata.get("critical_path", [])
        milestones: list[dict[str, Any]] = metadata.get("milestones", [])
        activities_with_negative_float: list[dict[str, Any]] = metadata.get(
            "negative_float_activities", []
        )
        completion_date_str = metadata.get("completion_date", "")
        baseline_completion_str = metadata.get("baseline_completion_date", "")

        schedule_record = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "document_id": document.get("id", ""),
            "data_date": data_date.isoformat(),
            "completion_date": completion_date_str,
            "baseline_completion_date": baseline_completion_str,
            "critical_path_count": len(critical_path_activities),
            "negative_float_count": len(activities_with_negative_float),
            "milestone_count": len(milestones),
            "created_by": user_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._records.append(schedule_record)
        self._record_action("parse_schedule", {
            "data_date": data_date.isoformat(),
            "critical_path_count": len(critical_path_activities),
        })

        # 2. Compare against baseline
        schedule_variance_days = 0
        if completion_date_str and baseline_completion_str:
            completion = datetime.fromisoformat(completion_date_str).replace(tzinfo=UTC)
            baseline = datetime.fromisoformat(baseline_completion_str).replace(tzinfo=UTC)
            schedule_variance_days = (completion - baseline).days

            self._records.append({
                "type": "schedule_variance",
                "project_id": project_id,
                "current_completion": completion_date_str,
                "baseline_completion": baseline_completion_str,
                "variance_days": schedule_variance_days,
            })
            self._record_action("baseline_comparison", {
                "variance_days": schedule_variance_days,
            })

        # 3. Flag activities with negative float
        if activities_with_negative_float:
            self._record_action("flag_negative_float", {
                "count": len(activities_with_negative_float),
                "activities": [a.get("name", "Unknown") for a in activities_with_negative_float[:5]],
            })

            pm = metadata.get("project_manager", user_id)
            float_details = "\n".join(
                f"  - {a.get('name', 'Unknown')}: {a.get('total_float', 0)} days float"
                for a in activities_with_negative_float[:10]
            )
            await self.notify(
                recipients=[pm],
                subject=f"Schedule Alert — {len(activities_with_negative_float)} Activities with Negative Float",
                message=(
                    f"The following activities have negative float:\n\n"
                    f"{float_details}\n\n"
                    f"Data Date: {data_date.strftime('%B %d, %Y')}"
                ),
                channel=NotificationChannel.BOTH,
                urgency=Urgency.HIGH,
            )
            next_steps.append("Review activities with negative float")

        # 4. Update project milestone dates
        if milestones:
            for milestone in milestones:
                self._records.append({
                    "type": "milestone_update",
                    "project_id": project_id,
                    "milestone_name": milestone.get("name", ""),
                    "planned_date": milestone.get("planned_date", ""),
                    "forecast_date": milestone.get("forecast_date", ""),
                })
            self._record_action("update_milestones", {"count": len(milestones)})

        # 5. Notify PM if completion date changed
        if schedule_variance_days != 0:
            pm = metadata.get("project_manager", user_id)
            direction = "delayed" if schedule_variance_days > 0 else "ahead of schedule"
            await self.notify(
                recipients=[pm],
                subject=f"Schedule Update — Completion Date {direction.title()} by {abs(schedule_variance_days)} Days",
                message=(
                    f"The project completion date has changed.\n\n"
                    f"Baseline Completion: {baseline_completion_str}\n"
                    f"Current Completion: {completion_date_str}\n"
                    f"Variance: {schedule_variance_days:+d} days ({direction})\n"
                    f"Data Date: {data_date.strftime('%B %d, %Y')}"
                ),
                channel=NotificationChannel.BOTH,
                urgency=Urgency.HIGH if schedule_variance_days > 0 else Urgency.NORMAL,
            )
            next_steps.append(f"Completion date {direction} by {abs(schedule_variance_days)} days")

        await self.create_log_entry(
            action="schedule_processed",
            details={
                "data_date": data_date.isoformat(),
                "variance_days": schedule_variance_days,
                "negative_float_count": len(activities_with_negative_float),
            },
            document_id=document.get("id", ""),
            project_id=project_id,
            user_id=user_id,
        )

        if not next_steps:
            next_steps.append("Schedule processed — on track")

        return self._build_result(success=True, next_steps=next_steps)
