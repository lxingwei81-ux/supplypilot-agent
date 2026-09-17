from __future__ import annotations

from datetime import date
from fractions import Fraction
from math import ceil, lcm
from typing import Sequence

from ..config import RulesConfig, load_rules
from ..models import (
    OptimizationStatus,
    POAdjustment,
    POOption,
    POOptimizationResult,
    PriceBreak,
    ProcurementOptimizationResult,
)


def optimize_po_reduction_plan(
    material_id: str,
    plant: str,
    *,
    excess_qty: float,
    po_options: Sequence[POOption],
    as_of_date: date,
    horizon_weeks: int = 13,
    holding_cost_per_unit_week: float | None = None,
    obsolescence_cost_per_unit: float | None = None,
    rules: RulesConfig | None = None,
) -> POOptimizationResult:
    cfg = rules or load_rules()
    if any(option.material_id != material_id or option.plant != plant for option in po_options):
        raise ValueError("PO options must match material and plant")
    holding = holding_cost_per_unit_week if holding_cost_per_unit_week is not None else cfg.po_optimization.default_holding_cost_per_unit_week
    obsolescence = obsolescence_cost_per_unit if obsolescence_cost_per_unit is not None else cfg.po_optimization.default_obsolescence_cost_per_unit
    # DP state: total cancelled -> (net benefit, [(option, qty)]). Cancellation never exceeds safe excess.
    states: dict[float, tuple[float, list[tuple[POOption, float]]]] = {0.0: (0.0, [])}
    blocked: list[str] = []
    for option in po_options:
        if option.cancellation_deadline and as_of_date > option.cancellation_deadline:
            blocked.append(f"{option.document_id}: cancellation deadline passed")
            continue
        max_cancel = min(option.cancelable_qty, option.open_qty, excess_qty)
        steps = int(max_cancel // option.mpq)
        candidates = [index * option.mpq for index in range(steps + 1)]
        if max_cancel > 0 and (not candidates or candidates[-1] < max_cancel - 1e-9):
            candidates.append(max_cancel)
        next_states: dict[float, tuple[float, list[tuple[POOption, float]]]] = {}
        for current_qty, (current_benefit, plan) in states.items():
            for quantity in candidates:
                total_qty = round(current_qty + quantity, 6)
                if total_qty > excess_qty + 1e-9:
                    continue
                penalty = quantity * option.unit_price * option.cancellation_penalty_rate
                avoided = quantity * (holding * min(horizon_weeks, option.weeks_until_receipt + horizon_weeks) + obsolescence)
                benefit = current_benefit + avoided - penalty
                candidate_plan = plan + ([(option, quantity)] if quantity > 0 else [])
                if total_qty not in next_states or benefit > next_states[total_qty][0] + 1e-9:
                    next_states[total_qty] = (benefit, candidate_plan)
        if len(next_states) > cfg.po_optimization.maximum_dynamic_programming_states:
            ranked = sorted(next_states.items(), key=lambda item: (item[1][0], item[0]), reverse=True)
            next_states = dict(ranked[:cfg.po_optimization.maximum_dynamic_programming_states])
        states = next_states or states
    _, (best_benefit, best_plan) = max(states.items(), key=lambda item: (item[1][0], item[0]))
    plan_by_document = {option.document_id: (option, quantity) for option, quantity in best_plan}
    cancelled = sum(quantity for _, quantity in best_plan)
    remaining_excess = max(0.0, excess_qty - cancelled)
    adjustments: list[POAdjustment] = []
    total_penalty = 0.0
    total_avoided = 0.0
    for option in po_options:
        cancel_qty = plan_by_document.get(option.document_id, (option, 0.0))[1]
        remaining_document = max(0.0, option.open_qty - cancel_qty - option.locked_qty)
        delay_qty = min(option.reschedulable_qty, remaining_document, remaining_excess)
        remaining_excess -= delay_qty
        penalty = cancel_qty * option.unit_price * option.cancellation_penalty_rate
        avoided_cancel = cancel_qty * (holding * min(horizon_weeks, option.weeks_until_receipt + horizon_weeks) + obsolescence)
        avoided_delay = delay_qty * holding * max(1, horizon_weeks // 2)
        avoided = avoided_cancel + avoided_delay
        if cancel_qty > 0 or delay_qty > 0:
            adjustments.append(POAdjustment(
                document_id=option.document_id, cancel_qty=cancel_qty, delay_qty=delay_qty,
                penalty_cost=penalty, avoided_holding_cost=cancel_qty * holding * horizon_weeks + avoided_delay,
                avoided_obsolescence_cost=cancel_qty * obsolescence,
                net_benefit=avoided - penalty,
            ))
        total_penalty += penalty
        total_avoided += avoided
    excess_after = max(0.0, excess_qty - sum(row.cancel_qty + row.delay_qty for row in adjustments))
    status = OptimizationStatus.OPTIMAL if excess_after <= 1e-9 else (OptimizationStatus.FEASIBLE if adjustments else OptimizationStatus.INFEASIBLE)
    return POOptimizationResult(
        material_id=material_id, plant=plant, status=status, adjustments=adjustments,
        excess_before=excess_qty, excess_after=excess_after, shortage_after=0,
        total_penalty_cost=total_penalty, total_avoided_cost=total_avoided,
        net_benefit=total_avoided - total_penalty,
        constraints=["total cancel+delay <= decision excess", "locked quantity cannot be cancelled", "cancel quantities follow MPQ", "expired cancel window is excluded"],
        infeasible_reasons=blocked + ([f"Residual excess {excess_after:.2f} cannot be adjusted"] if excess_after > 1e-9 else []),
        source_versions={"po": ",".join(sorted({item.data_version for item in po_options}))},
        rules_version=cfg.metadata.version,
    )


def _joint_multiple(*values: float) -> float:
    fractions = [Fraction(str(value)).limit_denominator(10000) for value in values]
    denominator = 1
    for value in fractions:
        denominator = lcm(denominator, value.denominator)
    integers = [int(value * denominator) for value in fractions]
    multiple = 1
    for value in integers:
        multiple = lcm(multiple, value)
    return multiple / denominator


def optimize_replenishment_order(
    material_id: str,
    *,
    required_qty: float,
    price_breaks: Sequence[PriceBreak],
    moq: float,
    mpq: float,
    package_multiple: float,
    order_fixed_cost: float | None = None,
    holding_cost_per_unit: float | None = None,
    shortage_cost_per_unit: float | None = None,
    rules: RulesConfig | None = None,
) -> ProcurementOptimizationResult:
    cfg = rules or load_rules()
    if not price_breaks:
        raise ValueError("at least one price break is required")
    if min(moq, mpq, package_multiple) <= 0 or required_qty < 0:
        raise ValueError("lot sizes must be positive and required quantity non-negative")
    ordered_breaks = sorted(price_breaks, key=lambda item: item.minimum_qty)
    if ordered_breaks[0].minimum_qty > 0:
        raise ValueError("price breaks must include a base price at minimum_qty=0")
    fixed = order_fixed_cost if order_fixed_cost is not None else cfg.replenishment_optimization.default_order_fixed_cost
    holding = holding_cost_per_unit if holding_cost_per_unit is not None else cfg.replenishment_optimization.default_holding_cost_per_unit
    shortage = shortage_cost_per_unit if shortage_cost_per_unit is not None else cfg.replenishment_optimization.default_shortage_cost_per_unit
    step = _joint_multiple(mpq, package_multiple)
    minimum_order = ceil(moq / step) * step
    highest_break = max(item.minimum_qty for item in ordered_breaks)
    maximum = max(minimum_order, required_qty * cfg.replenishment_optimization.maximum_target_multiplier, highest_break + step)
    candidate_count = min(cfg.replenishment_optimization.maximum_candidates, int(maximum // step) + 2)
    quantities = [0.0] + [minimum_order + index * step for index in range(candidate_count) if minimum_order + index * step <= maximum + 1e-9]
    quantities.extend(ceil(item.minimum_qty / step) * step for item in ordered_breaks if item.minimum_qty > 0)
    quantities = sorted(set(round(quantity, 8) for quantity in quantities if quantity == 0 or quantity >= moq - 1e-9))
    evaluations = []
    for quantity in quantities:
        applicable = [item for item in ordered_breaks if item.minimum_qty <= quantity + 1e-9]
        unit_price = applicable[-1].unit_price if applicable else ordered_breaks[0].unit_price
        ending_surplus = max(0.0, quantity - required_qty)
        ending_shortage = max(0.0, required_qty - quantity)
        purchase_cost = quantity * unit_price
        holding_cost = ending_surplus * holding
        shortage_cost = ending_shortage * shortage
        fixed_cost = fixed if quantity > 0 else 0.0
        total = purchase_cost + holding_cost + shortage_cost + fixed_cost
        evaluations.append((total, ending_shortage, quantity, unit_price, purchase_cost, holding_cost, shortage_cost, fixed_cost, ending_surplus))
    best = min(evaluations, key=lambda row: (row[0], row[1], row[2]))
    status = OptimizationStatus.OPTIMAL if best[1] <= 1e-9 else OptimizationStatus.DETERMINISTIC_FALLBACK
    return ProcurementOptimizationResult(
        material_id=material_id, status=status, required_qty=required_qty,
        recommended_order_qty=best[2], selected_unit_price=best[3], purchase_cost=best[4],
        holding_cost=best[5], shortage_cost=best[6], fixed_order_cost=best[7], total_cost=best[0],
        ending_surplus=best[8], ending_shortage=best[1], moq=moq, mpq=mpq,
        package_multiple=package_multiple, evaluated_candidates=len(evaluations),
        constraints=["Q=0 or Q>=MOQ", f"Q follows joint MPQ/package multiple {step}", "unit price selected by applicable price tier"],
        explanation="Deterministically enumerated feasible lot-size and price-break candidates and selected minimum total cost",
        source_versions={"price_breaks": ",".join(sorted({item.data_version for item in price_breaks}))},
        rules_version=cfg.metadata.version,
    )
