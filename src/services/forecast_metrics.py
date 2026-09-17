from __future__ import annotations

from typing import Sequence

from ..models import ForecastMetrics


def _pairs(actual: Sequence[float], predicted: Sequence[float]) -> list[tuple[float, float]]:
    return [(max(0.0, float(a)), max(0.0, float(p))) for a, p in zip(actual, predicted)]


def wape(actual: Sequence[float], predicted: Sequence[float]) -> float | None:
    pairs = _pairs(actual, predicted)
    denominator = sum(actual_value for actual_value, _ in pairs)
    if denominator == 0:
        return None
    return sum(abs(actual_value - predicted_value) for actual_value, predicted_value in pairs) / denominator


def bias(actual: Sequence[float], predicted: Sequence[float]) -> float | None:
    """Positive bias means over-forecast; negative bias means under-forecast."""
    pairs = _pairs(actual, predicted)
    denominator = sum(actual_value for actual_value, _ in pairs)
    if denominator == 0:
        return None
    return sum(predicted_value - actual_value for actual_value, predicted_value in pairs) / denominator


def mae(actual: Sequence[float], predicted: Sequence[float]) -> float | None:
    pairs = _pairs(actual, predicted)
    if not pairs:
        return None
    return sum(abs(actual_value - predicted_value) for actual_value, predicted_value in pairs) / len(pairs)


def calculate_metrics(
    model_name: str,
    actual: Sequence[float],
    predicted: Sequence[float],
    *,
    backtest_count: int,
    expected_points: int,
    stockout_unit_cost: float,
    excess_unit_cost: float,
    weights: tuple[float, float, float, float],
) -> ForecastMetrics:
    pairs = _pairs(actual, predicted)
    total_actual = sum(actual_value for actual_value, _ in pairs)
    normalizer = max(total_actual, 1.0)
    stockout_loss = sum(max(0.0, actual_value - predicted_value) for actual_value, predicted_value in pairs)
    excess_loss = sum(max(0.0, predicted_value - actual_value) for actual_value, predicted_value in pairs)
    stockout_loss = stockout_loss * stockout_unit_cost / normalizer
    excess_loss = excess_loss * excess_unit_cost / normalizer
    metric_wape = wape(actual, predicted)
    metric_bias = bias(actual, predicted)
    metric_mae = mae(actual, predicted)
    if not pairs:
        score = None
    else:
        score = (
            weights[0] * (metric_wape if metric_wape is not None else 1.0)
            + weights[1] * abs(metric_bias if metric_bias is not None else 0.0)
            + weights[2] * stockout_loss
            + weights[3] * excess_loss
        )
    return ForecastMetrics(
        model_name=model_name,
        wape=metric_wape,
        bias=metric_bias,
        mae=metric_mae,
        stockout_loss=stockout_loss,
        excess_loss=excess_loss,
        model_score=score,
        backtest_count=backtest_count,
        data_coverage=len(pairs) / expected_points if expected_points else 0.0,
        zero_actual_periods=sum(1 for actual_value, _ in pairs if actual_value == 0),
    )

