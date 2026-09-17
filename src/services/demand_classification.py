from __future__ import annotations

from statistics import fmean, pstdev
from typing import Mapping, Sequence

from ..config import RulesConfig, load_rules
from ..models import (
    ABCClass,
    DemandClassification,
    IntermittencyClass,
    ProductLifecycle,
    XYZClass,
)


def _xyz(cv: float | None, trend_rate: float, seasonal_strength: float, rules: RulesConfig) -> XYZClass:
    if cv is None:
        return XYZClass.Z
    if cv > rules.classification.xyz.y_max_cv:
        return XYZClass.Z
    if (
        abs(trend_rate) >= rules.classification.xyz.trend_rate_threshold
        or seasonal_strength >= rules.classification.xyz.seasonal_autocorrelation_threshold
    ):
        return XYZClass.Y
    if cv <= rules.classification.xyz.x_max_cv:
        return XYZClass.X
    return XYZClass.Y


def _pearson_lag(values: list[float], lag: int) -> float:
    if len(values) < lag * 2:
        return 0.0
    left = values[:-lag]
    right = values[lag:]
    left_mean = fmean(left)
    right_mean = fmean(right)
    numerator = sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right))
    denominator = (sum((a - left_mean) ** 2 for a in left) * sum((b - right_mean) ** 2 for b in right)) ** 0.5
    return numerator / denominator if denominator > 0 else 0.0


def _intermittency(adi: float | None, cv_squared: float | None, rules: RulesConfig) -> IntermittencyClass:
    if adi is None or cv_squared is None:
        return IntermittencyClass.LUMPY
    intermittent = adi >= rules.classification.intermittency.adi_threshold
    variable_size = cv_squared >= rules.classification.intermittency.cv_squared_threshold
    if not intermittent and not variable_size:
        return IntermittencyClass.SMOOTH
    if not intermittent and variable_size:
        return IntermittencyClass.ERRATIC
    if intermittent and not variable_size:
        return IntermittencyClass.INTERMITTENT
    return IntermittencyClass.LUMPY


def recommended_models(
    xyz_class: XYZClass,
    intermittency: IntermittencyClass,
    lifecycle: ProductLifecycle,
) -> list[str]:
    if lifecycle == ProductLifecycle.NPI:
        return ["ANALOG_OR_EXPERT_RANGE"]
    if lifecycle == ProductLifecycle.EOL:
        return ["DECAY", "MANUAL_CONFIRMATION"]
    if intermittency in {IntermittencyClass.INTERMITTENT, IntermittencyClass.LUMPY}:
        return ["CROSTON", "SBA", "TSB"]
    if xyz_class == XYZClass.X:
        return ["MA4", "MA8", "MA13", "WMA", "SES"]
    if xyz_class == XYZClass.Y:
        return ["HOLT", "HOLT_WINTERS", "SES"]
    return ["NAIVE", "SES", "SCENARIO_REVIEW"]


def inventory_strategy(
    abc: ABCClass,
    xyz: XYZClass,
    intermittency: IntermittencyClass,
    lifecycle: ProductLifecycle,
) -> str:
    if lifecycle == ProductLifecycle.EOL:
        return "限制新增补货，优先消耗在库与取消未锁定PO，人工确认售后需求"
    if lifecycle == ProductLifecycle.NPI:
        return "分阶段小批量承诺，按预售和早期实需滚动修正"
    if intermittency in {IntermittencyClass.INTERMITTENT, IntermittencyClass.LUMPY}:
        return "使用间歇需求策略与服务水平分层，避免以均值堆积库存"
    if abc == ABCClass.A and xyz == XYZClass.X:
        return "高服务水平、统计安全库存、连续复核补货"
    if xyz == XYZClass.Z:
        return "情景区间+人工复核，控制单次承诺并缩短响应周期"
    return "按ABC-XYZ服务水平设置安全库存和再订货点"


def classify_demand(
    histories: Mapping[str, Sequence[float]],
    *,
    unit_costs: Mapping[str, float] | None = None,
    lifecycles: Mapping[str, ProductLifecycle | str] | None = None,
    source_version: str = "UNVERSIONED",
    rules: RulesConfig | None = None,
) -> list[DemandClassification]:
    cfg = rules or load_rules()
    costs = unit_costs or {}
    lifecycle_values = lifecycles or {}
    raw: list[dict[str, object]] = []
    for item_id in sorted(histories):
        demand = [max(0.0, float(value)) for value in histories[item_id]]
        annual_demand = sum(demand[-52:])
        unit_cost = max(0.0, float(costs.get(item_id, 0.0)))
        annual_value = annual_demand * unit_cost
        mean = fmean(demand) if demand else 0.0
        std = pstdev(demand) if len(demand) > 1 else 0.0
        cv = std / mean if mean > 0 else None
        nonzero = [value for value in demand if value > 0]
        adi = len(demand) / len(nonzero) if nonzero else None
        nonzero_mean = fmean(nonzero) if nonzero else 0.0
        nonzero_cv = pstdev(nonzero) / nonzero_mean if len(nonzero) > 1 and nonzero_mean > 0 else 0.0
        cv_squared = nonzero_cv ** 2 if nonzero else None
        midpoint = len(demand) // 2
        first_half = fmean(demand[:midpoint]) if midpoint else mean
        second_half = fmean(demand[midpoint:]) if demand[midpoint:] else mean
        trend_rate = (second_half - first_half) / max(mean, 1.0)
        seasonal_strength = max(0.0, _pearson_lag(demand, cfg.forecast.parameters.seasonal_periods))
        lifecycle_raw = lifecycle_values.get(item_id, ProductLifecycle.MATURE)
        lifecycle = lifecycle_raw if isinstance(lifecycle_raw, ProductLifecycle) else ProductLifecycle(str(lifecycle_raw).upper().replace("-", "_"))
        raw.append({
            "item_id": item_id,
            "annual_demand": annual_demand,
            "unit_cost": unit_cost,
            "annual_value": annual_value,
            "mean": mean,
            "std": std,
            "cv": cv,
            "adi": adi,
            "cv_squared": cv_squared,
            "trend_rate": trend_rate,
            "seasonal_strength": seasonal_strength,
            "lifecycle": lifecycle,
        })

    total_value = sum(float(item["annual_value"]) for item in raw)
    ordered = sorted(raw, key=lambda item: (-float(item["annual_value"]), str(item["item_id"])))
    cumulative = 0.0
    class_by_item: dict[str, tuple[ABCClass, float]] = {}
    for item in ordered:
        previous_share = cumulative / total_value if total_value > 0 else 1.0
        cumulative += float(item["annual_value"])
        share = cumulative / total_value if total_value > 0 else 1.0
        if total_value == 0:
            abc = ABCClass.C
        elif previous_share < cfg.classification.abc.a_cumulative_value:
            abc = ABCClass.A
        elif previous_share < cfg.classification.abc.b_cumulative_value:
            abc = ABCClass.B
        else:
            abc = ABCClass.C
        class_by_item[str(item["item_id"])] = (abc, min(share, 1.0))

    results: list[DemandClassification] = []
    for item in raw:
        item_id = str(item["item_id"])
        abc, share = class_by_item[item_id]
        xyz = _xyz(item["cv"], float(item["trend_rate"]), float(item["seasonal_strength"]), cfg)  # type: ignore[arg-type]
        intermittency = _intermittency(item["adi"], item["cv_squared"], cfg)  # type: ignore[arg-type]
        lifecycle = item["lifecycle"]
        assert isinstance(lifecycle, ProductLifecycle)
        reasons: list[str] = []
        if item["cv"] is None:
            reasons.append("ZERO_MEAN_DEMAND")
        if intermittency in {IntermittencyClass.INTERMITTENT, IntermittencyClass.LUMPY}:
            reasons.append("INTERMITTENT_DEMAND")
        if lifecycle in {ProductLifecycle.NPI, ProductLifecycle.EOL}:
            reasons.append(f"LIFECYCLE_{lifecycle.value}")
        if xyz == XYZClass.Y and abs(float(item["trend_rate"])) >= cfg.classification.xyz.trend_rate_threshold:
            reasons.append("TREND_DETECTED")
        if xyz == XYZClass.Y and float(item["seasonal_strength"]) >= cfg.classification.xyz.seasonal_autocorrelation_threshold:
            reasons.append("SEASONALITY_DETECTED")
        requires_review = xyz == XYZClass.Z or bool(reasons)
        results.append(DemandClassification(
            item_id=item_id,
            abc_class=abc,
            xyz_class=xyz,
            intermittency_class=intermittency,
            lifecycle=lifecycle,
            annual_demand=float(item["annual_demand"]),
            unit_cost=float(item["unit_cost"]),
            annual_value=float(item["annual_value"]),
            cumulative_value_share=share,
            mean_demand=float(item["mean"]),
            demand_std=float(item["std"]),
            cv=item["cv"],  # type: ignore[arg-type]
            adi=item["adi"],  # type: ignore[arg-type]
            cv_squared=item["cv_squared"],  # type: ignore[arg-type]
            recommended_forecast_models=recommended_models(xyz, intermittency, lifecycle),
            inventory_strategy=inventory_strategy(abc, xyz, intermittency, lifecycle),
            requires_manual_review=requires_review,
            reason_codes=reasons,
            source_version=source_version,
        ))
    return sorted(results, key=lambda result: result.item_id)
