from __future__ import annotations

from datetime import date

from ..config import RulesConfig, load_rules
from ..models import ECNTransitionRecord, ECNValidationStatus, ECNWorkflow


ALLOWED_TRANSITIONS: dict[ECNValidationStatus, set[ECNValidationStatus]] = {
    ECNValidationStatus.CANDIDATE: {ECNValidationStatus.SPEC_REVIEW, ECNValidationStatus.REJECTED},
    ECNValidationStatus.SPEC_REVIEW: {ECNValidationStatus.TRIAL, ECNValidationStatus.REJECTED},
    ECNValidationStatus.TRIAL: {ECNValidationStatus.QUALITY_APPROVAL, ECNValidationStatus.REJECTED},
    ECNValidationStatus.QUALITY_APPROVAL: {ECNValidationStatus.CUSTOMER_APPROVAL, ECNValidationStatus.APPROVED, ECNValidationStatus.REJECTED},
    ECNValidationStatus.CUSTOMER_APPROVAL: {ECNValidationStatus.APPROVED, ECNValidationStatus.REJECTED},
    ECNValidationStatus.APPROVED: set(),
    ECNValidationStatus.REJECTED: set(),
}

ROLE_BY_STATUS = {
    ECNValidationStatus.SPEC_REVIEW: {"研发", "工程"},
    ECNValidationStatus.TRIAL: {"研发", "工程", "制造"},
    ECNValidationStatus.QUALITY_APPROVAL: {"质量"},
    ECNValidationStatus.CUSTOMER_APPROVAL: {"客户", "销售", "项目"},
    ECNValidationStatus.APPROVED: {"研发", "质量", "计划", "采购", "供应链负责人"},
    ECNValidationStatus.REJECTED: {"研发", "质量", "客户", "项目", "供应链负责人"},
}


def create_ecn_workflow(
    ecn_id: str,
    source_material: str,
    target_material: str,
    *,
    affected_products: list[str],
    customer_characteristic: bool,
    owner_department: str,
    due_date: date,
    data_version: str,
) -> ECNWorkflow:
    return ECNWorkflow(
        ecn_id=ecn_id,
        source_material=source_material,
        target_material=target_material,
        affected_products=affected_products,
        current_status=ECNValidationStatus.CANDIDATE,
        customer_characteristic=customer_characteristic,
        owner_department=owner_department,
        due_date=due_date,
        data_version=data_version,
    )


def transition_ecn(
    workflow: ECNWorkflow,
    to_status: ECNValidationStatus,
    *,
    actor: str,
    role: str,
    evidence_updates: dict[str, str] | None = None,
    comment: str = "",
    effective_batch: str | None = None,
    traceability_rule: str | None = None,
    rules: RulesConfig | None = None,
) -> ECNWorkflow:
    cfg = rules or load_rules()
    current = workflow.current_status
    if to_status not in ALLOWED_TRANSITIONS[current]:
        raise ValueError(f"invalid ECN transition {current.value}->{to_status.value}")
    if current == ECNValidationStatus.QUALITY_APPROVAL and workflow.customer_characteristic and to_status == ECNValidationStatus.APPROVED:
        raise ValueError("customer characteristic requires CUSTOMER_APPROVAL before APPROVED")
    allowed_roles = ROLE_BY_STATUS.get(to_status, set())
    if allowed_roles and role not in allowed_roles:
        raise ValueError(f"role {role} cannot approve transition to {to_status.value}")
    updated = workflow.model_copy(deep=True)
    updated.evidence.update(evidence_updates or {})
    if effective_batch:
        updated.effective_batch = effective_batch
        updated.evidence["effective_batch"] = effective_batch
    if traceability_rule:
        updated.traceability_rule = traceability_rule
        updated.evidence["traceability_rule"] = traceability_rule
    required = cfg.ecn_workflow.required_evidence.get(to_status.value, [])
    missing = [key for key in required if not updated.evidence.get(key)]
    if missing:
        raise ValueError(f"missing ECN evidence for {to_status.value}: {missing}")
    updated.approvals[to_status.value] = f"{actor}({role})"
    updated.history.append(ECNTransitionRecord(
        from_status=current,
        to_status=to_status,
        actor=actor,
        role=role,
        evidence_keys=sorted((evidence_updates or {}).keys()),
        comment=comment,
    ))
    updated.current_status = to_status
    return updated

