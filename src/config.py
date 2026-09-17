from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BacktestConfig(StrictConfig):
    forecast_horizon: int = Field(gt=0)
    min_training_periods: int = Field(ge=4)
    step: int = Field(gt=0)
    min_backtests: int = Field(gt=0)


class ForecastParameters(StrictConfig):
    weighted_moving_average_weights: list[float]
    ses_alpha: float
    holt_alpha: float
    holt_beta: float
    holt_winters_alpha: float
    holt_winters_beta: float
    holt_winters_gamma: float
    seasonal_periods: int = Field(ge=2)
    croston_alpha: float
    tsb_beta: float

    @field_validator(
        "ses_alpha", "holt_alpha", "holt_beta", "holt_winters_alpha",
        "holt_winters_beta", "holt_winters_gamma", "croston_alpha", "tsb_beta"
    )
    @classmethod
    def probability(cls, value: float) -> float:
        if not 0 < value <= 1:
            raise ValueError("smoothing parameters must be in (0, 1]")
        return value

    @field_validator("weighted_moving_average_weights")
    @classmethod
    def weights_sum_to_one(cls, value: list[float]) -> list[float]:
        if not value or any(weight < 0 for weight in value) or abs(sum(value) - 1.0) > 1e-9:
            raise ValueError("weighted moving-average weights must be non-negative and sum to 1")
        return value


class ScoreWeights(StrictConfig):
    wape: float = Field(ge=0)
    absolute_bias: float = Field(ge=0)
    stockout_loss: float = Field(ge=0)
    excess_loss: float = Field(ge=0)

    @model_validator(mode="after")
    def sum_to_one(self) -> "ScoreWeights":
        if abs(sum((self.wape, self.absolute_bias, self.stockout_loss, self.excess_loss)) - 1.0) > 1e-9:
            raise ValueError("forecast score weights must sum to 1")
        return self


class LossCosts(StrictConfig):
    default_stockout_unit_cost: float = Field(ge=0)
    default_excess_unit_cost: float = Field(ge=0)


class ScenarioBand(StrictConfig):
    minimum_rate: float = Field(ge=0, le=1)
    volatility_multiplier: float = Field(ge=0)


class ConfidenceConfig(StrictConfig):
    high_min_periods: int = Field(gt=0)
    medium_min_periods: int = Field(gt=0)
    high_max_wape: float = Field(ge=0)
    medium_max_wape: float = Field(ge=0)
    high_max_cv: float = Field(ge=0)


class ForecastConfig(StrictConfig):
    horizons: list[int]
    backtest: BacktestConfig
    parameters: ForecastParameters
    score_weights: ScoreWeights
    loss_costs: LossCosts
    scenario_band: ScenarioBand
    confidence: ConfidenceConfig
    fva_tolerance: float = Field(ge=0)

    @field_validator("horizons")
    @classmethod
    def required_horizons(cls, value: list[int]) -> list[int]:
        if sorted(set(value)) != [4, 8, 13, 26]:
            raise ValueError("forecast horizons must contain exactly 4, 8, 13 and 26")
        return value


class ABCConfig(StrictConfig):
    a_cumulative_value: float
    b_cumulative_value: float

    @model_validator(mode="after")
    def ordered(self) -> "ABCConfig":
        if not 0 < self.a_cumulative_value < self.b_cumulative_value <= 1:
            raise ValueError("ABC thresholds must satisfy 0 < A < B <= 1")
        return self


class XYZConfig(StrictConfig):
    x_max_cv: float = Field(ge=0)
    y_max_cv: float = Field(ge=0)
    trend_rate_threshold: float = Field(ge=0)
    seasonal_autocorrelation_threshold: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def ordered(self) -> "XYZConfig":
        if self.x_max_cv >= self.y_max_cv:
            raise ValueError("XYZ thresholds must satisfy X < Y")
        return self


class IntermittencyConfig(StrictConfig):
    adi_threshold: float = Field(gt=0)
    cv_squared_threshold: float = Field(ge=0)


class ClassificationConfig(StrictConfig):
    abc: ABCConfig
    xyz: XYZConfig
    intermittency: IntermittencyConfig


class CoverageConfig(StrictConfig):
    shortage_warning_below: float = Field(ge=0)
    excess_13w_above: float = Field(gt=0)
    excess_26w_above: float = Field(gt=0)


class LotSizingConfig(StrictConfig):
    default_moq: float = Field(gt=0)
    default_mpq: float = Field(gt=0)
    default_package_multiple: float = Field(gt=0)


class InventoryConfig(StrictConfig):
    service_levels: dict[str, float]
    default_lead_time_variance: float = Field(ge=0)
    coverage_weeks: CoverageConfig
    lot_sizing: LotSizingConfig
    eol_new_replenishment_allowed: bool

    @field_validator("service_levels")
    @classmethod
    def valid_service_levels(cls, value: dict[str, float]) -> dict[str, float]:
        if "default" not in value or any(not 0.5 < level < 1 for level in value.values()):
            raise ValueError("service levels must contain default and be between 0.5 and 1")
        return value


class DemandChangeConfig(StrictConfig):
    absolute_threshold: float = Field(ge=0)
    increase_rate: float = Field(gt=0)
    decrease_rate: float = Field(lt=0)
    actual_forecast_deviation_warning: float = Field(ge=0)


class QuantityRiskConfig(StrictConfig):
    critical_qty: float = Field(ge=0)
    high_qty: float = Field(ge=0)
    medium_qty: float = Field(ge=0)
    critical_weeks_to_event: int = Field(ge=0)
    high_weeks_to_event: int = Field(ge=0)


class ValueRiskConfig(StrictConfig):
    critical_value: float = Field(ge=0)
    high_value: float = Field(ge=0)
    medium_value: float = Field(ge=0)


class AgingConfig(StrictConfig):
    warning_days: int = Field(ge=0)
    critical_days: int = Field(ge=0)


class RiskConfig(StrictConfig):
    shortage: QuantityRiskConfig
    excess: ValueRiskConfig
    aging: AgingConfig


class ProcurementConfig(StrictConfig):
    long_lead_time_days: int = Field(gt=0)
    cancellation_window_days: int = Field(ge=0)
    processing_days: int = Field(ge=0)
    maximum_cancellation_penalty_rate: float = Field(ge=0, le=1)


class ApprovalConfig(StrictConfig):
    matrix: dict[str, list[str]]


class DataQualityConfig(StrictConfig):
    blocking_codes: list[str]
    minimum_history_periods: int = Field(gt=0)
    required_fields: dict[str, list[str]]


class MetadataConfig(StrictConfig):
    version: str
    source: str
    demo_only: bool


class ReportingConfig(StrictConfig):
    currency: str
    timezone: str
    trace_source_label: str


class AllocationConfig(StrictConfig):
    frozen_order_bonus: float = Field(ge=0)
    customer_priority_weight: float = Field(ge=0)
    shortage_penalty_weight: float = Field(ge=0)
    due_urgency_weight: float = Field(ge=0)
    lifecycle_priority: dict[str, float]
    minimum_fair_share: float = Field(ge=0, le=1)


class TransferOptimizationConfig(StrictConfig):
    default_unit_transfer_cost: float = Field(ge=0)
    default_fixed_transfer_cost: float = Field(ge=0)
    maximum_lead_time_days: int = Field(gt=0)
    minimum_source_coverage_weeks: float = Field(ge=0)
    shortage_penalty_per_unit: float = Field(gt=0)


class POOptimizationConfig(StrictConfig):
    default_holding_cost_per_unit_week: float = Field(ge=0)
    default_obsolescence_cost_per_unit: float = Field(ge=0)
    default_shortage_cost_per_unit: float = Field(gt=0)
    default_cancellation_cost_rate: float = Field(ge=0, le=1)
    maximum_dynamic_programming_states: int = Field(gt=0)


class ReplenishmentOptimizationConfig(StrictConfig):
    default_order_fixed_cost: float = Field(ge=0)
    default_holding_cost_per_unit: float = Field(ge=0)
    default_shortage_cost_per_unit: float = Field(gt=0)
    maximum_target_multiplier: float = Field(gt=0)
    maximum_candidates: int = Field(gt=0)


class ECNWorkflowConfig(StrictConfig):
    require_customer_approval_for_customer_characteristic: bool
    required_evidence: dict[str, list[str]]


class SnapshotConfig(StrictConfig):
    retention_weeks: int = Field(gt=0)
    trend_windows: list[int]

    @field_validator("trend_windows")
    @classmethod
    def positive_windows(cls, value: list[int]) -> list[int]:
        if not value or any(window <= 0 for window in value):
            raise ValueError("snapshot trend windows must be positive")
        return sorted(set(value))


class ExcelImportConfig(StrictConfig):
    maximum_rows: int = Field(gt=0)
    allowed_extensions: list[str]
    aliases: dict[str, list[str]]


class TaskManagementConfig(StrictConfig):
    reminder_days_before_due: int = Field(ge=0)
    overdue_escalation_days: list[int]
    escalation_roles: list[str]

    @model_validator(mode="after")
    def escalation_alignment(self) -> "TaskManagementConfig":
        if len(self.overdue_escalation_days) != len(self.escalation_roles):
            raise ValueError("escalation days and roles must have the same length")
        if self.overdue_escalation_days != sorted(self.overdue_escalation_days):
            raise ValueError("overdue escalation days must be ordered")
        return self


class SupplierReliabilityWeights(StrictConfig):
    on_time_rate: float = Field(ge=0)
    quantity_fill_rate: float = Field(ge=0)
    lead_time_stability: float = Field(ge=0)
    confirmation_adherence: float = Field(ge=0)

    @model_validator(mode="after")
    def sum_to_one(self) -> "SupplierReliabilityWeights":
        total = self.on_time_rate + self.quantity_fill_rate + self.lead_time_stability + self.confirmation_adherence
        if abs(total - 1.0) > 1e-9:
            raise ValueError("supplier reliability weights must sum to 1")
        return self


class SupplierReliabilityConfig(StrictConfig):
    on_time_tolerance_days: int = Field(ge=0)
    minimum_samples: int = Field(gt=0)
    weights: SupplierReliabilityWeights
    grade_thresholds: dict[str, float]

    @field_validator("grade_thresholds")
    @classmethod
    def valid_grades(cls, value: dict[str, float]) -> dict[str, float]:
        if set(value) != {"A", "B", "C"} or not (1 >= value["A"] > value["B"] > value["C"] >= 0):
            raise ValueError("supplier grade thresholds must satisfy 1>=A>B>C>=0")
        return value


class ScenarioOptimizationConfig(StrictConfig):
    holding_cost_per_unit_week: float = Field(ge=0)
    shortage_cost_per_unit: float = Field(gt=0)
    excess_cost_per_unit: float = Field(ge=0)
    maximum_allowed_shortage: float = Field(ge=0)


class RulesConfig(StrictConfig):
    metadata: MetadataConfig
    forecast: ForecastConfig
    classification: ClassificationConfig
    inventory: InventoryConfig
    demand_change: DemandChangeConfig
    risk: RiskConfig
    procurement: ProcurementConfig
    approvals: ApprovalConfig
    data_quality: DataQualityConfig
    reporting: ReportingConfig
    allocation: AllocationConfig
    transfer_optimization: TransferOptimizationConfig
    po_optimization: POOptimizationConfig
    replenishment_optimization: ReplenishmentOptimizationConfig
    ecn_workflow: ECNWorkflowConfig
    snapshots: SnapshotConfig
    excel_import: ExcelImportConfig
    task_management: TaskManagementConfig
    supplier_reliability: SupplierReliabilityConfig
    scenario_optimization: ScenarioOptimizationConfig


DEFAULT_RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "rules.yaml"


@lru_cache(maxsize=8)
def load_rules(path: str | Path = DEFAULT_RULES_PATH) -> RulesConfig:
    rules_path = Path(path)
    with rules_path.open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle)
    return RulesConfig.model_validate(raw)
