from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from math import inf
from typing import Sequence

from ..config import RulesConfig, load_rules
from ..models import (
    OptimizationStatus,
    TransferLane,
    TransferOptimizationResult,
    TransferRecommendation,
    TransferSource,
    TransferTarget,
)


@dataclass
class _Edge:
    to: int
    reverse: int
    capacity: float
    cost: float
    original_capacity: float
    lane_key: tuple[str, str] | None = None


def _add_edge(graph: list[list[_Edge]], start: int, end: int, capacity: float, cost: float, lane_key=None) -> None:
    forward = _Edge(end, len(graph[end]), capacity, cost, capacity, lane_key)
    backward = _Edge(start, len(graph[start]), 0.0, -cost, 0.0, None)
    graph[start].append(forward)
    graph[end].append(backward)


def optimize_cross_plant_transfer(
    material_id: str,
    *,
    as_of_date: date,
    sources: Sequence[TransferSource],
    targets: Sequence[TransferTarget],
    lanes: Sequence[TransferLane],
    rules: RulesConfig | None = None,
) -> TransferOptimizationResult:
    cfg = rules or load_rules()
    if any(item.material_id != material_id for item in [*sources, *targets]):
        raise ValueError("all transfer sources and targets must use the same material")
    source_available = {
        source.plant: max(0.0, source.on_hand - source.protected_qty - source.future_demand - source.minimum_coverage_qty)
        for source in sources
    }
    target_shortage = {target.plant: target.shortage_qty for target in targets}
    source_index = {source.plant: index + 1 for index, source in enumerate(sources)}
    target_offset = 1 + len(sources)
    target_index = {target.plant: target_offset + index for index, target in enumerate(targets)}
    sink = target_offset + len(targets)
    graph: list[list[_Edge]] = [[] for _ in range(sink + 1)]
    for source in sources:
        _add_edge(graph, 0, source_index[source.plant], source_available[source.plant], 0.0)
    for target in targets:
        _add_edge(graph, target_index[target.plant], sink, target.shortage_qty, 0.0)
    valid_lanes: dict[tuple[str, str], TransferLane] = {}
    skipped: list[str] = []
    for lane in lanes:
        key = (lane.source_plant, lane.target_plant)
        source = next((item for item in sources if item.plant == lane.source_plant), None)
        target = next((item for item in targets if item.plant == lane.target_plant), None)
        if source is None or target is None:
            skipped.append(f"{key}: source or target missing")
            continue
        if not lane.compatible:
            skipped.append(f"{key}: incompatible material/version/quality")
            continue
        if lane.lead_time_days > cfg.transfer_optimization.maximum_lead_time_days:
            skipped.append(f"{key}: lead time exceeds configured maximum")
            continue
        if as_of_date + timedelta(days=lane.lead_time_days) > target.need_date:
            skipped.append(f"{key}: arrival later than need date")
            continue
        capacity = min(source_available[source.plant], target.shortage_qty)
        if capacity <= 0:
            continue
        # Fixed cost is spread across potential lane capacity for deterministic min-cost-flow ranking.
        effective_cost = lane.unit_cost + lane.fixed_cost / capacity - target.priority * cfg.transfer_optimization.shortage_penalty_per_unit
        _add_edge(graph, source_index[source.plant], target_index[target.plant], capacity, effective_cost, key)
        valid_lanes[key] = lane
    required_flow = min(sum(source_available.values()), sum(target_shortage.values()))
    flow = 0.0
    while flow + 1e-9 < required_flow:
        distance = [inf] * len(graph)
        previous: list[tuple[int, int] | None] = [None] * len(graph)
        distance[0] = 0.0
        # Bellman-Ford supports residual negative edges and keeps the implementation dependency-free.
        for _ in range(len(graph) - 1):
            changed = False
            for node, edges in enumerate(graph):
                if distance[node] == inf:
                    continue
                for edge_index, edge in enumerate(edges):
                    if edge.capacity > 1e-9 and distance[edge.to] > distance[node] + edge.cost + 1e-12:
                        distance[edge.to] = distance[node] + edge.cost
                        previous[edge.to] = (node, edge_index)
                        changed = True
            if not changed:
                break
        if previous[sink] is None:
            break
        augment = required_flow - flow
        node = sink
        while node != 0:
            parent, edge_index = previous[node]  # type: ignore[misc]
            augment = min(augment, graph[parent][edge_index].capacity)
            node = parent
        node = sink
        while node != 0:
            parent, edge_index = previous[node]  # type: ignore[misc]
            edge = graph[parent][edge_index]
            edge.capacity -= augment
            graph[node][edge.reverse].capacity += augment
            node = parent
        flow += augment
    flows: dict[tuple[str, str], float] = defaultdict(float)
    for source in sources:
        node = source_index[source.plant]
        for edge in graph[node]:
            if edge.lane_key is not None:
                used = edge.original_capacity - edge.capacity
                if used > 1e-9:
                    flows[edge.lane_key] += used
    source_remaining = source_available.copy()
    target_remaining = target_shortage.copy()
    recommendations: list[TransferRecommendation] = []
    total_cost = 0.0
    for key, quantity in sorted(flows.items()):
        lane = valid_lanes[key]
        source_remaining[key[0]] -= quantity
        target_remaining[key[1]] -= quantity
        variable_cost = quantity * lane.unit_cost
        lane_total = variable_cost + lane.fixed_cost
        total_cost += lane_total
        recommendations.append(TransferRecommendation(
            source_plant=key[0], target_plant=key[1], material_id=material_id,
            quantity=quantity, arrival_date=as_of_date + timedelta(days=lane.lead_time_days),
            unit_cost=lane.unit_cost, variable_cost=variable_cost, fixed_cost=lane.fixed_cost,
            total_cost=lane_total, source_remaining_available=max(0.0, source_remaining[key[0]]),
            target_remaining_shortage=max(0.0, target_remaining[key[1]]),
        ))
    shortage_before = sum(target_shortage.values())
    shortage_after = sum(max(0.0, value) for value in target_remaining.values())
    if shortage_before == 0:
        status = OptimizationStatus.OPTIMAL
    elif shortage_after <= 1e-9:
        status = OptimizationStatus.OPTIMAL
    elif recommendations:
        status = OptimizationStatus.FEASIBLE
    else:
        status = OptimizationStatus.INFEASIBLE
    reasons = skipped[:]
    if shortage_after > 1e-9:
        reasons.append(f"Uncovered target shortage remains {shortage_after:.2f}")
    return TransferOptimizationResult(
        material_id=material_id, status=status, recommendations=recommendations,
        total_shortage_before=shortage_before, total_shortage_after=shortage_after,
        total_transfer_qty=sum(flows.values()), total_cost=total_cost,
        infeasible_reasons=reasons, solver="DETERMINISTIC_MIN_COST_FLOW",
        trace=[
            f"Source available after protection={source_available}",
            f"Target shortage={target_shortage}",
            f"Valid lanes={sorted(valid_lanes)}",
        ],
        source_versions={
            "sources": ",".join(sorted({item.data_version for item in sources})),
            "targets": ",".join(sorted({item.data_version for item in targets})),
        },
        rules_version=cfg.metadata.version,
    )
