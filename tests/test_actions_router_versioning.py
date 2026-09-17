from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.demo import demo_histories, demo_projection
from src.models import Action, ActionType, ForecastAdjustment, ForecastConfidence, ProductLifecycle, ScenarioType
from src.router import route_scenario
from src.services.action_validation import validate_action_impact
from src.services.demand_classification import classify_demand
from src.services.forecasting import generate_forecast
from src.services.forecast_versioning import ForecastVersionService


def action(action_id, action_type, data, quantity, effective_index, **kwargs):
    return Action(
        action_id=action_id, action_type=action_type, object_id=f"OBJ-{action_id}",
        material_id=data.material_id, plant=data.plant, quantity=quantity,
        effective_week=data.weeks[effective_index].week_start,
        reason="test", execution_condition="approval", owner_department="计划/采购",
        due_date=data.weeks[0].week_start, **kwargs,
    )


def test_cancel_po_safe_is_recommended_and_requires_approval() -> None:
    data = demo_projection("CASE1", "MAT-A", "DEMO_PLANT")
    result = validate_action_impact(action("C1", ActionType.CANCEL_PO, data, 8000, 3), data, unit_cost=18)
    assert result.recommended
    assert result.approval_required
    assert result.action.approval is not None


def test_cancel_po_that_creates_shortage_is_rejected() -> None:
    data = demo_projection("CASE3", "MAT-C", "DEMO_PLANT")
    result = validate_action_impact(action("C2", ActionType.CANCEL_PO, data, 10000, 7), data)
    assert result.creates_new_shortage
    assert not result.recommended


def test_delay_po_causes_short_term_shortage() -> None:
    data = demo_projection("CASE2", "MAT-B", "TARGET_PLANT")
    delayed_week = data.weeks[10].week_start
    result = validate_action_impact(action("D1", ActionType.DELAY_PO, data, 5000, 5, target_week=delayed_week), data)
    assert result.creates_new_shortage


def test_transfer_cannot_create_source_shortage() -> None:
    target = demo_projection("CASE2", "MAT-B", "TARGET_PLANT")
    source = demo_projection("CASE2", "MAT-B", "SOURCE_PLANT")
    result = validate_action_impact(action("T1", ActionType.TRANSFER, target, 7000, 1, source_plant="SOURCE_PLANT"), target, related_inputs=[source])
    assert not result.recommended
    assert any(projection.plant == "SOURCE_PLANT" and projection.maximum_shortage_qty > 0 for projection in result.related_entity_results)


def test_substitute_shortage_is_rejected() -> None:
    original = demo_projection("CASE2", "MAT-B", "TARGET_PLANT")
    substitute = original.model_copy(deep=True)
    substitute.material_id = "SUB-M"
    substitute.on_hand = 100
    for row in substitute.weeks:
        row.gross_demand = 0
        row.po_receipt = 0
        row.safety_stock = 0
    act = action("S1", ActionType.SUBSTITUTE, original, 2000, 0, target_material_id="SUB-M")
    result = validate_action_impact(act, original, related_inputs=[substitute])
    assert result.creates_new_shortage
    assert not result.recommended


def test_ecn_consumption_reduces_excess() -> None:
    old = demo_projection("CASE1", "MAT-A", "DEMO_PLANT")
    new = old.model_copy(deep=True)
    new.material_id = "MAT-A-NEW"
    new.on_hand = 5000
    for row in new.weeks:
        row.gross_demand = 500
        row.po_receipt = 0
        row.safety_stock = 0
    act = action("E1", ActionType.ECN_SWITCH, old, 1000, 0, target_material_id="MAT-A-NEW", parameters={"mode": "consume_source_excess"})
    result = validate_action_impact(act, old, related_inputs=[new])
    assert result.excess_delta < 0
    assert result.approval_required


def test_action_result_is_traceable() -> None:
    data = demo_projection("CASE1", "MAT-A", "DEMO_PLANT")
    result = validate_action_impact(action("TRACE", ActionType.CANCEL_PO, data, 1000, 3), data)
    assert result.validation_id == "VAL-TRACE"
    assert result.baseline.source_versions == {"weekly_inventory": "DEMO-INV-V1"}
    assert result.scenario.points[0].calculation_basis


@pytest.mark.parametrize(("query", "expected"), [
    ("检查数据质量", ScenarioType.DATA_QUALITY),
    ("需求突增", ScenarioType.DEMAND_INCREASE),
    ("需求突降", ScenarioType.DEMAND_DECREASE),
    ("预测版本变化", ScenarioType.FORECAST_VERSION_CHANGE),
    ("做人工调整", ScenarioType.FORECAST_MANUAL_ADJUSTMENT),
    ("供应商延期", ScenarioType.SUPPLY_DELAY),
    ("中间周缺料", ScenarioType.DYNAMIC_SHORTAGE),
    ("低于安全库存", ScenarioType.BELOW_SAFETY_STOCK),
    ("库存冗余", ScenarioType.INVENTORY_EXCESS),
    ("呆滞库存", ScenarioType.OBSOLETE_INVENTORY),
    ("无需求但有在途PO", ScenarioType.NO_DEMAND_OPEN_PO),
    ("EOL库存", ScenarioType.EOL_INVENTORY),
    ("PO提前", ScenarioType.PO_EXPEDITE),
    ("PO延期", ScenarioType.PO_DELAY),
    ("PO减量", ScenarioType.PO_REDUCTION),
    ("PO取消", ScenarioType.PO_CANCELLATION),
    ("跨仓调拨", ScenarioType.CROSS_PLANT_TRANSFER),
    ("替代料", ScenarioType.SUBSTITUTE_MATERIAL),
    ("ECN切换", ScenarioType.ECN_SWITCH),
    ("情景模拟", ScenarioType.WHAT_IF_SIMULATION),
])
def test_router_covers_scenarios(query: str, expected: ScenarioType) -> None:
    assert route_scenario(query).scenario_type == expected


def test_facts_override_keyword_routing() -> None:
    assert route_scenario("库存冗余", facts={"blocking_data_quality": True}).scenario_type == ScenarioType.DATA_QUALITY


def test_forecast_versions_and_fva() -> None:
    histories, metadata = demo_histories()
    item = "PRODUCT_A"
    c = classify_demand({item: histories[item]}, source_version="T")[0]
    result = generate_forecast(item, histories[item], c, last_history_week=date.fromisoformat(metadata[item]["last_history_week"]), history_source="T")
    service = ForecastVersionService()
    statistical = service.create_statistical(item, result.points)
    point = statistical.points[0]
    adjustment = ForecastAdjustment(
        adjustment_id="A1", item_id=item, week_start=point.week_start,
        before_qty=point.baseline_qty, after_qty=point.baseline_qty + 100,
        reason_code="EVIDENCE", reason="confirmed order", adjusted_by="planner",
        effective_from=point.week_start, effective_to=point.week_start,
        confidence=ForecastConfidence.MEDIUM,
    )
    adjusted = service.create_adjusted(statistical.version_id, [adjustment], created_by="planner")
    assert service.evaluate_fva(statistical.version_id, adjusted.version_id, {})["status"] == "PENDING_ACTUALS"
    consensus = service.approve_consensus(adjusted.version_id, approved_by="manager")
    fva = service.evaluate_fva(statistical.version_id, adjusted.version_id, {point.week_start: point.baseline_qty + 100})
    assert fva["fva"] > 0
    assert service.planning_version(item)[0].version_id == consensus.version_id
