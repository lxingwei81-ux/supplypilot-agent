from datetime import date
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .agent import ask
from .models import (
    Action, ATPDemand, DemandScenario, ECNValidationStatus, ECNWorkflow,
    InventoryDecision, InventoryProjectionInput, POOption, PriceBreak,
    SupplierDeliveryRecord, TransferLane, TransferSource, TransferTarget,
)
from .router import route_scenario
from .services.action_validation import validate_action_impact
from .services.allocation import allocate_shared_material_atp
from .services.data_quality import assess_project_data
from .services.demand_classification import classify_demand
from .services.forecasting import generate_forecast
from .services.inventory_projection import project_inventory_by_week
from .services.ecn_workflow import transition_ecn
from .services.procurement_optimization import optimize_po_reduction_plan, optimize_replenishment_order
from .services.scenario_optimization import optimize_inventory_across_scenarios
from .services.supplier_reliability import calculate_supplier_reliability
from .services.transfer_optimization import optimize_cross_plant_transfer

app=FastAPI(title="SupplyPilot API", version="3.1.0")
class QueryRequest(BaseModel):question:str
@app.get("/health")
def health()->dict[str,str]:return {"status":"ok","version":"3.1.0"}
@app.post("/query")
async def query(req:QueryRequest)->dict[str,str]:return {"answer":await ask(req.question)}


class RouteRequest(BaseModel):
    query: str
    facts: dict[str, Any] = Field(default_factory=dict)
    available_data: set[str] = Field(default_factory=set)


class ForecastRequest(BaseModel):
    item_id: str
    history: list[float]
    unit_cost: float = Field(default=0, ge=0)
    lifecycle: str = "MATURE"
    last_history_week: date
    source_version: str = "API"


class ActionValidationRequest(BaseModel):
    action: Action
    baseline: InventoryProjectionInput
    related: list[InventoryProjectionInput] = Field(default_factory=list)
    unit_cost: float = Field(default=0, ge=0)


class ATPRequest(BaseModel):
    material_id: str
    available_supply: float = Field(ge=0)
    protected_supply: float = Field(ge=0)
    demands: list[ATPDemand]
    source_versions: dict[str, str] = Field(default_factory=dict)


class TransferOptimizationRequest(BaseModel):
    material_id: str
    as_of_date: date
    sources: list[TransferSource]
    targets: list[TransferTarget]
    lanes: list[TransferLane]


class POOptimizationRequest(BaseModel):
    material_id: str
    plant: str
    excess_qty: float = Field(ge=0)
    as_of_date: date
    horizon_weeks: int = Field(default=13, gt=0)
    options: list[POOption]


class ReplenishmentOptimizationRequest(BaseModel):
    material_id: str
    required_qty: float = Field(ge=0)
    price_breaks: list[PriceBreak]
    moq: float = Field(gt=0)
    mpq: float = Field(gt=0)
    package_multiple: float = Field(gt=0)


class ECNTransitionRequest(BaseModel):
    workflow: ECNWorkflow
    to_status: ECNValidationStatus
    actor: str
    role: str
    evidence_updates: dict[str, str] = Field(default_factory=dict)
    comment: str = ""
    effective_batch: str | None = None
    traceability_rule: str | None = None


class SupplierReliabilityRequest(BaseModel):
    supplier_id: str
    records: list[SupplierDeliveryRecord]


class ScenarioOptimizationRequest(BaseModel):
    baseline: InventoryProjectionInput
    scenarios: list[DemandScenario]
    decisions: list[InventoryDecision]


@app.get("/v3/data-quality")
def data_quality() -> dict[str, Any]:
    return assess_project_data().model_dump(mode="json")


@app.post("/v3/route")
def route(req: RouteRequest) -> dict[str, Any]:
    return route_scenario(req.query, facts=req.facts, available_data=req.available_data).model_dump(mode="json")


@app.post("/v3/forecast")
def forecast(req: ForecastRequest) -> dict[str, Any]:
    classification = classify_demand(
        {req.item_id: req.history}, unit_costs={req.item_id: req.unit_cost},
        lifecycles={req.item_id: req.lifecycle}, source_version=req.source_version,
    )[0]
    return generate_forecast(
        req.item_id, req.history, classification, last_history_week=req.last_history_week,
        history_source=req.source_version, stockout_unit_cost=req.unit_cost,
    ).model_dump(mode="json")


@app.post("/v3/inventory/project")
def inventory_project(req: InventoryProjectionInput) -> dict[str, Any]:
    return project_inventory_by_week(req).model_dump(mode="json")


@app.post("/v3/action/validate")
def action_validate(req: ActionValidationRequest) -> dict[str, Any]:
    return validate_action_impact(
        req.action, req.baseline, related_inputs=req.related, unit_cost=req.unit_cost,
    ).model_dump(mode="json")


@app.post("/v3/allocation/atp")
def atp_allocate(req: ATPRequest) -> dict[str, Any]:
    return allocate_shared_material_atp(
        req.material_id, available_supply=req.available_supply,
        protected_supply=req.protected_supply, demands=req.demands,
        source_versions=req.source_versions,
    ).model_dump(mode="json")


@app.post("/v3/transfer/optimize")
def transfer_optimize(req: TransferOptimizationRequest) -> dict[str, Any]:
    return optimize_cross_plant_transfer(
        req.material_id, as_of_date=req.as_of_date, sources=req.sources,
        targets=req.targets, lanes=req.lanes,
    ).model_dump(mode="json")


@app.post("/v3/procurement/po-optimize")
def po_optimize(req: POOptimizationRequest) -> dict[str, Any]:
    return optimize_po_reduction_plan(
        req.material_id, req.plant, excess_qty=req.excess_qty,
        po_options=req.options, as_of_date=req.as_of_date,
        horizon_weeks=req.horizon_weeks,
    ).model_dump(mode="json")


@app.post("/v3/procurement/replenishment-optimize")
def replenishment_optimize(req: ReplenishmentOptimizationRequest) -> dict[str, Any]:
    return optimize_replenishment_order(
        req.material_id, required_qty=req.required_qty,
        price_breaks=req.price_breaks, moq=req.moq, mpq=req.mpq,
        package_multiple=req.package_multiple,
    ).model_dump(mode="json")


@app.post("/v3/ecn/transition")
def ecn_transition(req: ECNTransitionRequest) -> dict[str, Any]:
    return transition_ecn(
        req.workflow, req.to_status, actor=req.actor, role=req.role,
        evidence_updates=req.evidence_updates, comment=req.comment,
        effective_batch=req.effective_batch,
        traceability_rule=req.traceability_rule,
    ).model_dump(mode="json")


@app.post("/v3/supplier/reliability")
def supplier_reliability(req: SupplierReliabilityRequest) -> dict[str, Any]:
    return calculate_supplier_reliability(req.supplier_id, req.records).model_dump(mode="json")


@app.post("/v3/inventory/scenario-optimize")
def inventory_scenario_optimize(req: ScenarioOptimizationRequest) -> dict[str, Any]:
    return optimize_inventory_across_scenarios(
        req.baseline, scenarios=req.scenarios, decisions=req.decisions,
    ).model_dump(mode="json")
