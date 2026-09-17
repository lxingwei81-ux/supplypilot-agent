from __future__ import annotations

from datetime import date, datetime, timezone

from ..config import RulesConfig, load_rules
from ..models import (
    Risk,
    RiskLevel,
    RiskTask,
    TaskNotification,
    TaskPriority,
    TaskStatus,
    utc_now,
)


TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.OPEN: {TaskStatus.ACKNOWLEDGED, TaskStatus.CANCELLED},
    TaskStatus.ACKNOWLEDGED: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
    TaskStatus.IN_PROGRESS: {TaskStatus.PENDING_APPROVAL, TaskStatus.COMPLETED, TaskStatus.CANCELLED},
    TaskStatus.PENDING_APPROVAL: {TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: {TaskStatus.VERIFIED, TaskStatus.IN_PROGRESS},
    TaskStatus.VERIFIED: {TaskStatus.CLOSED, TaskStatus.IN_PROGRESS},
    TaskStatus.CLOSED: set(),
    TaskStatus.CANCELLED: set(),
}


class RiskTaskService:
    def __init__(self, rules: RulesConfig | None = None) -> None:
        self.rules = rules or load_rules()
        self._tasks: dict[str, RiskTask] = {}
        self._sent_notifications: set[tuple[str, str, str, date]] = set()

    def create_from_risk(self, risk: Risk, *, assignee: str, approvers: list[str] | None = None) -> RiskTask:
        priority = {
            RiskLevel.CRITICAL: TaskPriority.P0,
            RiskLevel.HIGH: TaskPriority.P1,
            RiskLevel.MEDIUM: TaskPriority.P2,
            RiskLevel.LOW: TaskPriority.P3,
        }[risk.level]
        task = RiskTask(
            task_id=f"TASK-{risk.risk_id}", risk_id=risk.risk_id,
            title=f"{risk.risk_type.value} {risk.material_id}/{risk.plant}",
            priority=priority, status=TaskStatus.OPEN,
            owner_department=risk.owner_department, assignee=assignee,
            approvers=approvers or [], due_date=risk.latest_action_date,
            evidence=risk.evidence,
        )
        if task.task_id in self._tasks:
            raise ValueError(f"duplicate task {task.task_id}")
        self._tasks[task.task_id] = task
        return task

    def transition(self, task_id: str, to_status: TaskStatus, *, actor: str, as_of: datetime | None = None) -> RiskTask:
        task = self._tasks[task_id]
        if to_status not in TASK_TRANSITIONS[task.status]:
            raise ValueError(f"invalid task transition {task.status.value}->{to_status.value}")
        updated = task.model_copy(deep=True)
        timestamp = as_of or utc_now()
        if to_status == TaskStatus.ACKNOWLEDGED:
            updated.acknowledged_at = timestamp
        if to_status == TaskStatus.COMPLETED:
            updated.completed_at = timestamp
        updated.status = to_status
        self._tasks[task_id] = updated
        return updated

    def generate_notifications(self, as_of: date) -> list[TaskNotification]:
        cfg = self.rules.task_management
        notifications: list[TaskNotification] = []
        closed = {TaskStatus.COMPLETED, TaskStatus.VERIFIED, TaskStatus.CLOSED, TaskStatus.CANCELLED}
        for task_id in sorted(self._tasks):
            task = self._tasks[task_id]
            if task.status in closed:
                continue
            days_to_due = (task.due_date - as_of).days
            if 0 <= days_to_due <= cfg.reminder_days_before_due:
                key = (task_id, "REMINDER", task.assignee, as_of)
                if key not in self._sent_notifications:
                    notifications.append(TaskNotification(
                        notification_id=f"REM-{task_id}-{as_of.isoformat()}", task_id=task_id,
                        notification_type="DUE_REMINDER", recipient=task.assignee,
                        message=f"任务将在{days_to_due}天后到期：{task.title}",
                    ))
                    self._sent_notifications.add(key)
                    task.reminder_count += 1
            overdue_days = max(0, -days_to_due)
            level = 0
            for index, threshold in enumerate(cfg.overdue_escalation_days, start=1):
                if overdue_days >= threshold:
                    level = index
            if level > task.escalation_level:
                recipient = cfg.escalation_roles[level - 1]
                key = (task_id, f"ESCALATION_{level}", recipient, as_of)
                if key not in self._sent_notifications:
                    notifications.append(TaskNotification(
                        notification_id=f"ESC-{level}-{task_id}-{as_of.isoformat()}", task_id=task_id,
                        notification_type=f"OVERDUE_ESCALATION_{level}", recipient=recipient,
                        message=f"任务逾期{overdue_days}天，升级至{recipient}：{task.title}",
                    ))
                    self._sent_notifications.add(key)
                    task.escalation_level = level
                    if recipient not in task.escalated_to:
                        task.escalated_to.append(recipient)
        return notifications

    def list_tasks(self) -> list[RiskTask]:
        return [self._tasks[key] for key in sorted(self._tasks)]

