from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Sequence

from ..config import RulesConfig, load_rules
from ..models import (
    DemandScenario,
    InventoryDecision,
    InventoryProjectionInput,
    MultiScenarioOptimizationResult,
    OptimizationStatus,
    ScenarioCostEvaluation,
)
from .inventory_projection import project_inventory_by_week


def _reduce_po(data: InventoryProjectionInput, quantity: float, start_week) -> None:
    remaining = quantity
    for row in sorted(data.weeks, key=lambda item: item.week_start):
        if start_week and row.week_start < start_week:
            continue
        reduction = min(row.po_receipt, remaining)
        row.po_receipt -= reduction
        remaining -= reduction
        if remaining <= 1e-9:
            return


def _apply(data: InventoryProjectionInput, scenario: DemandScenario, decision: InventoryDecision) -> InventoryProjectionInput:
    output = data.model_copy(deep=True)
    for row in output.weeks:
        row.gross_demand *= scenario.demand_multiplier
    if scenario.po_delay_weeks:
        receipt_by_week = {row.week_start: row.po_receipt for row in output.weeks if row.po_receipt > 0}
        for row in output.weeks:
            row.po_receipt = 0
        week_index = {row.week_start: row for row in output.weeks}
        for week, quantity in receipt_by_week.items():
            delayed = week + timedelta(weeks=scenario.po_delay_weeks)
            if delayed in week_index:
                week_index[delayed].po_receipt += quantity
    if decision.cancel_qty > 0:
        _reduce_po(output, decision.cancel_qty, decision.cancel_from_week)
    if decision.order_qty > 0:
        if decision.order_week is None:
            raise ValueError("order decision requires order_week")
        row = next((row for row in output.weeks if row.week_start == decision.order_week), None)
        if row is None:
            raise ValueError("order_week is outside projection horizon")
        row.po_receipt += decision.order_qty
    if decision.transfer_in_qty > 0:
        if decision.transfer_week is None:
            raise ValueError("transfer decision requires transfer_week")
        row = next((row for row in output.weeks if row.week_start == decision.transfer_week), None)
        if row is None:
            raise ValueError("transfer_week is outside projection horizon")
        row.transfer_in += decision.transfer_in_qty
    return output


def optimize_inventory_across_scenarios(
    baseline: InventoryProjectionInput,
    *,
    scenarios: Sequence[DemandScenario],
    decisions: Sequence[InventoryDecision],
    rules: RulesConfig | None = None,
) -> MultiScenarioOptimizationResult:
    cfg = rules or load_rules()
    probability = sum(scenario.probability for scenario in scenarios)
    if abs(probability - 1.0) > 1e-9:
        raise ValueError("scenario probabilities must sum to 1")
    if not decisions or not scenarios:
        raise ValueError("at least one scenario and decision are required")
    cost = cfg.scenario_optimization
    evaluations: list[ScenarioCostEvaluation] = []
    expected: dict[str, float] = defaultdict(float)
    feasible_by_decision = {decision.decision_id: True for decision in decisions}
    reasons: list[str] = []
    for decision in decisions:
        for scenario in scenarios:
            result = project_inventory_by_week(_apply(baseline, scenario, decision))
            holding_cost = sum(max(0.0, point.ending_inventory) for point in result.points) * cost.holding_cost_per_unit_week
            shortage_cost = sum(point.shortage_qty for point in result.points) * cost.shortage_cost_per_unit
            excess_cost = result.ending_excess_qty * cost.excess_cost_per_unit
            total = holding_cost + shortage_cost + excess_cost + decision.action_cost
            feasible = result.maximum_shortage_qty <= cost.maximum_allowed_shortage + 1e-9
            if not feasible:
                feasible_by_decision[decision.decision_id] = False
            evaluations.append(ScenarioCostEvaluation(
                decision_id=decision.decision_id, scenario_id=scenario.scenario_id,
                probability=scenario.probability, holding_cost=holding_cost,
                shortage_cost=shortage_cost, excess_cost=excess_cost,
                action_cost=decision.action_cost, total_cost=total,
                maximum_shortage=result.maximum_shortage_qty,
                ending_excess=result.ending_excess_qty, feasible=feasible,
            ))
            expected[decision.decision_id] += scenario.probability * total
    robust = sorted(decision_id for decision_id, feasible in feasible_by_decision.items() if feasible)
    if robust:
        selected = min(robust, key=lambda decision_id: (expected[decision_id], decision_id))
        status = OptimizationStatus.OPTIMAL
    else:
        selected = None
        status = OptimizationStatus.INFEASIBLE
        reasons.append("No decision avoids shortage in every configured scenario; no unsafe decision is recommended")
    return MultiScenarioOptimizationResult(
        material_id=baseline.material_id, selected_decision_id=selected, status=status,
        expected_cost_by_decision={key: expected[key] for key in sorted(expected)},
        evaluations=evaluations, robust_feasible_decisions=robust,
        infeasible_reasons=reasons,
        calculation_basis="Expected cost = probability × (inventory-period holding + shortage + ending excess + action cost); selection restricted to zero-shortage decisions",
        source_versions={"baseline": baseline.data_version},
        rules_version=cfg.metadata.version,
    )
