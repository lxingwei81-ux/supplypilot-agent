from __future__ import annotations

from datetime import date

import pytest

from src.models import OptimizationStatus, POOption, PriceBreak
from src.services.procurement_optimization import optimize_po_reduction_plan, optimize_replenishment_order


TODAY = date(2026, 7, 21)


def po(
    document_id: str,
    quantity: float,
    *,
    cancelable: float | None = None,
    reschedulable: float = 0,
    locked: float = 0,
    penalty: float = 0,
    deadline: date | None = None,
    mpq: float = 10,
) -> POOption:
    return POOption(
        document_id=document_id, material_id="M", plant="P", open_qty=quantity,
        cancelable_qty=quantity if cancelable is None else cancelable,
        reschedulable_qty=reschedulable, locked_qty=locked, unit_price=10,
        cancellation_penalty_rate=penalty, weeks_until_receipt=2,
        cancellation_deadline=deadline, mpq=mpq,
    )


def test_po_optimizer_never_adjusts_more_than_decision_excess() -> None:
    result = optimize_po_reduction_plan(
        "M", "P", excess_qty=75, po_options=[po("PO1", 100, mpq=25)], as_of_date=TODAY,
    )
    assert sum(row.cancel_qty + row.delay_qty for row in result.adjustments) <= 75
    assert result.shortage_after == 0
    assert result.excess_after == 0


def test_po_optimizer_excludes_expired_cancellation_window() -> None:
    result = optimize_po_reduction_plan(
        "M", "P", excess_qty=50,
        po_options=[po("OLD", 50, deadline=date(2026, 7, 20))], as_of_date=TODAY,
    )
    assert result.status == OptimizationStatus.INFEASIBLE
    assert result.adjustments == []
    assert any("deadline passed" in reason for reason in result.infeasible_reasons)


def test_po_optimizer_obeys_cancelable_and_locked_quantity() -> None:
    result = optimize_po_reduction_plan(
        "M", "P", excess_qty=100,
        po_options=[po("PO1", 100, cancelable=30, locked=70, mpq=10)], as_of_date=TODAY,
    )
    assert sum(row.cancel_qty for row in result.adjustments) <= 30
    assert result.excess_after == 70


def test_po_optimizer_prefers_lower_cancellation_penalty() -> None:
    result = optimize_po_reduction_plan(
        "M", "P", excess_qty=50,
        po_options=[po("EXPENSIVE", 50, penalty=0.9), po("CHEAP", 50, penalty=0.0)],
        as_of_date=TODAY, holding_cost_per_unit_week=1, obsolescence_cost_per_unit=5,
    )
    selected = {row.document_id: row.cancel_qty for row in result.adjustments}
    assert selected.get("CHEAP") == 50
    assert selected.get("EXPENSIVE", 0) == 0


def test_joint_lot_multiple_and_price_break_are_honored() -> None:
    result = optimize_replenishment_order(
        "M", required_qty=101,
        price_breaks=[PriceBreak(minimum_qty=0, unit_price=10), PriceBreak(minimum_qty=120, unit_price=8)],
        moq=100, mpq=30, package_multiple=20,
        holding_cost_per_unit=1, shortage_cost_per_unit=100,
    )
    assert result.recommended_order_qty % 60 == 0
    assert result.recommended_order_qty >= 100
    assert result.selected_unit_price == 8
    assert result.ending_shortage == 0


def test_high_shortage_cost_selects_feasible_replenishment() -> None:
    result = optimize_replenishment_order(
        "M", required_qty=95, price_breaks=[PriceBreak(minimum_qty=0, unit_price=10)],
        moq=100, mpq=10, package_multiple=10, shortage_cost_per_unit=1000,
    )
    assert result.status == OptimizationStatus.OPTIMAL
    assert result.recommended_order_qty == 100


def test_replenishment_rejects_missing_base_price_or_invalid_lot() -> None:
    with pytest.raises(ValueError, match="base price"):
        optimize_replenishment_order(
            "M", required_qty=10, price_breaks=[PriceBreak(minimum_qty=100, unit_price=8)],
            moq=10, mpq=10, package_multiple=10,
        )
    with pytest.raises(ValueError, match="positive"):
        optimize_replenishment_order(
            "M", required_qty=10, price_breaks=[PriceBreak(minimum_qty=0, unit_price=8)],
            moq=10, mpq=0, package_multiple=10,
        )


def test_procurement_optimization_is_deterministic() -> None:
    kwargs = dict(
        material_id="M", required_qty=470,
        price_breaks=[PriceBreak(minimum_qty=0, unit_price=10), PriceBreak(minimum_qty=500, unit_price=8)],
        moq=100, mpq=50, package_multiple=20,
    )
    assert optimize_replenishment_order(**kwargs).model_dump(exclude={"calculated_at"}) == optimize_replenishment_order(**kwargs).model_dump(exclude={"calculated_at"})

