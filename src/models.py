from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)


class ScenarioType(str, Enum):
    DATA_QUALITY = "DATA_QUALITY"
    MPS_DATA_QUALITY = "MPS_DATA_QUALITY"
    DEMAND_INCREASE = "DEMAND_INCREASE"
    DEMAND_DECREASE = "DEMAND_DECREASE"
    FORECAST_VERSION_CHANGE = "FORECAST_VERSION_CHANGE"
    FORECAST_MANUAL_ADJUSTMENT = "FORECAST_MANUAL_ADJUSTMENT"
    SUPPLY_DELAY = "SUPPLY_DELAY"
    PRODUCT_SUPPLY_RISK = "PRODUCT_SUPPLY_RISK"
    STATIC_SHORTAGE = "STATIC_SHORTAGE"
    DYNAMIC_SHORTAGE = "DYNAMIC_SHORTAGE"
    BELOW_SAFETY_STOCK = "BELOW_SAFETY_STOCK"
    LONG_LT_SHORTAGE = "LONG_LT_SHORTAGE"
    PO_LATE = "PO_LATE"
    PR_NOT_CONVERTED = "PR_NOT_CONVERTED"
    SHARED_MATERIAL_COMPETITION = "SHARED_MATERIAL_COMPETITION"
    INVENTORY_EXCESS = "INVENTORY_EXCESS"
    OBSOLETE_INVENTORY = "OBSOLETE_INVENTORY"
    NO_DEMAND_OPEN_PO = "NO_DEMAND_OPEN_PO"
    EOL_INVENTORY = "EOL_INVENTORY"
    PO_EXPEDITE = "PO_EXPEDITE"
    PO_DELAY = "PO_DELAY"
    PO_REDUCTION = "PO_REDUCTION"
    PO_CANCELLATION = "PO_CANCELLATION"
    CROSS_PLANT_TRANSFER = "CROSS_PLANT_TRANSFER"
    SUBSTITUTE_MATERIAL = "SUBSTITUTE_MATERIAL"
    ECN_SWITCH = "ECN_SWITCH"
    COMMON_MATERIAL_CONSUMPTION = "COMMON_MATERIAL_CONSUMPTION"
    SUPPLIER_RETURN = "SUPPLIER_RETURN"
    STRANDED_INVENTORY = "STRANDED_INVENTORY"
    WHAT_IF_SIMULATION = "WHAT_IF_SIMULATION"


class RiskType(str, Enum):
    SHORTAGE = "SHORTAGE"
    BELOW_SAFETY_STOCK = "BELOW_SAFETY_STOCK"
    LATE_SUPPLY = "LATE_SUPPLY"
    EXCESS = "EXCESS"
    OBSOLETE = "OBSOLETE"
    QUALITY_HOLD = "QUALITY_HOLD"
    SINGLE_SOURCE = "SINGLE_SOURCE"
    ECN = "ECN"


class RiskLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ActionType(str, Enum):
    DELETE_PR = "DELETE_PR"
    CANCEL_PO = "CANCEL_PO"
    REDUCE_PO = "REDUCE_PO"
    EXPEDITE_PO = "EXPEDITE_PO"
    DELAY_PO = "DELAY_PO"
    SPLIT_PO = "SPLIT_PO"
    TRANSFER = "TRANSFER"
    SUBSTITUTE = "SUBSTITUTE"
    ECN_SWITCH = "ECN_SWITCH"
    DEMAND_ADJUST = "DEMAND_ADJUST"
    SAFETY_STOCK_ADJUST = "SAFETY_STOCK_ADJUST"
    SUPPLIER_RETURN = "SUPPLIER_RETURN"
    SCRAP = "SCRAP"
    FREEZE_PURCHASE = "FREEZE_PURCHASE"


class ApprovalStatus(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ExecutionStatus(str, Enum):
    DETECTED = "DETECTED"
    ANALYZED = "ANALYZED"
    PROPOSED = "PROPOSED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    VERIFIED = "VERIFIED"
    CLOSED = "CLOSED"


class ForecastVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"


class ForecastVersionType(str, Enum):
    STATISTICAL = "STATISTICAL"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"
    CONSENSUS = "CONSENSUS"


class ECNValidationStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    SPEC_REVIEW = "SPEC_REVIEW"
    TRIAL = "TRIAL"
    QUALITY_APPROVAL = "QUALITY_APPROVAL"
    CUSTOMER_APPROVAL = "CUSTOMER_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ProductLifecycle(str, Enum):
    NPI = "NPI"
    RAMP_UP = "RAMP_UP"
    MATURE = "MATURE"
    DECLINE = "DECLINE"
    EOL = "EOL"
    SERVICE = "SERVICE"


class ABCClass(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class XYZClass(str, Enum):
    X = "X"
    Y = "Y"
    Z = "Z"


class IntermittencyClass(str, Enum):
    SMOOTH = "SMOOTH"
    ERRATIC = "ERRATIC"
    INTERMITTENT = "INTERMITTENT"
    LUMPY = "LUMPY"


class DataQualitySeverity(str, Enum):
    BLOCKING = "BLOCKING"
    WARNING = "WARNING"
    INFO = "INFO"


class ForecastConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT"


class OptimizationStatus(str, Enum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    DETERMINISTIC_FALLBACK = "DETERMINISTIC_FALLBACK"


class WorkflowStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    COMMERCIAL_REVIEW = "COMMERCIAL_REVIEW"
    SUPPLY_REVIEW = "SUPPLY_REVIEW"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EFFECTIVE = "EFFECTIVE"
    MEASURED = "MEASURED"


class TaskStatus(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    COMPLETED = "COMPLETED"
    VERIFIED = "VERIFIED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class TaskPriority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class ImportStatus(str, Enum):
    VALIDATED = "VALIDATED"
    BLOCKED = "BLOCKED"
    IMPORTED = "IMPORTED"


class Evidence(DomainModel):
    source: str
    source_record_id: str | None = None
    field: str | None = None
    value: Any = None
    description: str
    data_version: str | None = None
    observed_at: datetime = Field(default_factory=utc_now)


class DataQualityIssue(DomainModel):
    code: str
    severity: DataQualitySeverity
    message: str
    table: str
    row_index: int | None = None
    field: str | None = None
    value: Any = None
    blocking: bool = False
    impact: str = ""
    evidence: list[Evidence] = Field(default_factory=list)


class DataQualityReport(DomainModel):
    report_id: str
    data_version: str
    checked_at: datetime = Field(default_factory=utc_now)
    issues: list[DataQualityIssue] = Field(default_factory=list)
    tables_checked: list[str] = Field(default_factory=list)
    can_proceed: bool = True
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def derive_gate(self) -> "DataQualityReport":
        self.can_proceed = not any(issue.blocking for issue in self.issues)
        return self


class DemandClassification(DomainModel):
    item_id: str
    abc_class: ABCClass
    xyz_class: XYZClass
    intermittency_class: IntermittencyClass
    lifecycle: ProductLifecycle
    annual_demand: float = Field(ge=0)
    unit_cost: float = Field(ge=0)
    annual_value: float = Field(ge=0)
    cumulative_value_share: float = Field(ge=0, le=1)
    mean_demand: float = Field(ge=0)
    demand_std: float = Field(ge=0)
    cv: float | None = Field(default=None, ge=0)
    adi: float | None = Field(default=None, ge=0)
    cv_squared: float | None = Field(default=None, ge=0)
    recommended_forecast_models: list[str]
    inventory_strategy: str
    requires_manual_review: bool = False
    reason_codes: list[str] = Field(default_factory=list)
    source_version: str
    calculated_at: datetime = Field(default_factory=utc_now)


class ForecastPoint(DomainModel):
    item_id: str
    week_start: date
    horizon_week: int = Field(gt=0, le=52)
    baseline_qty: float = Field(ge=0)
    optimistic_qty: float = Field(ge=0)
    pessimistic_qty: float = Field(ge=0)
    lower_bound: float = Field(ge=0)
    upper_bound: float = Field(ge=0)
    model_name: str
    source_version: str


class ForecastMetrics(DomainModel):
    model_name: str
    wape: float | None = Field(default=None, ge=0)
    bias: float | None = None
    mae: float | None = Field(default=None, ge=0)
    stockout_loss: float = Field(default=0, ge=0)
    excess_loss: float = Field(default=0, ge=0)
    model_score: float | None = Field(default=None, ge=0)
    backtest_count: int = Field(default=0, ge=0)
    data_coverage: float = Field(default=0, ge=0, le=1)
    zero_actual_periods: int = Field(default=0, ge=0)


class ForecastResult(DomainModel):
    item_id: str
    selected_model: str | None = None
    points: list[ForecastPoint] = Field(default_factory=list)
    horizon_totals: dict[int, float] = Field(default_factory=dict)
    candidate_metrics: list[ForecastMetrics] = Field(default_factory=list)
    selected_metrics: ForecastMetrics | None = None
    confidence: ForecastConfidence
    requires_manual_review: bool
    review_reasons: list[str] = Field(default_factory=list)
    data_quality_warnings: list[str] = Field(default_factory=list)
    previous_version_change: float | None = None
    history_source: str
    rules_version: str
    calculated_at: datetime = Field(default_factory=utc_now)


class ForecastAdjustment(DomainModel):
    adjustment_id: str
    item_id: str
    week_start: date
    before_qty: float = Field(ge=0)
    after_qty: float = Field(ge=0)
    reason_code: str
    reason: str
    evidence: list[Evidence] = Field(default_factory=list)
    adjusted_by: str
    approved_by: str | None = None
    effective_from: date
    effective_to: date
    confidence: ForecastConfidence
    created_at: datetime = Field(default_factory=utc_now)


class ForecastVersion(DomainModel):
    version_id: str
    item_id: str
    version_type: ForecastVersionType
    status: ForecastVersionStatus
    created_at: datetime = Field(default_factory=utc_now)
    created_by: str
    approved_by: str | None = None
    source_version_ids: list[str] = Field(default_factory=list)
    points: list[ForecastPoint]
    adjustments: list[ForecastAdjustment] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    effective_from: date
    effective_to: date
    fva: float | None = None
    fva_status: str = "PENDING_ACTUALS"


class BOMRequirement(DomainModel):
    finished_good_id: str
    material_id: str
    demand_week: date
    bom_path: list[str]
    bom_version: str
    base_usage: float = Field(ge=0)
    cumulative_usage: float = Field(ge=0)
    loss_rate: float = Field(ge=0)
    base_quantity: float = Field(ge=0)
    loss_quantity: float = Field(ge=0)
    gross_requirement: float = Field(ge=0)
    unit: str
    conversion_factor: float = Field(gt=0)
    forecast_version_id: str
    source: str
    calculated_at: datetime = Field(default_factory=utc_now)


class InventoryProjection(DomainModel):
    material_id: str
    plant: str
    week_start: date
    beginning_inventory: float
    gross_demand: float = Field(ge=0)
    reserved_demand: float = Field(ge=0)
    safety_stock: float = Field(ge=0)
    po_receipt: float = Field(ge=0)
    production_receipt: float = Field(ge=0)
    transfer_in: float = Field(ge=0)
    transfer_out: float = Field(ge=0)
    ending_inventory: float
    available_to_promise: float
    net_requirement: float = Field(ge=0)
    shortage_qty: float = Field(ge=0)
    below_safety_stock_qty: float = Field(ge=0)
    excess_qty: float = Field(ge=0)
    coverage_weeks: float | None = Field(default=None, ge=0)
    data_version: str
    calculation_basis: str


class WeeklyInventoryInput(DomainModel):
    week_start: date
    gross_demand: float = Field(default=0, ge=0)
    reserved_demand: float = Field(default=0, ge=0)
    safety_stock: float = Field(default=0, ge=0)
    po_receipt: float = Field(default=0, ge=0)
    production_receipt: float = Field(default=0, ge=0)
    transfer_in: float = Field(default=0, ge=0)
    transfer_out: float = Field(default=0, ge=0)


class InventoryProjectionInput(DomainModel):
    material_id: str
    plant: str
    on_hand: float = Field(ge=0)
    frozen: float = Field(default=0, ge=0)
    quality_hold: float = Field(default=0, ge=0)
    allocated: float = Field(default=0, ge=0)
    reusable_return: float = Field(default=0, ge=0)
    weeks: list[WeeklyInventoryInput]
    data_version: str
    source_versions: dict[str, str] = Field(default_factory=dict)


class InventoryProjectionResult(DomainModel):
    material_id: str
    plant: str
    points: list[InventoryProjection]
    first_below_safety_stock_week: date | None = None
    first_shortage_week: date | None = None
    maximum_shortage_qty: float = Field(ge=0)
    maximum_shortage_week: date | None = None
    ending_excess_qty: float = Field(ge=0)
    initial_available_inventory: float
    warnings: list[str] = Field(default_factory=list)
    source_versions: dict[str, str] = Field(default_factory=dict)
    calculated_at: datetime = Field(default_factory=utc_now)


class InventoryPolicyResult(DomainModel):
    material_id: str
    service_level: float = Field(gt=0.5, lt=1)
    z_value: float
    mean_weekly_demand: float = Field(ge=0)
    demand_variance: float = Field(ge=0)
    mean_lead_time_weeks: float = Field(ge=0)
    lead_time_variance: float = Field(ge=0)
    safety_stock: float = Field(ge=0)
    reorder_point: float = Field(ge=0)
    inventory_position: float
    raw_order_quantity: float = Field(ge=0)
    recommended_order_quantity: float = Field(ge=0)
    moq: float = Field(gt=0)
    mpq: float = Field(gt=0)
    package_multiple: float = Field(gt=0)
    lifecycle: ProductLifecycle
    warnings: list[str] = Field(default_factory=list)
    calculation_basis: str
    rules_version: str


class Approval(DomainModel):
    approval_id: str
    action_id: str
    required: bool
    approvers: list[str]
    owner_department: str
    status: ApprovalStatus
    due_date: date
    decided_by: str | None = None
    decided_at: datetime | None = None
    comments: str = ""


class Action(DomainModel):
    action_id: str
    action_type: ActionType
    object_id: str
    material_id: str
    plant: str
    quantity: float = Field(ge=0)
    effective_week: date
    target_week: date | None = None
    source_plant: str | None = None
    target_material_id: str | None = None
    estimated_value: float = Field(default=0, ge=0)
    reason: str
    execution_condition: str
    owner_department: str
    due_date: date
    status: ExecutionStatus = ExecutionStatus.PROPOSED
    parameters: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    approval: Approval | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ActionValidation(DomainModel):
    validation_id: str
    action: Action
    baseline: InventoryProjectionResult
    scenario: InventoryProjectionResult
    shortage_delta: float
    excess_delta: float
    inventory_value_delta: float
    ending_coverage_delta: float | None = None
    creates_new_shortage: bool
    affects_other_entities: bool
    related_entity_results: list[InventoryProjectionResult] = Field(default_factory=list)
    recommended: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    residual_risks: list[str] = Field(default_factory=list)
    approval_required: bool
    calculated_at: datetime = Field(default_factory=utc_now)


class Risk(DomainModel):
    risk_id: str
    risk_type: RiskType
    level: RiskLevel
    material_id: str
    plant: str
    first_event_week: date | None = None
    quantity: float = Field(ge=0)
    value: float = Field(ge=0)
    affected_products: list[str] = Field(default_factory=list)
    affected_customers: list[str] = Field(default_factory=list)
    root_causes: list[str]
    evidence: list[Evidence]
    suggested_actions: list[ActionType]
    owner_department: str
    latest_action_date: date
    source_version: str
    calculated_at: datetime = Field(default_factory=utc_now)


class Scenario(DomainModel):
    scenario_type: ScenarioType
    confidence: float = Field(ge=0, le=1)
    trigger_rules: list[str]
    required_tools: list[str]
    missing_data: list[str]
    requires_human_confirmation: bool
    object_ids: dict[str, str] = Field(default_factory=dict)
    routed_at: datetime = Field(default_factory=utc_now)


class ScenarioReport(DomainModel):
    report_id: str
    scenario: Scenario
    title: str
    executive_summary: str
    evidence: list[Evidence]
    classifications: list[DemandClassification] = Field(default_factory=list)
    forecasts: list[ForecastResult] = Field(default_factory=list)
    bom_requirements: list[BOMRequirement] = Field(default_factory=list)
    inventory_projections: list[InventoryProjectionResult] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)
    validations: list[ActionValidation] = Field(default_factory=list)
    data_quality: DataQualityReport | None = None
    limitations: list[str] = Field(default_factory=list)
    source_versions: dict[str, str]
    generated_at: datetime = Field(default_factory=utc_now)


class ATPDemand(DomainModel):
    demand_id: str
    material_id: str
    customer_id: str
    product_id: str
    plant: str
    need_week: date
    requested_qty: float = Field(gt=0)
    frozen_order: bool = False
    customer_priority: int = Field(default=3, ge=1, le=5)
    shortage_penalty_per_unit: float = Field(default=0, ge=0)
    lifecycle: ProductLifecycle = ProductLifecycle.MATURE
    source_version: str


class ATPAllocation(DomainModel):
    demand_id: str
    material_id: str
    customer_id: str
    product_id: str
    plant: str
    need_week: date
    requested_qty: float = Field(gt=0)
    allocated_qty: float = Field(ge=0)
    unfulfilled_qty: float = Field(ge=0)
    allocation_score: float
    rank: int = Field(gt=0)
    rule_reasons: list[str]


class ATPAllocationResult(DomainModel):
    material_id: str
    available_supply: float = Field(ge=0)
    protected_supply: float = Field(ge=0)
    allocatable_supply: float = Field(ge=0)
    total_requested: float = Field(ge=0)
    total_allocated: float = Field(ge=0)
    total_unfulfilled: float = Field(ge=0)
    allocations: list[ATPAllocation]
    policy: str
    trace: list[str]
    source_versions: dict[str, str]
    rules_version: str = "UNSPECIFIED"
    calculated_at: datetime = Field(default_factory=utc_now)


class TransferSource(DomainModel):
    plant: str
    material_id: str
    on_hand: float = Field(ge=0)
    protected_qty: float = Field(ge=0)
    future_demand: float = Field(ge=0)
    minimum_coverage_qty: float = Field(default=0, ge=0)
    data_version: str


class TransferTarget(DomainModel):
    plant: str
    material_id: str
    shortage_qty: float = Field(gt=0)
    need_date: date
    priority: int = Field(default=3, ge=1, le=5)
    data_version: str


class TransferLane(DomainModel):
    source_plant: str
    target_plant: str
    lead_time_days: int = Field(ge=0)
    unit_cost: float = Field(ge=0)
    fixed_cost: float = Field(default=0, ge=0)
    compatible: bool = True


class TransferRecommendation(DomainModel):
    source_plant: str
    target_plant: str
    material_id: str
    quantity: float = Field(gt=0)
    arrival_date: date
    unit_cost: float = Field(ge=0)
    variable_cost: float = Field(ge=0)
    fixed_cost: float = Field(ge=0)
    total_cost: float = Field(ge=0)
    source_remaining_available: float = Field(ge=0)
    target_remaining_shortage: float = Field(ge=0)
    approval_required: bool = True


class TransferOptimizationResult(DomainModel):
    material_id: str
    status: OptimizationStatus
    recommendations: list[TransferRecommendation]
    total_shortage_before: float = Field(ge=0)
    total_shortage_after: float = Field(ge=0)
    total_transfer_qty: float = Field(ge=0)
    total_cost: float = Field(ge=0)
    infeasible_reasons: list[str]
    solver: str
    trace: list[str]
    source_versions: dict[str, str] = Field(default_factory=dict)
    rules_version: str = "UNSPECIFIED"
    calculated_at: datetime = Field(default_factory=utc_now)


class POOption(DomainModel):
    document_id: str
    material_id: str
    plant: str
    open_qty: float = Field(ge=0)
    cancelable_qty: float = Field(ge=0)
    reschedulable_qty: float = Field(ge=0)
    locked_qty: float = Field(ge=0)
    unit_price: float = Field(ge=0)
    cancellation_penalty_rate: float = Field(ge=0, le=1)
    weeks_until_receipt: int = Field(ge=0)
    cancellation_deadline: date | None = None
    mpq: float = Field(default=1, gt=0)
    data_version: str = "UNSPECIFIED"


class POAdjustment(DomainModel):
    document_id: str
    cancel_qty: float = Field(ge=0)
    delay_qty: float = Field(ge=0)
    penalty_cost: float = Field(ge=0)
    avoided_holding_cost: float = Field(ge=0)
    avoided_obsolescence_cost: float = Field(ge=0)
    net_benefit: float
    approval_required: bool = True


class POOptimizationResult(DomainModel):
    material_id: str
    plant: str
    status: OptimizationStatus
    adjustments: list[POAdjustment]
    excess_before: float = Field(ge=0)
    excess_after: float = Field(ge=0)
    shortage_after: float = Field(ge=0)
    total_penalty_cost: float = Field(ge=0)
    total_avoided_cost: float = Field(ge=0)
    net_benefit: float
    constraints: list[str]
    infeasible_reasons: list[str]
    source_versions: dict[str, str] = Field(default_factory=dict)
    rules_version: str = "UNSPECIFIED"
    calculated_at: datetime = Field(default_factory=utc_now)


class PriceBreak(DomainModel):
    minimum_qty: float = Field(ge=0)
    unit_price: float = Field(ge=0)
    data_version: str = "UNSPECIFIED"


class ProcurementOptimizationResult(DomainModel):
    material_id: str
    status: OptimizationStatus
    required_qty: float = Field(ge=0)
    recommended_order_qty: float = Field(ge=0)
    selected_unit_price: float = Field(ge=0)
    purchase_cost: float = Field(ge=0)
    holding_cost: float = Field(ge=0)
    shortage_cost: float = Field(ge=0)
    fixed_order_cost: float = Field(ge=0)
    total_cost: float = Field(ge=0)
    ending_surplus: float = Field(ge=0)
    ending_shortage: float = Field(ge=0)
    moq: float = Field(gt=0)
    mpq: float = Field(gt=0)
    package_multiple: float = Field(gt=0)
    evaluated_candidates: int = Field(ge=0)
    constraints: list[str]
    explanation: str
    source_versions: dict[str, str] = Field(default_factory=dict)
    rules_version: str = "UNSPECIFIED"


class ECNTransitionRecord(DomainModel):
    from_status: ECNValidationStatus
    to_status: ECNValidationStatus
    actor: str
    role: str
    evidence_keys: list[str]
    comment: str = ""
    transitioned_at: datetime = Field(default_factory=utc_now)


class ECNWorkflow(DomainModel):
    ecn_id: str
    source_material: str
    target_material: str
    affected_products: list[str]
    current_status: ECNValidationStatus
    customer_characteristic: bool = False
    evidence: dict[str, str] = Field(default_factory=dict)
    approvals: dict[str, str] = Field(default_factory=dict)
    effective_batch: str | None = None
    traceability_rule: str | None = None
    history: list[ECNTransitionRecord] = Field(default_factory=list)
    owner_department: str
    due_date: date
    data_version: str


class WeeklySnapshot(DomainModel):
    snapshot_id: str
    as_of_week: date
    entity_type: str
    entity_id: str
    plant: str | None = None
    metrics: dict[str, float]
    source_versions: dict[str, str]
    created_at: datetime = Field(default_factory=utc_now)


class SnapshotTrend(DomainModel):
    entity_id: str
    metric: str
    window_weeks: int = Field(gt=0)
    start_value: float
    end_value: float
    absolute_change: float
    change_rate: float | None = None
    direction: str
    observations: int = Field(ge=0)


class FieldMapping(DomainModel):
    target_field: str
    source_column: str
    required: bool = False
    data_type: str = "str"


class ExcelImportResult(DomainModel):
    file_name: str
    sheet_name: str
    status: ImportStatus
    row_count: int = Field(ge=0)
    mapped_fields: dict[str, str]
    unmapped_required_fields: list[str]
    rows: list[dict[str, Any]] = Field(default_factory=list)
    issues: list[DataQualityIssue] = Field(default_factory=list)
    data_version: str
    imported_at: datetime = Field(default_factory=utc_now)


class ForecastAdjustmentWorkflow(DomainModel):
    workflow_id: str
    item_id: str
    base_version_id: str
    adjusted_version_id: str | None = None
    status: WorkflowStatus
    requested_by: str
    commercial_reviewer: str | None = None
    supply_reviewer: str | None = None
    approver: str | None = None
    reason_code: str
    evidence: list[Evidence]
    effective_from: date
    effective_to: date
    due_date: date
    history: list[dict[str, Any]] = Field(default_factory=list)
    fva: float | None = None
    fva_error_before: float | None = Field(default=None, ge=0)
    fva_error_after: float | None = Field(default=None, ge=0)
    fva_status: str = "PENDING_ACTUALS"
    source_versions: dict[str, str] = Field(default_factory=dict)


class RiskTask(DomainModel):
    task_id: str
    risk_id: str
    title: str
    priority: TaskPriority
    status: TaskStatus
    owner_department: str
    assignee: str
    approvers: list[str]
    due_date: date
    created_at: datetime = Field(default_factory=utc_now)
    acknowledged_at: datetime | None = None
    completed_at: datetime | None = None
    escalation_level: int = Field(default=0, ge=0)
    escalated_to: list[str] = Field(default_factory=list)
    reminder_count: int = Field(default=0, ge=0)
    evidence: list[Evidence] = Field(default_factory=list)


class TaskNotification(DomainModel):
    notification_id: str
    task_id: str
    notification_type: str
    recipient: str
    message: str
    generated_at: datetime = Field(default_factory=utc_now)


class SupplierDeliveryRecord(DomainModel):
    supplier_id: str
    document_id: str
    promised_date: date
    confirmed_date: date | None = None
    actual_date: date
    ordered_qty: float = Field(gt=0)
    received_qty: float = Field(ge=0)
    order_date: date
    data_version: str


class SupplierReliabilityResult(DomainModel):
    supplier_id: str
    sample_count: int = Field(ge=0)
    on_time_rate: float = Field(ge=0, le=1)
    quantity_fill_rate: float = Field(ge=0, le=1)
    confirmation_adherence: float = Field(ge=0, le=1)
    mean_lead_time_days: float = Field(ge=0)
    lead_time_variance: float = Field(ge=0)
    mean_lateness_days: float
    lead_time_stability_score: float = Field(ge=0, le=1)
    reliability_score: float = Field(ge=0, le=1)
    grade: str
    warnings: list[str]
    source_versions: list[str]
    rules_version: str = "UNSPECIFIED"
    calculated_at: datetime = Field(default_factory=utc_now)


class DemandScenario(DomainModel):
    scenario_id: str
    probability: float = Field(gt=0, le=1)
    demand_multiplier: float = Field(ge=0)
    po_delay_weeks: int = Field(default=0, ge=0)
    description: str


class InventoryDecision(DomainModel):
    decision_id: str
    order_qty: float = Field(default=0, ge=0)
    order_week: date | None = None
    cancel_qty: float = Field(default=0, ge=0)
    cancel_from_week: date | None = None
    transfer_in_qty: float = Field(default=0, ge=0)
    transfer_week: date | None = None
    action_cost: float = Field(default=0, ge=0)


class ScenarioCostEvaluation(DomainModel):
    decision_id: str
    scenario_id: str
    probability: float = Field(gt=0, le=1)
    holding_cost: float = Field(ge=0)
    shortage_cost: float = Field(ge=0)
    excess_cost: float = Field(ge=0)
    action_cost: float = Field(ge=0)
    total_cost: float = Field(ge=0)
    maximum_shortage: float = Field(ge=0)
    ending_excess: float = Field(ge=0)
    feasible: bool


class MultiScenarioOptimizationResult(DomainModel):
    material_id: str
    selected_decision_id: str | None = None
    status: OptimizationStatus
    expected_cost_by_decision: dict[str, float]
    evaluations: list[ScenarioCostEvaluation]
    robust_feasible_decisions: list[str]
    infeasible_reasons: list[str]
    calculation_basis: str
    source_versions: dict[str, str] = Field(default_factory=dict)
    rules_version: str = "UNSPECIFIED"
    calculated_at: datetime = Field(default_factory=utc_now)


class ManagementDashboard(DomainModel):
    as_of: datetime = Field(default_factory=utc_now)
    data_quality_blockers: int = Field(ge=0)
    forecast_items: int = Field(ge=0)
    forecast_review_rate: float = Field(ge=0, le=1)
    average_wape: float | None = Field(default=None, ge=0)
    shortage_risk_count: int = Field(ge=0)
    excess_risk_count: int = Field(ge=0)
    shortage_value: float = Field(ge=0)
    excess_value: float = Field(ge=0)
    open_task_count: int = Field(ge=0)
    overdue_task_count: int = Field(ge=0)
    pending_approval_count: int = Field(ge=0)
    supplier_grade_distribution: dict[str, int]
    top_risks: list[dict[str, Any]]
    source_versions: dict[str, str]


class ControlTowerStatus(str, Enum):
    """Shared presentation status with one semantic color system."""

    HEALTHY = "HEALTHY"
    WATCH = "WATCH"
    RISK = "RISK"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class ControlTowerKPI(DomainModel):
    key: str
    label: str
    value: float
    display_value: str
    detail: str
    status: ControlTowerStatus = ControlTowerStatus.HEALTHY
    drilldown_page: str | None = None


class DemandTrendPoint(DomainModel):
    item_id: str
    week_start: date
    actual_qty: float | None = Field(default=None, ge=0)
    forecast_qty: float | None = Field(default=None, ge=0)
    lower_bound: float | None = Field(default=None, ge=0)
    upper_bound: float | None = Field(default=None, ge=0)
    period_type: str
    source_version: str


class InventoryRiskCell(DomainModel):
    material_id: str
    plant: str
    week_start: date
    ending_inventory: float
    safety_stock: float = Field(ge=0)
    gross_demand: float = Field(ge=0)
    incoming_supply: float = Field(ge=0)
    shortage_qty: float = Field(ge=0)
    excess_qty: float = Field(ge=0)
    coverage_weeks: float | None = Field(default=None, ge=0)
    status: ControlTowerStatus
    status_reason: str
    source_version: str


class RiskQueueItem(DomainModel):
    risk_id: str
    priority: RiskLevel
    material_id: str
    plant: str
    issue: str
    impact_quantity: float = Field(ge=0)
    impact_value: float = Field(ge=0)
    risk_date: date | None = None
    root_cause: str
    recommended_action: ActionType
    owner_department: str
    latest_action_date: date
    source_version: str


class InsightCard(DomainModel):
    insight_id: str
    status: ControlTowerStatus
    title: str
    what_happened: str
    why: str
    recommendation: str
    drilldown_page: str
    object_id: str


class CopilotEvidenceItem(DomainModel):
    label: str
    value: str
    source: str
    source_version: str


class StructuredCopilotResponse(DomainModel):
    question: str
    summary: str
    risk_level: RiskLevel
    evidence: list[CopilotEvidenceItem]
    root_causes: list[str]
    recommendations: list[str]
    expected_impact: list[str]
    business_rules: list[str]
    action_validation_id: str | None = None
    limitations: list[str] = Field(default_factory=list)
    source_versions: dict[str, str]
    generated_at: datetime = Field(default_factory=utc_now)


class ControlTowerSnapshot(DomainModel):
    """Read-only aggregate used by Streamlit and the overview API."""

    as_of: datetime = Field(default_factory=utc_now)
    selected_product_id: str
    selected_material_id: str
    kpis: list[ControlTowerKPI]
    demand_trend: list[DemandTrendPoint]
    inventory_heatmap: list[InventoryRiskCell]
    projections: list[InventoryProjectionResult]
    risks: list[Risk]
    risk_queue: list[RiskQueueItem]
    insights: list[InsightCard]
    action_validations: list[ActionValidation]
    suppliers: list[SupplierReliabilityResult]
    structured_response: StructuredCopilotResponse
    data_quality: DataQualityReport
    legacy_data_quality: DataQualityReport | None = None
    limitations: list[str]
    source_versions: dict[str, str]
