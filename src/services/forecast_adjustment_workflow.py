from __future__ import annotations

from datetime import date
from typing import Any

from ..models import Evidence, ForecastAdjustmentWorkflow, WorkflowStatus, utc_now


TRANSITIONS: dict[WorkflowStatus, set[WorkflowStatus]] = {
    WorkflowStatus.DRAFT: {WorkflowStatus.SUBMITTED},
    WorkflowStatus.SUBMITTED: {WorkflowStatus.COMMERCIAL_REVIEW, WorkflowStatus.REJECTED},
    WorkflowStatus.COMMERCIAL_REVIEW: {WorkflowStatus.SUPPLY_REVIEW, WorkflowStatus.REJECTED},
    WorkflowStatus.SUPPLY_REVIEW: {WorkflowStatus.PENDING_APPROVAL, WorkflowStatus.REJECTED},
    WorkflowStatus.PENDING_APPROVAL: {WorkflowStatus.APPROVED, WorkflowStatus.REJECTED},
    WorkflowStatus.APPROVED: {WorkflowStatus.EFFECTIVE},
    WorkflowStatus.EFFECTIVE: {WorkflowStatus.MEASURED},
    WorkflowStatus.MEASURED: set(),
    WorkflowStatus.REJECTED: set(),
}


def create_adjustment_workflow(
    workflow_id: str,
    item_id: str,
    base_version_id: str,
    *,
    requested_by: str,
    reason_code: str,
    evidence: list[Evidence],
    effective_from: date,
    effective_to: date,
    due_date: date,
) -> ForecastAdjustmentWorkflow:
    if not evidence:
        raise ValueError("forecast adjustment requires business evidence")
    return ForecastAdjustmentWorkflow(
        workflow_id=workflow_id,
        item_id=item_id,
        base_version_id=base_version_id,
        status=WorkflowStatus.DRAFT,
        requested_by=requested_by,
        reason_code=reason_code,
        evidence=evidence,
        effective_from=effective_from,
        effective_to=effective_to,
        due_date=due_date,
        source_versions={"base_forecast": base_version_id},
    )


def transition_adjustment(
    workflow: ForecastAdjustmentWorkflow,
    to_status: WorkflowStatus,
    *,
    actor: str,
    role: str,
    adjusted_version_id: str | None = None,
    comment: str = "",
) -> ForecastAdjustmentWorkflow:
    if to_status not in TRANSITIONS[workflow.status]:
        raise ValueError(f"invalid forecast workflow transition {workflow.status.value}->{to_status.value}")
    required_role = {
        WorkflowStatus.COMMERCIAL_REVIEW: {"销售", "市场", "项目"},
        WorkflowStatus.SUPPLY_REVIEW: {"计划", "供应链"},
        WorkflowStatus.APPROVED: {"计划经理", "S&OP负责人"},
        WorkflowStatus.EFFECTIVE: {"计划", "系统"},
        WorkflowStatus.MEASURED: {"计划", "系统"},
    }.get(to_status)
    if required_role and role not in required_role:
        raise ValueError(f"role {role} cannot transition to {to_status.value}")
    updated = workflow.model_copy(deep=True)
    if to_status == WorkflowStatus.COMMERCIAL_REVIEW:
        updated.commercial_reviewer = actor
    elif to_status == WorkflowStatus.SUPPLY_REVIEW:
        updated.supply_reviewer = actor
    elif to_status == WorkflowStatus.APPROVED:
        if not updated.commercial_reviewer or not updated.supply_reviewer:
            raise ValueError("commercial and supply reviews are required before approval")
        if not adjusted_version_id:
            raise ValueError("approved workflow requires adjusted forecast version id")
        updated.approver = actor
        updated.adjusted_version_id = adjusted_version_id
    updated.history.append({
        "from": workflow.status.value,
        "to": to_status.value,
        "actor": actor,
        "role": role,
        "comment": comment,
        "at": utc_now().isoformat(),
    })
    updated.status = to_status
    return updated


def record_workflow_fva(
    workflow: ForecastAdjustmentWorkflow,
    evaluation: dict[str, float | str | None],
    *,
    actor: str = "SYSTEM",
) -> ForecastAdjustmentWorkflow:
    if workflow.status != WorkflowStatus.EFFECTIVE:
        raise ValueError("FVA can be recorded only after workflow becomes effective")
    status = str(evaluation.get("status", ""))
    if status == "PENDING_ACTUALS":
        updated = workflow.model_copy(deep=True)
        updated.fva_status = status
        return updated
    allowed = {"IMPROVED", "WORSENED", "NO_MATERIAL_CHANGE", "NOT_EVALUABLE_ZERO_ACTUAL"}
    if status not in allowed:
        raise ValueError(f"unsupported FVA evaluation status {status}")
    fva = evaluation.get("fva")
    error_before = evaluation.get("error_before")
    error_after = evaluation.get("error_after")
    if status == "NOT_EVALUABLE_ZERO_ACTUAL":
        if fva is not None:
            raise ValueError("zero-actual FVA evaluation must not contain a numeric FVA")
    else:
        if not all(isinstance(value, (int, float)) for value in (fva, error_before, error_after)):
            raise ValueError("measured FVA requires numeric fva, error_before and error_after")
        if abs(float(fva) - (float(error_before) - float(error_after))) > 1e-9:
            raise ValueError("FVA must equal error_before - error_after")
    comment = f"{status}; FVA={fva}; before={error_before}; after={error_after}"
    updated = transition_adjustment(workflow, WorkflowStatus.MEASURED, actor=actor, role="系统", comment=comment)
    updated.fva = float(fva) if isinstance(fva, (int, float)) else None
    updated.fva_error_before = float(error_before) if isinstance(error_before, (int, float)) else None
    updated.fva_error_after = float(error_after) if isinstance(error_after, (int, float)) else None
    updated.fva_status = status
    return updated
