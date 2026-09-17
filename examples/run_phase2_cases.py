from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.demo import (
    demo_atp_demands,
    demo_histories,
    demo_po_options,
    demo_price_breaks,
    demo_projection,
    demo_supplier_records,
    demo_transfer_network,
)
from src.models import (
    DemandScenario,
    ECNValidationStatus,
    Evidence,
    FieldMapping,
    InventoryDecision,
    WeeklySnapshot,
    WorkflowStatus,
)
from src.services.allocation import allocate_shared_material_atp
from src.services.dashboard import build_management_dashboard
from src.services.data_quality import assess_project_data
from src.services.demand_classification import classify_demand
from src.services.ecn_workflow import create_ecn_workflow, transition_ecn
from src.services.excel_import import import_excel, suggest_field_mapping
from src.services.forecast_adjustment_workflow import (
    create_adjustment_workflow,
    record_workflow_fva,
    transition_adjustment,
)
from src.services.forecasting import generate_forecast
from src.services.inventory_projection import project_inventory_by_week
from src.services.procurement_optimization import optimize_po_reduction_plan, optimize_replenishment_order
from src.services.risks import identify_projection_risks
from src.services.scenario_optimization import optimize_inventory_across_scenarios
from src.services.snapshots import SnapshotStore
from src.services.supplier_reliability import calculate_supplier_reliability
from src.services.task_management import RiskTaskService
from src.services.transfer_optimization import optimize_cross_plant_transfer


AS_OF = date(2026, 7, 21)


def output(value) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def case_1_atp() -> None:
    output(allocate_shared_material_atp(
        "COMMON-M", available_supply=13000, protected_supply=1000,
        demands=demo_atp_demands(), source_versions={"demand": "DEMO-ATP-V1"},
    ))


def case_2_transfer() -> None:
    sources, targets, lanes = demo_transfer_network()
    output(optimize_cross_plant_transfer(
        "MAT-B", as_of_date=AS_OF, sources=sources, targets=targets, lanes=lanes,
    ))


def case_3_po_cost() -> None:
    output(optimize_po_reduction_plan(
        "MAT-A", "DEMO_PLANT", excess_qty=9000,
        po_options=demo_po_options(), as_of_date=AS_OF, horizon_weeks=13,
    ))


def case_4_lot_price() -> None:
    price_breaks, lot_rules = demo_price_breaks()
    output(optimize_replenishment_order(
        "MAT-B", required_qty=4700, price_breaks=price_breaks, **lot_rules,
    ))


def case_5_ecn() -> None:
    workflow = create_ecn_workflow(
        "ECN-DEMO-001", "MAT-A", "MAT-A-NEW", affected_products=["PRODUCT_A"],
        customer_characteristic=False, owner_department="研发",
        due_date=date(2026, 9, 1), data_version="DEMO-ECN-V1",
    )
    workflow = transition_ecn(
        workflow, ECNValidationStatus.SPEC_REVIEW, actor="demo_engineer", role="研发",
        evidence_updates={"drawing_comparison": "DRAWING-001", "specification_comparison": "SPEC-001"},
    )
    workflow = transition_ecn(
        workflow, ECNValidationStatus.TRIAL, actor="demo_engineer", role="研发",
        evidence_updates={"trial_plan": "TRIAL-001"},
    )
    workflow = transition_ecn(
        workflow, ECNValidationStatus.QUALITY_APPROVAL, actor="demo_quality", role="质量",
        evidence_updates={"trial_result": "PASS", "quality_report": "QUALITY-001"},
    )
    workflow = transition_ecn(
        workflow, ECNValidationStatus.APPROVED, actor="demo_planner", role="计划",
        effective_batch="BATCH-2026-09", traceability_rule="OLD_STOCK_FIRST",
    )
    output(workflow)


def case_6_snapshots() -> None:
    store = SnapshotStore()
    for index, quantity in enumerate([12000, 11000, 9000, 7200, 6000]):
        store.add(WeeklySnapshot(
            snapshot_id=f"SNAP-{index}", as_of_week=date(2026, 6, 29) + timedelta(weeks=index),
            entity_type="MATERIAL", entity_id="MAT-A", plant="DEMO_PLANT",
            metrics={"excess_qty": quantity, "excess_value": quantity * 18},
            source_versions={"inventory": f"DEMO-W{index}"},
        ))
    output({
        "snapshots": [row.model_dump(mode="json") for row in store.list(entity_id="MAT-A")],
        "trend": store.trends("MAT-A", "excess_qty", 4).model_dump(mode="json"),
    })


def case_7_forecast_workflow() -> None:
    workflow = create_adjustment_workflow(
        "FAW-DEMO-001", "PRODUCT_A", "STAT-001", requested_by="demo_planner",
        reason_code="CUSTOMER_COMMITMENT",
        evidence=[Evidence(source="CUSTOMER_CONFIRMATION", description="客户确认项目需求变化", value="CONFIRMED")],
        effective_from=date(2026, 8, 3), effective_to=date(2026, 8, 31), due_date=date(2026, 7, 30),
    )
    for status, actor, role in [
        (WorkflowStatus.SUBMITTED, "demo_planner", "计划"),
        (WorkflowStatus.COMMERCIAL_REVIEW, "demo_sales", "销售"),
        (WorkflowStatus.SUPPLY_REVIEW, "demo_supply", "供应链"),
        (WorkflowStatus.PENDING_APPROVAL, "demo_supply", "供应链"),
    ]:
        workflow = transition_adjustment(workflow, status, actor=actor, role=role)
    workflow = transition_adjustment(
        workflow, WorkflowStatus.APPROVED, actor="demo_manager", role="计划经理",
        adjusted_version_id="ADJ-DEMO-001",
    )
    workflow = transition_adjustment(workflow, WorkflowStatus.EFFECTIVE, actor="demo_planner", role="计划")
    workflow = record_workflow_fva(workflow, {"fva": None, "status": "PENDING_ACTUALS"}, actor="SYSTEM")
    output(workflow)


def case_8_excel_mapping() -> None:
    frame = pd.DataFrame({
        "物料编码": ["MAT-A", "MAT-B"],
        "周开始": ["2026-08-03", "2026-08-03"],
        "需求数量": [600, 1200],
        "工厂": ["DEMO_PLANT", "TARGET_PLANT"],
        "客户": ["CUSTOMER_A", "CUSTOMER_B"],
    })
    fields = ["item_id", "week_start", "demand_qty", "plant", "customer"]
    suggested = suggest_field_mapping(list(frame.columns), fields)
    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as handle:
            path = Path(handle.name)
        frame.to_excel(path, index=False)
        mappings = [FieldMapping(
            target_field=field, source_column=suggested[field], required=field in {"item_id", "week_start", "demand_qty"},
            data_type="date" if field == "week_start" else ("float" if field == "demand_qty" else "str"),
        ) for field in fields]
        output(import_excel(path, sheet_name="Sheet1", mappings=mappings, data_version="DEMO-UPLOAD-V1"))
    finally:
        if path and path.exists():
            path.unlink()


def case_9_tasks_and_supplier() -> None:
    projection = project_inventory_by_week(demo_projection("CASE2", "MAT-B", "TARGET_PLANT"))
    risks = identify_projection_risks(projection, unit_cost=45, context={"supplier_delay": True})
    task_service = RiskTaskService()
    for risk in risks:
        task_service.create_from_risk(risk, assignee="demo_buyer", approvers=["采购经理", "计划经理"])
    records = demo_supplier_records()
    supplier_results = [
        calculate_supplier_reliability(supplier, records)
        for supplier in sorted({record.supplier_id for record in records})
    ]
    output({
        "tasks": [task.model_dump(mode="json") for task in task_service.list_tasks()],
        "notifications": [item.model_dump(mode="json") for item in task_service.generate_notifications(date(2026, 8, 25))],
        "supplier_reliability": [item.model_dump(mode="json") for item in supplier_results],
    })


def case_10_scenario_cost() -> None:
    baseline = demo_projection("CASE3", "MAT-C", "DEMO_PLANT")
    scenarios = [
        DemandScenario(scenario_id="LOW", probability=0.2, demand_multiplier=0.8, description="需求下降"),
        DemandScenario(scenario_id="BASE", probability=0.5, demand_multiplier=1, description="基准"),
        DemandScenario(scenario_id="HIGH_DELAY", probability=0.3, demand_multiplier=1.15, po_delay_weeks=1, description="上升且延期"),
    ]
    decisions = [
        InventoryDecision(decision_id="NO_ACTION"),
        InventoryDecision(decision_id="ORDER_4000", order_qty=4000, order_week=baseline.weeks[1].week_start, action_cost=200),
        InventoryDecision(decision_id="TRANSFER_5000", transfer_in_qty=5000, transfer_week=baseline.weeks[1].week_start, action_cost=500),
    ]
    output(optimize_inventory_across_scenarios(baseline, scenarios=scenarios, decisions=decisions))


def case_11_dashboard() -> None:
    histories, metadata = demo_histories()
    forecasts = []
    for item_id in sorted(histories):
        meta = metadata[item_id]
        classification = classify_demand(
            {item_id: histories[item_id]}, unit_costs={item_id: float(meta["unit_cost"])},
            lifecycles={item_id: str(meta["lifecycle"])}, source_version=str(meta["data_version"]),
        )[0]
        forecasts.append(generate_forecast(
            item_id, histories[item_id], classification,
            last_history_week=date.fromisoformat(str(meta["last_history_week"])),
            history_source=str(meta["data_version"]), stockout_unit_cost=float(meta["unit_cost"]),
        ))
    risks = []
    for case_id, material, plant, unit_cost, context in [
        ("CASE1", "MAT-A", "DEMO_PLANT", 18, {"forecast_down_consecutive": True, "open_po": 16000}),
        ("CASE2", "MAT-B", "TARGET_PLANT", 45, {"supplier_delay": True}),
        ("CASE3", "MAT-C", "DEMO_PLANT", 20, {"po_late": True}),
    ]:
        risks.extend(identify_projection_risks(
            project_inventory_by_week(demo_projection(case_id, material, plant)),
            unit_cost=unit_cost, context=context,
        ))
    tasks = RiskTaskService()
    for risk in risks:
        tasks.create_from_risk(risk, assignee="demo_owner")
    tasks.generate_notifications(date(2026, 8, 25))
    records = demo_supplier_records()
    suppliers = [calculate_supplier_reliability(item, records) for item in sorted({row.supplier_id for row in records})]
    output(build_management_dashboard(
        data_quality=assess_project_data(), forecasts=forecasts, risks=risks,
        tasks=tasks.list_tasks(), suppliers=suppliers, source_versions={"dashboard": "DEMO-DASH-V1"},
    ))


CASES = {
    "1": case_1_atp,
    "2": case_2_transfer,
    "3": case_3_po_cost,
    "4": case_4_lot_price,
    "5": case_5_ecn,
    "6": case_6_snapshots,
    "7": case_7_forecast_workflow,
    "8": case_8_excel_mapping,
    "9": case_9_tasks_and_supplier,
    "10": case_10_scenario_cost,
    "11": case_11_dashboard,
}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run SupplyPilot phase-2 deterministic demo cases")
    parser.add_argument("--case", choices=[*CASES, "all"], default="all")
    args = parser.parse_args()
    selected = CASES.items() if args.case == "all" else [(args.case, CASES[args.case])]
    for case_id, runner in selected:
        print(f"\n===== Phase 2 Case {case_id} =====")
        runner()
