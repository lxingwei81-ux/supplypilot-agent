from __future__ import annotations

from src.models import ABCClass, IntermittencyClass, ProductLifecycle, XYZClass
from src.services.demand_classification import classify_demand


def mapping(histories, costs=None, lifecycles=None):
    return {row.item_id: row for row in classify_demand(histories, unit_costs=costs or {}, lifecycles=lifecycles or {}, source_version="T")}


def test_abc_value_boundaries() -> None:
    rows = mapping({"A": [80], "B": [15], "C": [5]}, {"A": 1, "B": 1, "C": 1})
    assert rows["A"].abc_class == ABCClass.A
    assert rows["B"].abc_class == ABCClass.B
    assert rows["C"].abc_class == ABCClass.C


def test_zero_mean_is_safe() -> None:
    row = mapping({"Z": [0] * 20})["Z"]
    assert row.cv is None
    assert row.xyz_class == XYZClass.Z
    assert row.intermittency_class == IntermittencyClass.LUMPY


def test_stable_demand_is_x_smooth() -> None:
    row = mapping({"S": [100] * 26})["S"]
    assert row.xyz_class == XYZClass.X
    assert row.intermittency_class == IntermittencyClass.SMOOTH


def test_high_variation_is_z() -> None:
    row = mapping({"V": [0, 0, 0, 400] * 8})["V"]
    assert row.xyz_class == XYZClass.Z


def test_intermittent_adi_classification() -> None:
    row = mapping({"I": [0, 0, 0, 10] * 10})["I"]
    assert row.adi == 4
    assert row.intermittency_class == IntermittencyClass.INTERMITTENT
    assert row.recommended_forecast_models == ["CROSTON", "SBA", "TSB"]


def test_trend_is_y_and_gets_holt() -> None:
    row = mapping({"T": [100 + 10 * index for index in range(40)]})["T"]
    assert row.xyz_class == XYZClass.Y
    assert "HOLT" in row.recommended_forecast_models


def test_eol_strategy_restricts_replenishment() -> None:
    row = mapping({"E": [10] * 20}, lifecycles={"E": ProductLifecycle.EOL})["E"]
    assert "限制新增补货" in row.inventory_strategy
    assert row.requires_manual_review


def test_npi_requires_analog_or_expert_range() -> None:
    row = mapping({"N": []}, lifecycles={"N": "NPI"})["N"]
    assert row.recommended_forecast_models == ["ANALOG_OR_EXPERT_RANGE"]

