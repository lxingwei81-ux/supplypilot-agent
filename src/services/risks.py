from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..config import RulesConfig, load_rules
from ..models import (
    ActionType,
    Evidence,
    InventoryProjectionResult,
    ProductLifecycle,
    Risk,
    RiskLevel,
    RiskType,
)


def _shortage_level(quantity: float, weeks_to_event: int, rules: RulesConfig) -> RiskLevel:
    cfg = rules.risk.shortage
    if quantity >= cfg.critical_qty or weeks_to_event <= cfg.critical_weeks_to_event:
        return RiskLevel.CRITICAL
    if quantity >= cfg.high_qty or weeks_to_event <= cfg.high_weeks_to_event:
        return RiskLevel.HIGH
    if quantity >= cfg.medium_qty:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _excess_level(value: float, rules: RulesConfig) -> RiskLevel:
    cfg = rules.risk.excess
    if value >= cfg.critical_value:
        return RiskLevel.CRITICAL
    if value >= cfg.high_value:
        return RiskLevel.HIGH
    if value >= cfg.medium_value:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def identify_projection_risks(
    projection: InventoryProjectionResult,
    *,
    unit_cost: float,
    affected_products: list[str] | None = None,
    affected_customers: list[str] | None = None,
    context: dict[str, Any] | None = None,
    rules: RulesConfig | None = None,
) -> list[Risk]:
    cfg = rules or load_rules()
    ctx = context or {}
    products = affected_products or []
    customers = affected_customers or []
    risks: list[Risk] = []
    start_week = projection.points[0].week_start
    if projection.first_shortage_week or projection.first_below_safety_stock_week:
        event_week = projection.first_shortage_week or projection.first_below_safety_stock_week
        assert event_week is not None
        shortage_quantity = projection.maximum_shortage_qty
        if shortage_quantity > 0:
            risk_type = RiskType.SHORTAGE
            quantity = shortage_quantity
        else:
            risk_type = RiskType.BELOW_SAFETY_STOCK
            quantity = max(point.below_safety_stock_qty for point in projection.points)
        roots: list[str] = []
        if ctx.get("po_late"):
            roots.append("PO晚于需求日期")
        if float(ctx.get("demand_change_rate", 0)) >= cfg.demand_change.increase_rate:
            roots.append("需求显著上升")
        if ctx.get("supplier_delay"):
            roots.append("供应商交期延误")
        if ctx.get("quality_hold"):
            roots.append("质量冻结降低可用库存")
        if ctx.get("substitute_shortage"):
            roots.append("替代料不足")
        if ctx.get("single_source"):
            roots.append("单一供应商异常")
        if not roots:
            roots.append("逐周有效供给不足")
        weeks_to_event = max(0, (event_week - start_week).days // 7)
        latest_date = event_week - timedelta(days=max(1, int(ctx.get("lead_time_days", 7))))
        risks.append(Risk(
            risk_id=f"RISK-SHORT-{projection.material_id}-{projection.plant}-{event_week.isoformat()}",
            risk_type=risk_type,
            level=_shortage_level(quantity, weeks_to_event, cfg),
            material_id=projection.material_id,
            plant=projection.plant,
            first_event_week=event_week,
            quantity=quantity,
            value=quantity * max(0.0, unit_cost),
            affected_products=products,
            affected_customers=customers,
            root_causes=roots,
            evidence=[Evidence(
                source="weekly_inventory_projection",
                source_record_id=projection.material_id,
                field="maximum_shortage_qty",
                value=quantity,
                description=f"首次风险周 {event_week}，最大缺口 {quantity:.2f}",
                data_version=projection.points[0].data_version,
            )],
            suggested_actions=[ActionType.EXPEDITE_PO, ActionType.TRANSFER, ActionType.SUBSTITUTE],
            owner_department="计划/采购",
            latest_action_date=latest_date,
            source_version=projection.points[0].data_version,
        ))

    ending = projection.points[-1]
    no_future_demand = all(point.gross_demand + point.reserved_demand == 0 for point in projection.points)
    lifecycle_raw = ctx.get("lifecycle", ProductLifecycle.MATURE)
    lifecycle = lifecycle_raw if isinstance(lifecycle_raw, ProductLifecycle) else ProductLifecycle(str(lifecycle_raw).upper().replace("-", "_"))
    coverage_trigger = ending.coverage_weeks is not None and ending.coverage_weeks > cfg.inventory.coverage_weeks.excess_13w_above
    excess_conditions = [
        coverage_trigger,
        bool(ctx.get("forecast_down_consecutive")),
        lifecycle == ProductLifecycle.EOL,
        bool(ctx.get("customer_cancelled")),
        no_future_demand and float(ctx.get("open_po", 0)) > 0,
        bool(ctx.get("po_not_produced_demand_down")),
        int(ctx.get("age_days", 0)) >= cfg.risk.aging.warning_days,
        bool(ctx.get("ecn_soon")),
        bool(ctx.get("single_product_material")),
    ]
    if ending.excess_qty > 0 and any(excess_conditions):
        roots = []
        if coverage_trigger:
            roots.append("覆盖周数超过配置阈值")
        if ctx.get("forecast_down_consecutive"):
            roots.append("预测连续下调")
        if lifecycle == ProductLifecycle.EOL:
            roots.append("产品进入EOL")
        if ctx.get("customer_cancelled"):
            roots.append("客户取消订单")
        if no_future_demand and float(ctx.get("open_po", 0)) > 0:
            roots.append("无未来需求但仍有在途PO")
        if ctx.get("po_not_produced_demand_down"):
            roots.append("PO尚未生产且需求已下降")
        if int(ctx.get("age_days", 0)) >= cfg.risk.aging.warning_days:
            roots.append("库存库龄超过预警阈值")
        if ctx.get("ecn_soon"):
            roots.append("ECN即将生效")
        if ctx.get("single_product_material"):
            roots.append("物料仅服务单一成品")
        value = ending.excess_qty * max(0.0, unit_cost)
        risks.append(Risk(
            risk_id=f"RISK-EXCESS-{projection.material_id}-{projection.plant}-{ending.week_start.isoformat()}",
            risk_type=RiskType.OBSOLETE if lifecycle == ProductLifecycle.EOL else RiskType.EXCESS,
            level=_excess_level(value, cfg),
            material_id=projection.material_id,
            plant=projection.plant,
            first_event_week=ending.week_start,
            quantity=ending.excess_qty,
            value=value,
            affected_products=products,
            affected_customers=customers,
            root_causes=roots or ["投影供给超过需求与安全库存"],
            evidence=[Evidence(
                source="weekly_inventory_projection",
                source_record_id=projection.material_id,
                field="ending_excess_qty",
                value=ending.excess_qty,
                description=f"期末冗余 {ending.excess_qty:.2f}，金额 {value:.2f}",
                data_version=ending.data_version,
            )],
            suggested_actions=[ActionType.FREEZE_PURCHASE, ActionType.CANCEL_PO, ActionType.TRANSFER, ActionType.ECN_SWITCH],
            owner_department="计划/采购",
            latest_action_date=start_week + timedelta(days=cfg.procurement.cancellation_window_days),
            source_version=ending.data_version,
        ))
    return risks
