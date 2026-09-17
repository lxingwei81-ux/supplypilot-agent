from __future__ import annotations

from datetime import date

import pytest

from src.models import ForecastConfidence, ProductLifecycle
from src.services.backtesting import rolling_backtest, rolling_backtest_trace
from src.services.demand_classification import classify_demand
from src.services.forecast_metrics import bias, wape
from src.services.forecasting import MODEL_FUNCTIONS, forecast_model, generate_forecast


def classification(item, history, lifecycle="MATURE"):
    return classify_demand({item: history}, lifecycles={item: lifecycle}, source_version="T")[0]


@pytest.mark.parametrize("model", sorted(MODEL_FUNCTIONS))
def test_every_model_is_deterministic_and_nonnegative(model: str) -> None:
    history = [0, 10, 0, 20, 30, 10, 0, 15] * 5
    first = forecast_model(model, history, 26)
    second = forecast_model(model, history, 26)
    assert first == second
    assert len(first) == 26
    assert all(value >= 0 for value in first)


def test_insufficient_history_is_flagged() -> None:
    history = [10] * 8
    result = generate_forecast("A", history, classification("A", history), last_history_week=date(2026, 1, 5), history_source="T")
    assert result.confidence == ForecastConfidence.INSUFFICIENT
    assert result.requires_manual_review


def test_all_zero_wape_is_safe() -> None:
    assert wape([0, 0], [0, 1]) is None
    metrics = rolling_backtest([0] * 30, ["NAIVE"])[0]
    assert metrics.wape is None
    assert metrics.model_score is not None


def test_bias_direction() -> None:
    assert bias([10, 10], [12, 12]) > 0
    assert bias([10, 10], [8, 8]) < 0


def test_stable_forecast_has_all_horizons() -> None:
    history = [100] * 60
    result = generate_forecast("S", history, classification("S", history), last_history_week=date(2026, 1, 5), history_source="T")
    assert set(result.horizon_totals) == {4, 8, 13, 26}
    assert len(result.points) == 26


def test_trend_candidates_include_holt() -> None:
    history = [100 + 5 * index for index in range(60)]
    result = generate_forecast("T", history, classification("T", history), last_history_week=date(2026, 1, 5), history_source="T")
    assert "HOLT" in {metric.model_name for metric in result.candidate_metrics}


def test_seasonal_candidates_include_holt_winters() -> None:
    seasonal = [100, 130, 160, 130, 100, 70, 40, 70, 100, 120, 140, 120, 100]
    history = seasonal * 5
    result = generate_forecast("Y", history, classification("Y", history), last_history_week=date(2026, 1, 5), history_source="T")
    assert "HOLT_WINTERS" in {metric.model_name for metric in result.candidate_metrics}


def test_intermittent_candidates_only_specialized_models() -> None:
    history = [0, 0, 0, 20] * 15
    result = generate_forecast("I", history, classification("I", history), last_history_week=date(2026, 1, 5), history_source="T")
    assert {metric.model_name for metric in result.candidate_metrics} == {"CROSTON", "SBA", "TSB"}


def test_rolling_trace_has_no_future_leakage() -> None:
    history = [10 + index for index in range(30)]
    changed_future = history[:17] + [9999] * 13
    first = rolling_backtest_trace(history, "MA4")
    second = rolling_backtest_trace(changed_future, "MA4")
    assert all(row["training_end_index"] < row["target_index"] for row in first)
    first_fold_a = [row["forecast"] for row in first if row["fold"] == 1]
    first_fold_b = [row["forecast"] for row in second if row["fold"] == 1]
    assert first_fold_a == first_fold_b


def test_model_selection_reproducible() -> None:
    history = [100 + (index % 4) * 5 for index in range(52)]
    c = classification("R", history)
    one = generate_forecast("R", history, c, last_history_week=date(2026, 1, 5), history_source="T")
    two = generate_forecast("R", history, c, last_history_week=date(2026, 1, 5), history_source="T")
    assert one.selected_model == two.selected_model
    assert [point.baseline_qty for point in one.points] == [point.baseline_qty for point in two.points]


def test_npi_does_not_create_pseudo_precision() -> None:
    history: list[float] = []
    result = generate_forecast("N", history, classification("N", history, ProductLifecycle.NPI), last_history_week=date(2026, 1, 5), history_source="T")
    assert not result.points
    assert result.confidence == ForecastConfidence.INSUFFICIENT


def test_eol_uses_decay_candidate() -> None:
    history = [100] * 30
    result = generate_forecast("E", history, classification("E", history, ProductLifecycle.EOL), last_history_week=date(2026, 1, 5), history_source="T")
    assert "DECAY" in {metric.model_name for metric in result.candidate_metrics}
