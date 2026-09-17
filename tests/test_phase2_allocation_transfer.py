from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.models import ATPDemand, OptimizationStatus, TransferLane, TransferSource, TransferTarget
from src.services.allocation import allocate_shared_material_atp
from src.services.transfer_optimization import optimize_cross_plant_transfer


TODAY = date(2026, 7, 21)


def demand(
    demand_id: str,
    quantity: float,
    *,
    frozen: bool = False,
    priority: int = 3,
    material: str = "M",
) -> ATPDemand:
    return ATPDemand(
        demand_id=demand_id,
        material_id=material,
        customer_id=f"C-{demand_id}",
        product_id="FG",
        plant="P1",
        need_week=TODAY,
        requested_qty=quantity,
        frozen_order=frozen,
        customer_priority=priority,
        source_version="TEST-V1",
    )


def test_atp_protects_inventory_and_never_overallocates() -> None:
    result = allocate_shared_material_atp(
        "M", available_supply=100, protected_supply=30,
        demands=[demand("A", 50), demand("B", 50)],
    )
    assert result.allocatable_supply == 70
    assert result.total_allocated == 70
    assert result.total_unfulfilled == 30


def test_atp_frozen_order_precedes_customer_priority() -> None:
    result = allocate_shared_material_atp(
        "M", available_supply=50, protected_supply=0,
        demands=[demand("FROZEN", 50, frozen=True, priority=1), demand("VIP", 50, priority=5)],
    )
    assert result.allocations[0].demand_id == "FROZEN"
    assert result.allocations[0].allocated_qty == 50
    assert result.allocations[1].allocated_qty == 0


def test_atp_higher_customer_priority_wins_when_other_factors_equal() -> None:
    result = allocate_shared_material_atp(
        "M", available_supply=40, protected_supply=0,
        demands=[demand("LOW", 40, priority=1), demand("HIGH", 40, priority=5)],
    )
    assert result.allocations[0].demand_id == "HIGH"
    assert result.allocations[0].allocated_qty == 40


def test_atp_empty_demand_and_material_validation() -> None:
    result = allocate_shared_material_atp("M", available_supply=10, protected_supply=3, demands=[])
    assert result.total_requested == 0
    with pytest.raises(ValueError, match="same material|requested material"):
        allocate_shared_material_atp(
            "M", available_supply=10, protected_supply=0,
            demands=[demand("X", 1, material="OTHER")],
        )


def source(plant: str, on_hand: float, *, protected: float = 0, future: float = 0, coverage: float = 0) -> TransferSource:
    return TransferSource(
        plant=plant, material_id="M", on_hand=on_hand, protected_qty=protected,
        future_demand=future, minimum_coverage_qty=coverage, data_version="TEST-V1",
    )


def target(plant: str, shortage: float, *, days: int = 7, priority: int = 3) -> TransferTarget:
    return TransferTarget(
        plant=plant, material_id="M", shortage_qty=shortage,
        need_date=TODAY + timedelta(days=days), priority=priority, data_version="TEST-V1",
    )


def lane(source_plant: str, target_plant: str, cost: float, *, days: int = 1, compatible: bool = True) -> TransferLane:
    return TransferLane(
        source_plant=source_plant, target_plant=target_plant,
        lead_time_days=days, unit_cost=cost, fixed_cost=0, compatible=compatible,
    )


def test_transfer_uses_cheapest_valid_source_and_fills_shortage() -> None:
    result = optimize_cross_plant_transfer(
        "M", as_of_date=TODAY,
        sources=[source("S1", 100), source("S2", 100)],
        targets=[target("T", 80)],
        lanes=[lane("S1", "T", 3), lane("S2", "T", 1)],
    )
    assert result.status == OptimizationStatus.OPTIMAL
    assert result.total_shortage_after == 0
    assert [(row.source_plant, row.quantity) for row in result.recommendations] == [("S2", 80)]


def test_transfer_protects_source_future_demand_and_coverage() -> None:
    result = optimize_cross_plant_transfer(
        "M", as_of_date=TODAY,
        sources=[source("S", 100, protected=10, future=30, coverage=20)],
        targets=[target("T", 80)], lanes=[lane("S", "T", 1)],
    )
    assert result.total_transfer_qty == 40
    assert result.total_shortage_after == 40
    assert result.status == OptimizationStatus.FEASIBLE
    assert result.recommendations[0].source_remaining_available == 0


def test_transfer_rejects_late_and_incompatible_lanes() -> None:
    result = optimize_cross_plant_transfer(
        "M", as_of_date=TODAY,
        sources=[source("S", 100)], targets=[target("T", 20, days=3)],
        lanes=[lane("S", "T", 1, days=4), lane("S", "T", 0.5, compatible=False)],
    )
    assert result.status == OptimizationStatus.INFEASIBLE
    assert result.total_transfer_qty == 0
    assert any("later than need date" in reason for reason in result.infeasible_reasons)
    assert any("incompatible" in reason for reason in result.infeasible_reasons)


def test_transfer_result_is_reproducible() -> None:
    kwargs = dict(
        material_id="M", as_of_date=TODAY,
        sources=[source("S1", 60), source("S2", 60)],
        targets=[target("T1", 50), target("T2", 50)],
        lanes=[lane("S1", "T1", 1), lane("S1", "T2", 2), lane("S2", "T1", 2), lane("S2", "T2", 1)],
    )
    first = optimize_cross_plant_transfer(**kwargs)
    second = optimize_cross_plant_transfer(**kwargs)
    assert [row.model_dump(exclude={"calculated_at"}) for row in first.recommendations] == [
        row.model_dump(exclude={"calculated_at"}) for row in second.recommendations
    ]

