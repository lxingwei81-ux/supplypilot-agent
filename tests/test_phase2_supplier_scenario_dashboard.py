from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.models import (
    ActionType,
    DataQualityIssue,
    DataQualityReport,
    DataQualitySeverity,
    DemandScenario,
    Evidence,
    InventoryDecision,
    InventoryProjectionInput,
    OptimizationStatus,
    Risk,
    RiskLevel,
    RiskType,
    SupplierDeliveryRecord,
    TaskStatus,
    WeeklyInventoryInput,
)
from src.services.dashboard import build_management_dashboard
from src.services.scenario_optimization import optimize_inventory_across_scenarios
from src.services.supplier_reliability import calculate_supplier_reliability
from src.services.task_management import RiskTaskService


START = date(2026, 7, 20)


def delivery(
    document_id: str,
    *,
    promised_offset: int = 10,
    actual_offset: int = 10,
    received: float = 100,
    confirmed: bool = True,
) -> SupplierDeliveryRecord:
    return SupplierDeliveryRecord(
        supplier_id="S1", document_id=document_id, order_date=START,
        promised_date=START + timedelta(days=promised_offset),
        confirmed_date=START + timedelta(days=promised_offset) if confirmed else None,
        actual_date=START + timedelta(days=actual_offset),
        ordered_qty=100, received_qty=received, data_version="TEST-V1",
    )


def test_supplier_perfect_delivery_scores_a() -> None:
    records = [delivery(f"PO{i}") for i in range(5)]
    result = calculate_supplier_reliability("S1", records)
    assert result.on_time_rate == 1
    assert result.quantity_fill_rate == 1
    assert result.confirmation_adherence == 1
    assert result.reliability_score == pytest.approx(1)
    assert result.grade == "A"
    assert result.warnings == []


def test_supplier_late_short_and_missing_confirmation_is_penalized() -> None:
    records = [delivery("PO1", actual_offset=20, received=50, confirmed=False)]
    result = calculate_supplier_reliability("S1", records)
    assert result.on_time_rate == 0
    assert result.quantity_fill_rate == 0.5
    assert result.confirmation_adherence == 0
    assert result.grade in {"C", "D"}
    assert len(result.warnings) == 2


def test_supplier_unknown_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="no delivery records"):
        calculate_supplier_reliability("UNKNOWN", [delivery("PO1")])


def baseline(on_hand: float = 0) -> InventoryProjectionInput:
    return InventoryProjectionInput(
        material_id="M", plant="P", on_hand=on_hand,
        weeks=[
            WeeklyInventoryInput(week_start=START + timedelta(weeks=index), gross_demand=10, safety_stock=0)
            for index in range(3)
        ],
        data_version="TEST-V1",
    )


def scenarios() -> list[DemandScenario]:
    return [
        DemandScenario(scenario_id="BASE", probability=0.5, demand_multiplier=1, description="base"),
        DemandScenario(scenario_id="HIGH", probability=0.5, demand_multiplier=2, description="high"),
    ]


def test_multi_scenario_selects_only_robust_zero_shortage_decision() -> None:
    result = optimize_inventory_across_scenarios(
        baseline(), scenarios=scenarios(), decisions=[
            InventoryDecision(decision_id="NO_ACTION"),
            InventoryDecision(decision_id="ORDER_30", order_qty=30, order_week=START),
            InventoryDecision(decision_id="ORDER_60", order_qty=60, order_week=START, action_cost=5),
        ],
    )
    assert result.status == OptimizationStatus.OPTIMAL
    assert result.robust_feasible_decisions == ["ORDER_60"]
    assert result.selected_decision_id == "ORDER_60"
    assert all(row.maximum_shortage == 0 for row in result.evaluations if row.decision_id == "ORDER_60")


def test_multi_scenario_returns_no_recommendation_when_all_decisions_unsafe() -> None:
    result = optimize_inventory_across_scenarios(
        baseline(), scenarios=scenarios(), decisions=[InventoryDecision(decision_id="NO_ACTION")],
    )
    assert result.status == OptimizationStatus.INFEASIBLE
    assert result.selected_decision_id is None
    assert "no unsafe decision" in result.infeasible_reasons[0]


def test_multi_scenario_probability_and_date_validation() -> None:
    with pytest.raises(ValueError, match="sum to 1"):
        optimize_inventory_across_scenarios(
            baseline(),
            scenarios=[DemandScenario(scenario_id="X", probability=0.8, demand_multiplier=1, description="x")],
            decisions=[InventoryDecision(decision_id="D")],
        )
    with pytest.raises(ValueError, match="outside projection horizon"):
        optimize_inventory_across_scenarios(
            baseline(on_hand=100), scenarios=scenarios(),
            decisions=[InventoryDecision(decision_id="BAD", order_qty=1, order_week=START + timedelta(weeks=9))],
        )


def test_multi_scenario_result_is_reproducible() -> None:
    decisions = [InventoryDecision(decision_id="ORDER", order_qty=60, order_week=START)]
    first = optimize_inventory_across_scenarios(baseline(), scenarios=scenarios(), decisions=decisions)
    second = optimize_inventory_across_scenarios(baseline(), scenarios=scenarios(), decisions=decisions)
    assert first.model_dump(exclude={"calculated_at"}) == second.model_dump(exclude={"calculated_at"})


def make_risk(risk_id: str, risk_type: RiskType, level: RiskLevel, value: float) -> Risk:
    return Risk(
        risk_id=risk_id, risk_type=risk_type, level=level, material_id="M", plant="P",
        quantity=10, value=value, root_causes=["TEST"],
        evidence=[Evidence(source="TEST", description="Risk evidence", value=value)],
        suggested_actions=[ActionType.EXPEDITE_PO], owner_department="计划",
        latest_action_date=START, source_version="TEST-V1",
    )


def test_dashboard_aggregates_risks_tasks_suppliers_and_severity_order() -> None:
    risks = [
        make_risk("LOW", RiskType.EXCESS, RiskLevel.LOW, 10000),
        make_risk("CRIT", RiskType.SHORTAGE, RiskLevel.CRITICAL, 1),
    ]
    service = RiskTaskService()
    first_task = service.create_from_risk(risks[0], assignee="owner")
    second_task = service.create_from_risk(risks[1], assignee="owner")
    service.transition(second_task.task_id, TaskStatus.ACKNOWLEDGED, actor="owner")
    service.transition(second_task.task_id, TaskStatus.IN_PROGRESS, actor="owner")
    service.transition(second_task.task_id, TaskStatus.PENDING_APPROVAL, actor="owner")
    data_quality = DataQualityReport(
        report_id="DQ", data_version="V", tables_checked=["T"],
        issues=[DataQualityIssue(
            code="BLOCK", severity=DataQualitySeverity.BLOCKING, message="x", table="T",
            blocking=True, impact="blocked",
        )],
    )
    supplier = calculate_supplier_reliability("S1", [delivery(f"PO{i}") for i in range(5)])
    dashboard = build_management_dashboard(
        data_quality=data_quality, forecasts=[], risks=risks,
        tasks=service.list_tasks(), suppliers=[supplier], source_versions={"all": "TEST-V1"},
    )
    assert dashboard.data_quality_blockers == 1
    assert dashboard.shortage_risk_count == 1
    assert dashboard.excess_risk_count == 1
    assert dashboard.pending_approval_count == 1
    assert dashboard.supplier_grade_distribution == {"A": 1}
    assert dashboard.top_risks[0]["risk_id"] == "CRIT"
