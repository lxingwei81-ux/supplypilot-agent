from __future__ import annotations

from datetime import date, timedelta
from math import isfinite
from statistics import fmean, pstdev
from typing import Callable, Sequence

from ..config import RulesConfig, load_rules
from ..models import (
    DemandClassification,
    ForecastConfidence,
    ForecastPoint,
    ForecastResult,
    IntermittencyClass,
    ProductLifecycle,
    XYZClass,
)


ForecastFunction = Callable[[Sequence[float], int, RulesConfig], list[float]]


def _clean(history: Sequence[float]) -> list[float]:
    values = [float(value) for value in history]
    if any(not isfinite(value) for value in values):
        raise ValueError("history contains non-finite demand")
    if any(value < 0 for value in values):
        raise ValueError("history contains negative demand; restore returns/cancellations before forecasting")
    return values


def naive(history: Sequence[float], horizon: int, rules: RulesConfig | None = None) -> list[float]:
    values = _clean(history)
    level = values[-1] if values else 0.0
    return [level] * horizon


def moving_average(history: Sequence[float], horizon: int, window: int) -> list[float]:
    values = _clean(history)
    if not values:
        return [0.0] * horizon
    output: list[float] = []
    working = values[:]
    for _ in range(horizon):
        forecast = fmean(working[-min(window, len(working)):])
        output.append(max(0.0, forecast))
        working.append(forecast)
    return output


def weighted_moving_average(history: Sequence[float], horizon: int, rules: RulesConfig) -> list[float]:
    values = _clean(history)
    weights = rules.forecast.parameters.weighted_moving_average_weights
    if not values:
        return [0.0] * horizon
    working = values[:]
    output: list[float] = []
    for _ in range(horizon):
        recent = list(reversed(working[-len(weights):]))
        selected_weights = weights[:len(recent)]
        scale = sum(selected_weights)
        forecast = sum(value * weight for value, weight in zip(recent, selected_weights)) / scale
        output.append(max(0.0, forecast))
        working.append(forecast)
    return output


def simple_exponential_smoothing(history: Sequence[float], horizon: int, rules: RulesConfig) -> list[float]:
    values = _clean(history)
    if not values:
        return [0.0] * horizon
    alpha = rules.forecast.parameters.ses_alpha
    level = values[0]
    for value in values[1:]:
        level = alpha * value + (1 - alpha) * level
    return [max(0.0, level)] * horizon


def holt(history: Sequence[float], horizon: int, rules: RulesConfig) -> list[float]:
    values = _clean(history)
    if len(values) < 2:
        return naive(values, horizon)
    alpha = rules.forecast.parameters.holt_alpha
    beta = rules.forecast.parameters.holt_beta
    level = values[0]
    trend = values[1] - values[0]
    for value in values[1:]:
        previous_level = level
        level = alpha * value + (1 - alpha) * (level + trend)
        trend = beta * (level - previous_level) + (1 - beta) * trend
    return [max(0.0, level + step * trend) for step in range(1, horizon + 1)]


def holt_winters(history: Sequence[float], horizon: int, rules: RulesConfig) -> list[float]:
    values = _clean(history)
    season = rules.forecast.parameters.seasonal_periods
    if len(values) < season * 2:
        return holt(values, horizon, rules)
    alpha = rules.forecast.parameters.holt_winters_alpha
    beta = rules.forecast.parameters.holt_winters_beta
    gamma = rules.forecast.parameters.holt_winters_gamma
    first_mean = fmean(values[:season])
    second_mean = fmean(values[season:season * 2])
    level = first_mean
    trend = (second_mean - first_mean) / season
    seasonal = [values[index] - first_mean for index in range(season)]
    for index, value in enumerate(values):
        season_index = index % season
        previous_level = level
        previous_season = seasonal[season_index]
        level = alpha * (value - previous_season) + (1 - alpha) * (level + trend)
        trend = beta * (level - previous_level) + (1 - beta) * trend
        seasonal[season_index] = gamma * (value - level) + (1 - gamma) * previous_season
    return [max(0.0, level + step * trend + seasonal[(len(values) + step - 1) % season]) for step in range(1, horizon + 1)]


def croston(history: Sequence[float], horizon: int, rules: RulesConfig, *, correction: float = 1.0) -> list[float]:
    values = _clean(history)
    nonzero_indices = [index for index, value in enumerate(values) if value > 0]
    if not nonzero_indices:
        return [0.0] * horizon
    alpha = rules.forecast.parameters.croston_alpha
    first = nonzero_indices[0]
    size = values[first]
    interval = float(first + 1)
    elapsed = 1.0
    for value in values[first + 1:]:
        if value > 0:
            size = alpha * value + (1 - alpha) * size
            interval = alpha * elapsed + (1 - alpha) * interval
            elapsed = 1.0
        else:
            elapsed += 1.0
    forecast = correction * size / max(interval, 1e-12)
    return [max(0.0, forecast)] * horizon


def sba(history: Sequence[float], horizon: int, rules: RulesConfig) -> list[float]:
    correction = 1 - rules.forecast.parameters.croston_alpha / 2
    return croston(history, horizon, rules, correction=correction)


def tsb(history: Sequence[float], horizon: int, rules: RulesConfig) -> list[float]:
    values = _clean(history)
    if not values or not any(value > 0 for value in values):
        return [0.0] * horizon
    alpha = rules.forecast.parameters.croston_alpha
    beta = rules.forecast.parameters.tsb_beta
    first_nonzero = next(value for value in values if value > 0)
    size = first_nonzero
    probability = 1.0 / max(1, next(index + 1 for index, value in enumerate(values) if value > 0))
    for value in values:
        occurrence = 1.0 if value > 0 else 0.0
        probability = beta * occurrence + (1 - beta) * probability
        if occurrence:
            size = alpha * value + (1 - alpha) * size
    return [max(0.0, probability * size)] * horizon


def decay(history: Sequence[float], horizon: int, rules: RulesConfig | None = None) -> list[float]:
    values = _clean(history)
    base = fmean(values[-min(4, len(values)):]) if values else 0.0
    return [max(0.0, base * (0.9 ** step)) for step in range(1, horizon + 1)]


MODEL_FUNCTIONS: dict[str, ForecastFunction] = {
    "NAIVE": lambda h, n, r: naive(h, n, r),
    "MA4": lambda h, n, r: moving_average(h, n, 4),
    "MA8": lambda h, n, r: moving_average(h, n, 8),
    "MA13": lambda h, n, r: moving_average(h, n, 13),
    "WMA": weighted_moving_average,
    "SES": simple_exponential_smoothing,
    "HOLT": holt,
    "HOLT_WINTERS": holt_winters,
    "CROSTON": croston,
    "SBA": sba,
    "TSB": tsb,
    "DECAY": lambda h, n, r: decay(h, n, r),
}


def forecast_model(model_name: str, history: Sequence[float], horizon: int, rules: RulesConfig | None = None) -> list[float]:
    cfg = rules or load_rules()
    normalized = model_name.upper()
    if normalized not in MODEL_FUNCTIONS:
        raise ValueError(f"unsupported forecast model: {model_name}")
    return MODEL_FUNCTIONS[normalized](history, horizon, cfg)


def candidate_models(classification: DemandClassification) -> list[str]:
    lifecycle = classification.lifecycle
    if lifecycle == ProductLifecycle.NPI:
        return []
    if lifecycle == ProductLifecycle.EOL:
        return ["DECAY", "NAIVE"]
    if classification.intermittency_class in {IntermittencyClass.INTERMITTENT, IntermittencyClass.LUMPY}:
        return ["CROSTON", "SBA", "TSB"]
    if classification.xyz_class == XYZClass.X:
        return ["NAIVE", "MA4", "MA8", "MA13", "WMA", "SES"]
    if classification.xyz_class == XYZClass.Y:
        return ["NAIVE", "SES", "HOLT", "HOLT_WINTERS"]
    return ["NAIVE", "SES", "HOLT"]


def _confidence(
    history: Sequence[float],
    classification: DemandClassification,
    selected_wape: float | None,
    rules: RulesConfig,
) -> ForecastConfidence:
    cfg = rules.forecast.confidence
    if len(history) < rules.forecast.backtest.min_training_periods:
        return ForecastConfidence.INSUFFICIENT
    if (
        len(history) >= cfg.high_min_periods
        and selected_wape is not None
        and selected_wape <= cfg.high_max_wape
        and (classification.cv or 0) <= cfg.high_max_cv
        and classification.intermittency_class == IntermittencyClass.SMOOTH
    ):
        return ForecastConfidence.HIGH
    if len(history) >= cfg.medium_min_periods and selected_wape is not None and selected_wape <= cfg.medium_max_wape:
        return ForecastConfidence.MEDIUM
    return ForecastConfidence.LOW


def generate_forecast(
    item_id: str,
    history: Sequence[float],
    classification: DemandClassification,
    *,
    last_history_week: date,
    history_source: str,
    previous_version_total: float | None = None,
    stockout_unit_cost: float | None = None,
    excess_unit_cost: float | None = None,
    rules: RulesConfig | None = None,
) -> ForecastResult:
    cfg = rules or load_rules()
    values = _clean(history)
    reviews: list[str] = []
    if classification.lifecycle == ProductLifecycle.NPI:
        return ForecastResult(
            item_id=item_id,
            confidence=ForecastConfidence.INSUFFICIENT,
            requires_manual_review=True,
            review_reasons=["NPI_WITHOUT_ANALOG_OR_PROJECT_EVIDENCE"],
            data_quality_warnings=["NPI无历史时不生成伪精确预测；请提供相似品、项目或预售数据"],
            history_source=history_source,
            rules_version=cfg.metadata.version,
        )
    models = candidate_models(classification)
    if len(values) < cfg.forecast.backtest.min_training_periods:
        reviews.append("INSUFFICIENT_HISTORY_FOR_ROLLING_BACKTEST")
    from .backtesting import rolling_backtest

    metrics = rolling_backtest(
        values,
        models,
        stockout_unit_cost=stockout_unit_cost,
        excess_unit_cost=excess_unit_cost,
        rules=cfg,
    )
    eligible = [metric for metric in metrics if metric.model_score is not None and metric.backtest_count >= cfg.forecast.backtest.min_backtests]
    if eligible:
        selected_metrics = min(eligible, key=lambda metric: (metric.model_score or float("inf"), metric.model_name))
        selected_model = selected_metrics.model_name
    else:
        selected_model = models[0] if models else "NAIVE"
        selected_metrics = next((metric for metric in metrics if metric.model_name == selected_model), None)
        reviews.append("MODEL_SELECTION_FALLBACK_NO_SUFFICIENT_BACKTESTS")
    horizon = max(cfg.forecast.horizons)
    baseline = forecast_model(selected_model, values, horizon, cfg)
    mean = fmean(values) if values else 0.0
    volatility = pstdev(values) / mean if len(values) > 1 and mean > 0 else 0.0
    band = min(1.0, max(cfg.forecast.scenario_band.minimum_rate, volatility * cfg.forecast.scenario_band.volatility_multiplier))
    points: list[ForecastPoint] = []
    for index, quantity in enumerate(baseline, start=1):
        week = last_history_week + timedelta(days=7 * index)
        lower = max(0.0, quantity * (1 - band))
        upper = quantity * (1 + band)
        points.append(ForecastPoint(
            item_id=item_id,
            week_start=week,
            horizon_week=index,
            baseline_qty=quantity,
            optimistic_qty=upper,
            pessimistic_qty=lower,
            lower_bound=lower,
            upper_bound=upper,
            model_name=selected_model,
            source_version=history_source,
        ))
    horizon_totals = {horizon_value: sum(point.baseline_qty for point in points[:horizon_value]) for horizon_value in cfg.forecast.horizons}
    total_13 = horizon_totals.get(13, sum(baseline[:13]))
    previous_change = None
    if previous_version_total is not None:
        previous_change = (total_13 - previous_version_total) / max(abs(previous_version_total), 1.0)
    selected_wape = selected_metrics.wape if selected_metrics else None
    confidence = _confidence(values, classification, selected_wape, cfg)
    if classification.xyz_class == XYZClass.Z:
        reviews.append("HIGH_VOLATILITY_SCENARIO_REVIEW")
    if classification.intermittency_class in {IntermittencyClass.INTERMITTENT, IntermittencyClass.LUMPY}:
        reviews.append("INTERMITTENT_DEMAND_POLICY_REVIEW")
    if classification.lifecycle == ProductLifecycle.EOL:
        reviews.append("EOL_REPLENISHMENT_RESTRICTED")
    return ForecastResult(
        item_id=item_id,
        selected_model=selected_model,
        points=points,
        horizon_totals=horizon_totals,
        candidate_metrics=metrics,
        selected_metrics=selected_metrics,
        confidence=confidence,
        requires_manual_review=confidence in {ForecastConfidence.LOW, ForecastConfidence.INSUFFICIENT} or bool(reviews),
        review_reasons=sorted(set(reviews)),
        previous_version_change=previous_change,
        history_source=history_source,
        rules_version=cfg.metadata.version,
    )

