from __future__ import annotations

from datetime import date

import pytest

from src.services.bom import BOMCycleError, InvalidBOMError, explode_bom


WEEK = date(2026, 1, 5)


def edge(parent, child, usage=1, **extra):
    return {"product_id": "P", "parent_id": parent, "child_id": child, "unit_usage": usage, "bom_version": "A", **extra}


def test_single_level_bom() -> None:
    result = explode_bom("P", {WEEK: 10}, [edge("P", "M", 2)], forecast_version_id="F")
    assert result[0].gross_requirement == 20
    assert result[0].bom_path == ["P", "M"]


def test_multi_level_cumulative_usage() -> None:
    result = explode_bom("P", {WEEK: 10}, [edge("P", "S", 2), edge("S", "M", 3)], forecast_version_id="F")
    assert len(result) == 1
    assert result[0].gross_requirement == 60
    assert result[0].bom_path == ["P", "S", "M"]


def test_shared_material_paths_are_aggregatable() -> None:
    rows = [edge("P", "S1", 1), edge("P", "S2", 1), edge("S1", "M", 2), edge("S2", "M", 3)]
    result = explode_bom("P", {WEEK: 10}, rows, forecast_version_id="F")
    assert sum(row.gross_requirement for row in result if row.material_id == "M") == 50
    assert len([row for row in result if row.material_id == "M"]) == 2


def test_loss_rate_is_applied_at_each_level() -> None:
    rows = [edge("P", "S", 2, loss_rate=0.1), edge("S", "M", 3, loss_rate=0.2)]
    result = explode_bom("P", {WEEK: 10}, rows, forecast_version_id="F")[0]
    assert result.base_quantity == 60
    assert result.gross_requirement == pytest.approx(79.2)
    assert result.loss_quantity == pytest.approx(19.2)


def test_effective_date_selects_version() -> None:
    rows = [
        edge("P", "M", 1, bom_version="A", effective_from="2025-01-01", effective_to="2025-12-31"),
        edge("P", "M", 2, bom_version="B", effective_from="2026-01-01", effective_to="2026-12-31"),
    ]
    result = explode_bom("P", {WEEK: 10}, rows, forecast_version_id="F")[0]
    assert result.bom_version == "B"
    assert result.gross_requirement == 20


def test_invalid_bom_rejected() -> None:
    with pytest.raises(InvalidBOMError):
        explode_bom("P", {WEEK: 10}, [edge("P", "M", 0)], forecast_version_id="F")


def test_missing_active_bom_rejected() -> None:
    rows = [edge("P", "M", 1, effective_from="2025-01-01", effective_to="2025-12-31")]
    with pytest.raises(InvalidBOMError):
        explode_bom("P", {WEEK: 10}, rows, forecast_version_id="F")


def test_cycle_rejected() -> None:
    rows = [edge("P", "S"), edge("S", "P")]
    with pytest.raises(BOMCycleError):
        explode_bom("P", {WEEK: 10}, rows, forecast_version_id="F")


def test_unit_conversion_is_applied() -> None:
    rows = [edge("P", "M", 2, unit="KG", base_unit="G", conversion_factor=1000)]
    result = explode_bom("P", {WEEK: 3}, rows, forecast_version_id="F")[0]
    assert result.gross_requirement == 6000
    assert result.unit == "G"

