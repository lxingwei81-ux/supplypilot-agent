from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from src.models import (
    ActionType,
    ECNValidationStatus,
    Evidence,
    FieldMapping,
    ImportStatus,
    Risk,
    RiskLevel,
    RiskType,
    TaskStatus,
    WeeklySnapshot,
    WorkflowStatus,
)
from src.services.ecn_workflow import create_ecn_workflow, transition_ecn
from src.services.excel_import import import_excel, suggest_field_mapping
from src.services.forecast_adjustment_workflow import (
    create_adjustment_workflow,
    record_workflow_fva,
    transition_adjustment,
)
from src.services.snapshots import SnapshotStore
from src.services.task_management import RiskTaskService


TODAY = date(2026, 7, 21)


def ecn(*, customer_characteristic: bool = False):
    return create_ecn_workflow(
        "ECN-1", "OLD", "NEW", affected_products=["FG"],
        customer_characteristic=customer_characteristic, owner_department="研发",
        due_date=TODAY + timedelta(days=30), data_version="TEST-V1",
    )


def advance_to_quality(workflow):
    workflow = transition_ecn(
        workflow, ECNValidationStatus.SPEC_REVIEW, actor="engineer", role="研发",
        evidence_updates={"drawing_comparison": "D1", "specification_comparison": "S1"},
    )
    workflow = transition_ecn(
        workflow, ECNValidationStatus.TRIAL, actor="engineer", role="研发",
        evidence_updates={"trial_plan": "TP1"},
    )
    return transition_ecn(
        workflow, ECNValidationStatus.QUALITY_APPROVAL, actor="quality", role="质量",
        evidence_updates={"trial_result": "PASS", "quality_report": "QR1"},
    )


def test_ecn_rejects_invalid_jump_and_missing_evidence() -> None:
    workflow = ecn()
    with pytest.raises(ValueError, match="invalid ECN transition"):
        transition_ecn(workflow, ECNValidationStatus.TRIAL, actor="engineer", role="研发")
    with pytest.raises(ValueError, match="missing ECN evidence"):
        transition_ecn(workflow, ECNValidationStatus.SPEC_REVIEW, actor="engineer", role="研发")


def test_ecn_rejects_wrong_approval_role() -> None:
    with pytest.raises(ValueError, match="cannot approve"):
        transition_ecn(
            ecn(), ECNValidationStatus.SPEC_REVIEW, actor="buyer", role="采购",
            evidence_updates={"drawing_comparison": "D1", "specification_comparison": "S1"},
        )


def test_customer_characteristic_requires_customer_approval() -> None:
    workflow = advance_to_quality(ecn(customer_characteristic=True))
    with pytest.raises(ValueError, match="requires CUSTOMER_APPROVAL"):
        transition_ecn(
            workflow, ECNValidationStatus.APPROVED, actor="planner", role="计划",
            effective_batch="B1", traceability_rule="OLD_FIRST",
        )
    workflow = transition_ecn(
        workflow, ECNValidationStatus.CUSTOMER_APPROVAL, actor="sales", role="销售",
        evidence_updates={"customer_submission": "APPROVED"},
    )
    workflow = transition_ecn(
        workflow, ECNValidationStatus.APPROVED, actor="planner", role="计划",
        effective_batch="B1", traceability_rule="OLD_FIRST",
    )
    assert workflow.current_status == ECNValidationStatus.APPROVED
    assert len(workflow.history) == 5


def evidence() -> list[Evidence]:
    return [Evidence(source="CUSTOMER", description="Customer commitment changed", value="CONFIRMED")]


def adjustment_workflow():
    return create_adjustment_workflow(
        "WF-1", "FG", "STAT-1", requested_by="planner", reason_code="COMMITMENT",
        evidence=evidence(), effective_from=TODAY, effective_to=TODAY + timedelta(weeks=4),
        due_date=TODAY + timedelta(days=2),
    )


def test_forecast_adjustment_requires_evidence() -> None:
    with pytest.raises(ValueError, match="requires business evidence"):
        create_adjustment_workflow(
            "WF", "FG", "STAT", requested_by="planner", reason_code="OTHER", evidence=[],
            effective_from=TODAY, effective_to=TODAY, due_date=TODAY,
        )


def test_forecast_adjustment_role_gates_and_full_path() -> None:
    workflow = transition_adjustment(adjustment_workflow(), WorkflowStatus.SUBMITTED, actor="planner", role="计划")
    with pytest.raises(ValueError, match="cannot transition"):
        transition_adjustment(workflow, WorkflowStatus.COMMERCIAL_REVIEW, actor="buyer", role="采购")
    workflow = transition_adjustment(workflow, WorkflowStatus.COMMERCIAL_REVIEW, actor="sales", role="销售")
    workflow = transition_adjustment(workflow, WorkflowStatus.SUPPLY_REVIEW, actor="supply", role="供应链")
    workflow = transition_adjustment(workflow, WorkflowStatus.PENDING_APPROVAL, actor="supply", role="供应链")
    with pytest.raises(ValueError, match="version id"):
        transition_adjustment(workflow, WorkflowStatus.APPROVED, actor="manager", role="计划经理")
    workflow = transition_adjustment(
        workflow, WorkflowStatus.APPROVED, actor="manager", role="计划经理",
        adjusted_version_id="ADJ-1",
    )
    workflow = transition_adjustment(workflow, WorkflowStatus.EFFECTIVE, actor="planner", role="计划")
    pending = record_workflow_fva(workflow, {"fva": None, "status": "PENDING_ACTUALS"}, actor="SYSTEM")
    assert pending.status == WorkflowStatus.EFFECTIVE
    workflow = record_workflow_fva(
        workflow,
        {"fva": 0.1, "status": "IMPROVED", "error_before": 0.2, "error_after": 0.1},
        actor="SYSTEM",
    )
    assert workflow.status == WorkflowStatus.MEASURED
    assert workflow.fva_status == "IMPROVED"
    assert workflow.fva == pytest.approx(0.1)


def test_forecast_workflow_rejects_unverified_fva_claim() -> None:
    workflow = transition_adjustment(adjustment_workflow(), WorkflowStatus.SUBMITTED, actor="planner", role="计划")
    workflow = transition_adjustment(workflow, WorkflowStatus.COMMERCIAL_REVIEW, actor="sales", role="销售")
    workflow = transition_adjustment(workflow, WorkflowStatus.SUPPLY_REVIEW, actor="supply", role="供应链")
    workflow = transition_adjustment(workflow, WorkflowStatus.PENDING_APPROVAL, actor="supply", role="供应链")
    workflow = transition_adjustment(
        workflow, WorkflowStatus.APPROVED, actor="manager", role="计划经理", adjusted_version_id="ADJ-1",
    )
    workflow = transition_adjustment(workflow, WorkflowStatus.EFFECTIVE, actor="planner", role="计划")
    with pytest.raises(ValueError, match="requires numeric"):
        record_workflow_fva(workflow, {"fva": None, "status": "IMPROVED"})
    with pytest.raises(ValueError, match="must equal"):
        record_workflow_fva(
            workflow,
            {"fva": 0.5, "status": "IMPROVED", "error_before": 0.2, "error_after": 0.1},
        )


def snapshot(snapshot_id: str, week: date, value: float) -> WeeklySnapshot:
    return WeeklySnapshot(
        snapshot_id=snapshot_id, as_of_week=week, entity_type="MATERIAL", entity_id="M",
        plant="P", metrics={"excess": value}, source_versions={"inventory": "TEST-V1"},
    )


def test_snapshot_persists_reloads_and_computes_trend(tmp_path) -> None:
    path = tmp_path / "snapshots.json"
    store = SnapshotStore(path)
    store.add(snapshot("S1", TODAY, 100))
    store.add(snapshot("S2", TODAY + timedelta(weeks=1), 70))
    reloaded = SnapshotStore(path)
    trend = reloaded.trends("M", "excess", 4)
    assert len(reloaded.list(entity_id="M")) == 2
    assert trend.direction == "DOWN"
    assert trend.change_rate == pytest.approx(-0.3)
    with pytest.raises(ValueError, match="duplicate snapshot"):
        reloaded.add(snapshot("S2", TODAY + timedelta(weeks=2), 50))


def test_excel_alias_mapping_and_valid_import(tmp_path) -> None:
    path = tmp_path / "input.xlsx"
    pd.DataFrame({"物料编码": ["M1"], "周开始": ["2026-07-20"], "需求数量": ["12.5"]}).to_excel(path, index=False)
    suggested = suggest_field_mapping(["物料编码", "周开始", "需求数量"], ["item_id", "week_start", "demand_qty"])
    assert suggested == {"item_id": "物料编码", "week_start": "周开始", "demand_qty": "需求数量"}
    result = import_excel(
        path, sheet_name="Sheet1", data_version="UPLOAD-V1",
        mappings=[
            FieldMapping(target_field="item_id", source_column="物料编码", required=True),
            FieldMapping(target_field="week_start", source_column="周开始", required=True, data_type="date"),
            FieldMapping(target_field="demand_qty", source_column="需求数量", required=True, data_type="float"),
        ],
    )
    assert result.status == ImportStatus.IMPORTED
    assert result.rows[0]["demand_qty"] == 12.5
    assert result.rows[0]["week_start"] == date(2026, 7, 20)


def test_excel_missing_column_and_invalid_type_are_blocking(tmp_path) -> None:
    missing_path = tmp_path / "missing.xlsx"
    pd.DataFrame({"SKU": ["M1"]}).to_excel(missing_path, index=False)
    missing = import_excel(
        missing_path, sheet_name="Sheet1", data_version="V",
        mappings=[FieldMapping(target_field="demand_qty", source_column="QTY", required=True, data_type="float")],
    )
    assert missing.status == ImportStatus.BLOCKED
    assert missing.unmapped_required_fields == ["demand_qty"]

    invalid_path = tmp_path / "invalid.xlsx"
    pd.DataFrame({"QTY": ["not-a-number"]}).to_excel(invalid_path, index=False)
    invalid = import_excel(
        invalid_path, sheet_name="Sheet1", data_version="V",
        mappings=[FieldMapping(target_field="demand_qty", source_column="QTY", required=True, data_type="float")],
    )
    assert invalid.status == ImportStatus.BLOCKED
    assert invalid.issues[0].code == "INVALID_FIELD_TYPE"


def risk(*, due_date: date = TODAY + timedelta(days=1), level: RiskLevel = RiskLevel.HIGH) -> Risk:
    return Risk(
        risk_id="R1", risk_type=RiskType.SHORTAGE, level=level, material_id="M", plant="P",
        quantity=10, value=100, root_causes=["DELAY"],
        evidence=[Evidence(source="TEST", description="Projection shortage", value=10)],
        suggested_actions=[ActionType.EXPEDITE_PO], owner_department="采购",
        latest_action_date=due_date, source_version="TEST-V1",
    )


def test_risk_task_priority_transition_reminder_and_escalation() -> None:
    service = RiskTaskService()
    task = service.create_from_risk(risk(), assignee="buyer", approvers=["manager"])
    assert task.priority.value == "P1"
    reminders = service.generate_notifications(TODAY)
    assert [item.notification_type for item in reminders] == ["DUE_REMINDER"]
    assert service.generate_notifications(TODAY) == []
    escalations = service.generate_notifications(TODAY + timedelta(days=8))
    assert escalations[0].notification_type == "OVERDUE_ESCALATION_3"
    assert service.list_tasks()[0].escalation_level == 3
    task = service.transition(task.task_id, TaskStatus.ACKNOWLEDGED, actor="buyer")
    task = service.transition(task.task_id, TaskStatus.IN_PROGRESS, actor="buyer")
    task = service.transition(task.task_id, TaskStatus.COMPLETED, actor="buyer")
    assert task.completed_at is not None


def test_risk_task_duplicate_and_invalid_transition_are_rejected() -> None:
    service = RiskTaskService()
    task = service.create_from_risk(risk(), assignee="buyer")
    with pytest.raises(ValueError, match="duplicate task"):
        service.create_from_risk(risk(), assignee="buyer")
    with pytest.raises(ValueError, match="invalid task transition"):
        service.transition(task.task_id, TaskStatus.COMPLETED, actor="buyer")
