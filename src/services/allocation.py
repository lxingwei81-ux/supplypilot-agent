from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Sequence

from ..config import RulesConfig, load_rules
from ..models import ATPAllocation, ATPAllocationResult, ATPDemand


def _allocation_score(demand: ATPDemand, earliest_week: date, rules: RulesConfig) -> tuple[float, list[str]]:
    cfg = rules.allocation
    reasons: list[str] = []
    score = 0.0
    if demand.frozen_order:
        score += cfg.frozen_order_bonus
        reasons.append("FROZEN_ORDER")
    score += demand.customer_priority * cfg.customer_priority_weight
    reasons.append(f"CUSTOMER_PRIORITY_{demand.customer_priority}")
    if demand.shortage_penalty_per_unit > 0:
        score += demand.shortage_penalty_per_unit * cfg.shortage_penalty_weight
        reasons.append("SHORTAGE_PENALTY")
    urgency_weeks = max(0, (demand.need_week - earliest_week).days // 7)
    score += cfg.due_urgency_weight / (1 + urgency_weeks)
    reasons.append("DUE_DATE_URGENCY")
    lifecycle_score = cfg.lifecycle_priority.get(demand.lifecycle.value, 0.0)
    score += lifecycle_score
    reasons.append(f"LIFECYCLE_{demand.lifecycle.value}")
    return score, reasons


def allocate_shared_material_atp(
    material_id: str,
    *,
    available_supply: float,
    protected_supply: float,
    demands: Sequence[ATPDemand],
    source_versions: dict[str, str] | None = None,
    rules: RulesConfig | None = None,
) -> ATPAllocationResult:
    cfg = rules or load_rules()
    if available_supply < 0 or protected_supply < 0:
        raise ValueError("available and protected supply must be non-negative")
    if any(demand.material_id != material_id for demand in demands):
        raise ValueError("all ATP demands must reference the requested material")
    if not demands:
        return ATPAllocationResult(
            material_id=material_id,
            available_supply=available_supply,
            protected_supply=protected_supply,
            allocatable_supply=max(0.0, available_supply - protected_supply),
            total_requested=0,
            total_allocated=0,
            total_unfulfilled=0,
            allocations=[],
            policy="RULE_PRIORITY_WITH_OPTIONAL_FAIR_SHARE",
            trace=["No demand records supplied"],
            source_versions=source_versions or {},
            rules_version=cfg.metadata.version,
        )
    earliest = min(demand.need_week for demand in demands)
    scored = []
    for demand in demands:
        score, reasons = _allocation_score(demand, earliest, cfg)
        scored.append((demand, score, reasons))
    scored.sort(key=lambda item: (-item[1], item[0].need_week, item[0].demand_id))
    allocatable = max(0.0, available_supply - protected_supply)
    allocations_by_id: dict[str, float] = defaultdict(float)
    trace = [
        f"Available={available_supply:.2f}; protected={protected_supply:.2f}; allocatable={allocatable:.2f}",
        "Priority score = frozen bonus + customer priority + shortage penalty + due urgency + lifecycle",
    ]
    fair_share = cfg.allocation.minimum_fair_share if hasattr(cfg, "allocation") else cfg.minimum_fair_share
    # A configured floor is applied proportionally before priority ranking, never beyond available supply.
    if fair_share > 0 and allocatable > 0:
        floor_need = sum(demand.requested_qty * fair_share for demand, _, _ in scored)
        scale = min(1.0, allocatable / floor_need) if floor_need > 0 else 0.0
        for demand, _, _ in scored:
            quantity = min(demand.requested_qty, demand.requested_qty * fair_share * scale)
            allocations_by_id[demand.demand_id] += quantity
            allocatable -= quantity
        trace.append(f"Applied minimum fair share={fair_share:.2%} with scale={scale:.4f}")
    for demand, _, _ in scored:
        remaining_need = max(0.0, demand.requested_qty - allocations_by_id[demand.demand_id])
        quantity = min(remaining_need, allocatable)
        allocations_by_id[demand.demand_id] += quantity
        allocatable -= quantity
    output: list[ATPAllocation] = []
    for rank, (demand, score, reasons) in enumerate(scored, start=1):
        allocated = allocations_by_id[demand.demand_id]
        output.append(ATPAllocation(
            demand_id=demand.demand_id,
            material_id=material_id,
            customer_id=demand.customer_id,
            product_id=demand.product_id,
            plant=demand.plant,
            need_week=demand.need_week,
            requested_qty=demand.requested_qty,
            allocated_qty=allocated,
            unfulfilled_qty=max(0.0, demand.requested_qty - allocated),
            allocation_score=score,
            rank=rank,
            rule_reasons=reasons,
        ))
    total_requested = sum(demand.requested_qty for demand in demands)
    total_allocated = sum(row.allocated_qty for row in output)
    trace.append(f"Allocated={total_allocated:.2f}; unfulfilled={total_requested-total_allocated:.2f}")
    return ATPAllocationResult(
        material_id=material_id,
        available_supply=available_supply,
        protected_supply=protected_supply,
        allocatable_supply=max(0.0, available_supply - protected_supply),
        total_requested=total_requested,
        total_allocated=total_allocated,
        total_unfulfilled=max(0.0, total_requested - total_allocated),
        allocations=output,
        policy="RULE_PRIORITY_WITH_OPTIONAL_FAIR_SHARE",
        trace=trace,
        source_versions=source_versions or {},
        rules_version=cfg.metadata.version,
    )
