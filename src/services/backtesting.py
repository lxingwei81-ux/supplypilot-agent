from __future__ import annotations

from typing import Sequence

from ..config import RulesConfig, load_rules
from ..models import ForecastMetrics
from .forecast_metrics import calculate_metrics
from .forecasting import forecast_model


def rolling_backtest(
    history: Sequence[float],
    model_names: Sequence[str],
    *,
    stockout_unit_cost: float | None = None,
    excess_unit_cost: float | None = None,
    rules: RulesConfig | None = None,
) -> list[ForecastMetrics]:
    cfg = rules or load_rules()
    values = [max(0.0, float(value)) for value in history]
    bt = cfg.forecast.backtest
    weights = cfg.forecast.score_weights
    score_weights = (weights.wape, weights.absolute_bias, weights.stockout_loss, weights.excess_loss)
    stockout_cost = stockout_unit_cost if stockout_unit_cost is not None else cfg.forecast.loss_costs.default_stockout_unit_cost
    excess_cost = excess_unit_cost if excess_unit_cost is not None else cfg.forecast.loss_costs.default_excess_unit_cost
    results: list[ForecastMetrics] = []
    for model_name in model_names:
        actual: list[float] = []
        predicted: list[float] = []
        count = 0
        for origin in range(bt.min_training_periods, len(values) - bt.forecast_horizon + 1, bt.step):
            training = values[:origin]
            holdout = values[origin:origin + bt.forecast_horizon]
            # Only observations strictly before origin are passed to the model.
            fold_prediction = forecast_model(model_name, training, bt.forecast_horizon, cfg)
            actual.extend(holdout)
            predicted.extend(fold_prediction)
            count += 1
        expected = count * bt.forecast_horizon
        results.append(calculate_metrics(
            model_name,
            actual,
            predicted,
            backtest_count=count,
            expected_points=expected,
            stockout_unit_cost=stockout_cost,
            excess_unit_cost=excess_cost,
            weights=score_weights,
        ))
    return results


def rolling_backtest_trace(
    history: Sequence[float],
    model_name: str,
    *,
    rules: RulesConfig | None = None,
) -> list[dict[str, float | int | str]]:
    """Return auditable fold-level points for UI comparison without exposing future data to training."""
    cfg = rules or load_rules()
    values = [max(0.0, float(value)) for value in history]
    bt = cfg.forecast.backtest
    trace: list[dict[str, float | int | str]] = []
    fold = 0
    for origin in range(bt.min_training_periods, len(values) - bt.forecast_horizon + 1, bt.step):
        fold += 1
        prediction = forecast_model(model_name, values[:origin], bt.forecast_horizon, cfg)
        for offset, forecast in enumerate(prediction):
            trace.append({
                "fold": fold,
                "training_end_index": origin - 1,
                "target_index": origin + offset,
                "actual": values[origin + offset],
                "forecast": forecast,
                "model": model_name,
            })
    return trace
