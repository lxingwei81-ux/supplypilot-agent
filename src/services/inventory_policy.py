from __future__ import annotations

from math import ceil, sqrt
from statistics import NormalDist

from ..config import RulesConfig, load_rules
from ..models import ABCClass, InventoryPolicyResult, ProductLifecycle, XYZClass


def _round_lot(quantity: float, moq: float, mpq: float, package_multiple: float) -> float:
    if quantity <= 0:
        return 0.0
    rounded = max(quantity, moq)
    multiple = max(mpq, package_multiple)
    return ceil(rounded / multiple) * multiple


def calculate_inventory_policy(
    material_id: str,
    *,
    mean_weekly_demand: float,
    demand_variance: float,
    mean_lead_time_weeks: float,
    lead_time_variance: float | None,
    on_hand: float,
    on_order: float = 0,
    allocated: float = 0,
    abc_class: ABCClass | str = ABCClass.B,
    xyz_class: XYZClass | str = XYZClass.Y,
    lifecycle: ProductLifecycle | str = ProductLifecycle.MATURE,
    critical: bool = False,
    service_level: float | None = None,
    moq: float | None = None,
    mpq: float | None = None,
    package_multiple: float | None = None,
    target_inventory: float | None = None,
    rules: RulesConfig | None = None,
) -> InventoryPolicyResult:
    cfg = rules or load_rules()
    abc = abc_class if isinstance(abc_class, ABCClass) else ABCClass(str(abc_class))
    xyz = xyz_class if isinstance(xyz_class, XYZClass) else XYZClass(str(xyz_class))
    lifecycle_value = lifecycle if isinstance(lifecycle, ProductLifecycle) else ProductLifecycle(str(lifecycle).upper().replace("-", "_"))
    warnings: list[str] = []
    if lead_time_variance is None:
        lead_time_variance = cfg.inventory.default_lead_time_variance
        warnings.append("交期方差缺失，使用rules.yaml显式默认值")
    key = "critical" if critical else f"{abc.value}_{xyz.value}"
    selected_service = service_level if service_level is not None else cfg.inventory.service_levels.get(key, cfg.inventory.service_levels["default"])
    if service_level is None:
        warnings.append(f"服务水平未提供，使用配置 {key}={selected_service:.2%}")
    z_value = NormalDist().inv_cdf(selected_service)
    safety_stock = z_value * sqrt(
        max(0.0, mean_lead_time_weeks * demand_variance + mean_weekly_demand ** 2 * lead_time_variance)
    )
    reorder_point = max(0.0, mean_weekly_demand * mean_lead_time_weeks + safety_stock)
    inventory_position = on_hand + on_order - allocated
    target = target_inventory if target_inventory is not None else reorder_point
    raw_order = max(0.0, target - inventory_position)
    lot = cfg.inventory.lot_sizing
    selected_moq = moq if moq is not None else lot.default_moq
    selected_mpq = mpq if mpq is not None else lot.default_mpq
    selected_package = package_multiple if package_multiple is not None else lot.default_package_multiple
    recommended = _round_lot(raw_order, selected_moq, selected_mpq, selected_package)
    if lifecycle_value == ProductLifecycle.EOL and not cfg.inventory.eol_new_replenishment_allowed:
        recommended = 0.0
        warnings.append("EOL规则限制新增补货；需人工确认售后需求后审批")
    return InventoryPolicyResult(
        material_id=material_id,
        service_level=selected_service,
        z_value=z_value,
        mean_weekly_demand=max(0.0, mean_weekly_demand),
        demand_variance=max(0.0, demand_variance),
        mean_lead_time_weeks=max(0.0, mean_lead_time_weeks),
        lead_time_variance=max(0.0, lead_time_variance),
        safety_stock=safety_stock,
        reorder_point=reorder_point,
        inventory_position=inventory_position,
        raw_order_quantity=raw_order,
        recommended_order_quantity=recommended,
        moq=selected_moq,
        mpq=selected_mpq,
        package_multiple=selected_package,
        lifecycle=lifecycle_value,
        warnings=warnings,
        calculation_basis="SS=z*sqrt(MeanLT*DemandVariance+MeanDemand^2*LeadTimeVariance); ROP=MeanDemand*MeanLT+SS",
        rules_version=cfg.metadata.version,
    )
