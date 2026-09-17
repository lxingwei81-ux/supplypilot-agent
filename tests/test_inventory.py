from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.demo import demo_projection
from src.models import ABCClass, InventoryProjectionInput, ProductLifecycle, WeeklyInventoryInput, XYZClass
from src.services.inventory_policy import calculate_inventory_policy
from src.services.inventory_projection import available_inventory, project_inventory_by_week


START = date(2026, 1, 5)


def projection(on_hand=100, demand=None, receipts=None, safety=0, **states):
    demand = demand or [30, 30, 30, 30]
    receipts = receipts or [0] * len(demand)
    return InventoryProjectionInput(
        material_id="M", plant="P", on_hand=on_hand,
        weeks=[WeeklyInventoryInput(week_start=START + timedelta(days=7 * i), gross_demand=d, po_receipt=receipts[i], safety_stock=safety) for i, d in enumerate(demand)],
        data_version="T", **states,
    )


def test_no_receipt_shortage() -> None:
    result = project_inventory_by_week(projection(on_hand=50, demand=[30, 30]))
    assert result.first_shortage_week == START + timedelta(days=7)
    assert result.maximum_shortage_qty == 10


def test_on_time_receipt_prevents_shortage() -> None:
    result = project_inventory_by_week(projection(on_hand=50, demand=[30, 30], receipts=[0, 20]))
    assert result.first_shortage_week is None


def test_late_receipt_causes_temporary_shortage() -> None:
    result = project_inventory_by_week(projection(on_hand=50, demand=[30, 30, 30], receipts=[0, 0, 100]))
    assert result.first_shortage_week == START + timedelta(days=7)
    assert result.points[-1].ending_inventory == 60


def test_inventory_status_reduces_available() -> None:
    data = projection(on_hand=100, demand=[0], frozen=10, quality_hold=20, allocated=30, reusable_return=5)
    assert available_inventory(data) == 45
    assert project_inventory_by_week(data).points[0].beginning_inventory == 45


def test_safety_stock_warning_before_physical_shortage() -> None:
    result = project_inventory_by_week(projection(on_hand=100, demand=[30, 30, 30], safety=50))
    assert result.first_below_safety_stock_week == START + timedelta(days=7)
    assert result.first_shortage_week is None


def test_reserved_demand_is_consumed() -> None:
    data = projection(on_hand=100, demand=[20])
    data.weeks[0].reserved_demand = 30
    assert project_inventory_by_week(data).points[0].ending_inventory == 50


def test_static_surplus_can_hide_middle_week_shortage() -> None:
    data = demo_projection("CASE3", "MAT-C", "DEMO_PLANT")
    static_surplus = data.on_hand + sum(row.po_receipt for row in data.weeks) - sum(row.gross_demand for row in data.weeks)
    result = project_inventory_by_week(data)
    assert static_surplus > 0
    assert result.first_shortage_week is not None


def test_safety_stock_formula() -> None:
    result = calculate_inventory_policy(
        "M", mean_weekly_demand=100, demand_variance=400, mean_lead_time_weeks=4,
        lead_time_variance=1, on_hand=100, service_level=0.95,
    )
    expected = result.z_value * ((4 * 400 + 10000) ** 0.5)
    assert result.safety_stock == pytest.approx(expected)


def test_missing_policy_defaults_are_warned() -> None:
    result = calculate_inventory_policy(
        "M", mean_weekly_demand=10, demand_variance=4, mean_lead_time_weeks=2,
        lead_time_variance=None, on_hand=0,
    )
    assert len(result.warnings) == 2


def test_moq_mpq_and_package_constraints() -> None:
    result = calculate_inventory_policy(
        "M", mean_weekly_demand=10, demand_variance=0, mean_lead_time_weeks=1,
        lead_time_variance=0, on_hand=0, service_level=0.95,
        moq=100, mpq=30, package_multiple=20, target_inventory=101,
    )
    assert result.recommended_order_quantity == 120


def test_eol_blocks_new_replenishment() -> None:
    result = calculate_inventory_policy(
        "M", mean_weekly_demand=10, demand_variance=1, mean_lead_time_weeks=1,
        lead_time_variance=0, on_hand=0, lifecycle=ProductLifecycle.EOL,
    )
    assert result.recommended_order_quantity == 0

