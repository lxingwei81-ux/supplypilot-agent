from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.demo import demo_bom_rows, demo_histories, demo_projection
from src.models import (
    Action,
    ActionType,
    ForecastAdjustment,
    ForecastConfidence,
    InventoryProjectionInput,
    ProductLifecycle,
    WeeklyInventoryInput,
)
from src.router import route_scenario
from src.services.action_validation import validate_action_impact
from src.services.bom import explode_bom
from src.services.demand_classification import classify_demand
from src.services.forecasting import generate_forecast
from src.services.forecast_versioning import ForecastVersionService
from src.services.inventory_projection import project_inventory_by_week
from src.services.risks import identify_projection_risks


def _json(value: object) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def case1() -> dict[str, object]:
    projection_input = demo_projection("CASE1", "MAT-A", "DEMO_PLANT")
    baseline = project_inventory_by_week(projection_input)
    weekly_product_forecast = {week.week_start: 600.0 for week in projection_input.weeks}
    requirements = explode_bom("PRODUCT_A", weekly_product_forecast, demo_bom_rows(), forecast_version_id="CONSENSUS-DEMO-600")
    risks = identify_projection_risks(
        baseline,
        unit_cost=18,
        affected_products=["PRODUCT_A"],
        context={"forecast_down_consecutive": True, "demand_change_rate": -0.4, "open_po": 16000},
    )
    receipt_week = projection_input.weeks[3].week_start
    cancel = Action(
        action_id="CASE1-CANCEL",
        action_type=ActionType.CANCEL_PO,
        object_id="PO-DEMO-A-1",
        material_id="MAT-A",
        plant="DEMO_PLANT",
        quantity=8000,
        effective_week=receipt_week,
        reason="产品A周需求由1000下降到600，减少未锁定在途",
        execution_condition="供应商确认未投产及取消费用后，由计划与采购审批",
        owner_department="采购",
        due_date=receipt_week - timedelta(days=14),
    )
    cancellation_validation = validate_action_impact(cancel, projection_input, unit_cost=18)
    ecn = Action(
        action_id="CASE1-ECN",
        action_type=ActionType.ECN_SWITCH,
        object_id="ECN-DEMO-A",
        material_id="MAT-A",
        target_material_id="MAT-A-NEW",
        plant="DEMO_PLANT",
        quantity=2000,
        effective_week=projection_input.weeks[0].week_start,
        reason="候选ECN优先消耗旧料MAT-A",
        execution_condition="图纸/功能/质量/PPAP及必要客户批准全部完成",
        owner_department="研发/质量",
        due_date=projection_input.weeks[0].week_start,
        parameters={"mode": "consume_source_excess"},
    )
    new_material = projection_input.model_copy(deep=True)
    new_material.material_id = "MAT-A-NEW"
    new_material.on_hand = 10000
    for week in new_material.weeks:
        week.gross_demand = 500
        week.po_receipt = 0
        week.safety_stock = 500
    ecn_validation = validate_action_impact(ecn, projection_input, related_inputs=[new_material], unit_cost=18)
    return {
        "case": "需求下降导致冗余",
        "route": route_scenario("产品A需求下降并评估取消PO", facts={"demand_change_rate": -0.4}).model_dump(mode="json"),
        "bom_material_requirements": {row.material_id: sum(item.gross_requirement for item in requirements if item.material_id == row.material_id) for row in requirements},
        "baseline_ending_excess": baseline.ending_excess_qty,
        "risk_count": len(risks),
        "cancel_po_validation": cancellation_validation.model_dump(mode="json"),
        "ecn_validation": ecn_validation.model_dump(mode="json"),
    }


def case2() -> dict[str, object]:
    target = demo_projection("CASE2", "MAT-B", "TARGET_PLANT")
    source = demo_projection("CASE2", "MAT-B", "SOURCE_PLANT")
    baseline = project_inventory_by_week(target)
    original_receipt = target.weeks[5].week_start
    earlier_week = target.weeks[2].week_start
    expedite = Action(
        action_id="CASE2-EXPEDITE", action_type=ActionType.EXPEDITE_PO, object_id="PO-DEMO-B",
        material_id="MAT-B", plant="TARGET_PLANT", quantity=5000,
        effective_week=original_receipt, target_week=earlier_week,
        reason="需求上升且供应商交期延长，提前现有PO", execution_condition="供应商重新承诺",
        owner_department="采购", due_date=target.weeks[0].week_start,
    )
    transfer = Action(
        action_id="CASE2-TRANSFER", action_type=ActionType.TRANSFER, object_id="TR-DEMO-B",
        material_id="MAT-B", plant="TARGET_PLANT", source_plant="SOURCE_PLANT", quantity=2000,
        effective_week=target.weeks[3].week_start,
        reason="来源工厂存在可用库存", execution_condition="批次、质量和版本兼容",
        owner_department="物流/计划", due_date=target.weeks[1].week_start,
    )
    return {
        "case": "需求上升导致缺料",
        "baseline_first_shortage_week": baseline.first_shortage_week,
        "baseline_maximum_shortage": baseline.maximum_shortage_qty,
        "po_expedite": validate_action_impact(expedite, target, unit_cost=45).model_dump(mode="json"),
        "cross_plant_transfer": validate_action_impact(transfer, target, related_inputs=[source], unit_cost=45).model_dump(mode="json"),
    }


def case3() -> dict[str, object]:
    data = demo_projection("CASE3", "MAT-C", "DEMO_PLANT")
    baseline = project_inventory_by_week(data)
    static_surplus = data.on_hand + sum(week.po_receipt for week in data.weeks) - sum(week.gross_demand for week in data.weeks)
    expedite = Action(
        action_id="CASE3-EXPEDITE", action_type=ActionType.EXPEDITE_PO, object_id="PO-DEMO-C",
        material_id="MAT-C", plant="DEMO_PLANT", quantity=4000,
        effective_week=data.weeks[7].week_start, target_week=data.weeks[4].week_start,
        reason="总量充足但PO晚到导致中间周缺料", execution_condition="供应商同意拆分并提前首批",
        owner_department="采购", due_date=data.weeks[1].week_start,
    )
    return {
        "case": "总量不缺但中间周缺料",
        "static_total_surplus": static_surplus,
        "weekly_first_shortage_week": baseline.first_shortage_week,
        "weekly_maximum_shortage": baseline.maximum_shortage_qty,
        "expedite_validation": validate_action_impact(expedite, data, unit_cost=20).model_dump(mode="json"),
    }


def case4() -> dict[str, object]:
    histories, metadata = demo_histories()
    item = "INTERMITTENT_M"
    classification = classify_demand(
        {item: histories[item]}, unit_costs={item: metadata[item]["unit_cost"]},
        lifecycles={item: ProductLifecycle.SERVICE}, source_version=metadata[item]["data_version"],
    )[0]
    forecast = generate_forecast(
        item, histories[item], classification,
        last_history_week=date.fromisoformat(metadata[item]["last_history_week"]),
        history_source=metadata[item]["data_version"], stockout_unit_cost=metadata[item]["unit_cost"],
    )
    return {
        "case": "间歇性需求预测",
        "classification": classification.model_dump(mode="json"),
        "selected_model": forecast.selected_model,
        "candidate_metrics": [metric.model_dump(mode="json") for metric in forecast.candidate_metrics],
        "confidence": forecast.confidence.value,
        "horizon_totals": forecast.horizon_totals,
    }


def case5() -> dict[str, object]:
    histories, metadata = demo_histories()
    item = "PRODUCT_A"
    classification = classify_demand(
        {item: histories[item]}, unit_costs={item: metadata[item]["unit_cost"]},
        source_version=metadata[item]["data_version"],
    )[0]
    result = generate_forecast(
        item, histories[item], classification,
        last_history_week=date.fromisoformat(metadata[item]["last_history_week"]),
        history_source=metadata[item]["data_version"],
    )
    service = ForecastVersionService()
    statistical = service.create_statistical(item, result.points)
    point = statistical.points[0]
    adjustment = ForecastAdjustment(
        adjustment_id="CASE5-ADJ", item_id=item, week_start=point.week_start,
        before_qty=point.baseline_qty, after_qty=point.baseline_qty + 100,
        reason_code="CUSTOMER_COMMITMENT", reason="客户确认新增项目需求",
        adjusted_by="planner_demo", approved_by="manager_demo",
        effective_from=point.week_start, effective_to=point.week_start,
        confidence=ForecastConfidence.MEDIUM,
    )
    adjusted = service.create_adjusted(statistical.version_id, [adjustment], created_by="planner_demo")
    consensus = service.approve_consensus(adjusted.version_id, approved_by="manager_demo")
    actuals = {point.week_start: point.baseline_qty + 100}
    fva = service.evaluate_fva(statistical.version_id, adjusted.version_id, actuals)
    return {
        "case": "人工调整及FVA",
        "statistical_version": statistical.version_id,
        "adjusted_version": adjusted.version_id,
        "consensus_version": consensus.version_id,
        "planning_version": service.planning_version(item)[1],
        "fva": fva,
    }


CASES = {"1": case1, "2": case2, "3": case3, "4": case4, "5": case5}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic SupplyPilot business cases")
    parser.add_argument("--case", choices=[*CASES, "all"], default="all")
    args = parser.parse_args()
    output = {key: function() for key, function in CASES.items()} if args.case == "all" else CASES[args.case]()
    print(_json(output))


if __name__ == "__main__":
    main()
