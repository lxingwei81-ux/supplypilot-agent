from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import RulesConfig, load_rules
from .models import Scenario, ScenarioType


@dataclass(frozen=True)
class RouteDefinition:
    keywords: tuple[str, ...]
    tools: tuple[str, ...]
    required_data: tuple[str, ...]
    human_confirmation: bool = False


ROUTES: dict[ScenarioType, RouteDefinition] = {
    ScenarioType.DATA_QUALITY: RouteDefinition(("数据质量", "缺字段", "重复", "格式错误"), ("run_data_quality_v2",), ("source_tables",)),
    ScenarioType.DEMAND_INCREASE: RouteDefinition(("需求上升", "需求增加", "突增", "增量"), ("forecast_demand_v2", "explode_bom_demand_v2", "project_inventory_by_week_v2"), ("historical_demand", "bom", "inventory", "supply"), True),
    ScenarioType.DEMAND_DECREASE: RouteDefinition(("需求下降", "需求减少", "突降", "取消需求"), ("forecast_demand_v2", "explode_bom_demand_v2", "get_excess_portfolio", "validate_action_impact_v2"), ("historical_demand", "bom", "inventory", "supply"), True),
    ScenarioType.FORECAST_VERSION_CHANGE: RouteDefinition(("预测版本", "forecast版本", "版本变化"), ("compare_forecast_versions_v2",), ("forecast_versions",)),
    ScenarioType.FORECAST_MANUAL_ADJUSTMENT: RouteDefinition(("人工调整", "调整预测", "共识预测", "fva"), ("create_forecast_adjustment_v2",), ("forecast_versions", "adjustment_evidence"), True),
    ScenarioType.SUPPLY_DELAY: RouteDefinition(("供应延期", "供应商延期", "交期延长"), ("project_inventory_by_week_v2", "validate_action_impact_v2"), ("inventory", "weekly_demand", "po_schedule"), True),
    ScenarioType.STATIC_SHORTAGE: RouteDefinition(("静态缺料", "总量缺料"), ("calculate_shortage_v2",), ("inventory", "total_demand", "total_supply")),
    ScenarioType.DYNAMIC_SHORTAGE: RouteDefinition(("动态缺料", "中间周缺料", "首次缺料周", "逐周缺料"), ("project_inventory_by_week_v2",), ("inventory", "weekly_demand", "weekly_supply")),
    ScenarioType.BELOW_SAFETY_STOCK: RouteDefinition(("低于安全库存", "安全库存不足"), ("project_inventory_by_week_v2", "calculate_inventory_policy_v2"), ("inventory", "weekly_demand", "safety_stock")),
    ScenarioType.INVENTORY_EXCESS: RouteDefinition(("库存冗余", "库存过剩", "超储"), ("get_excess_portfolio", "project_inventory_by_week_v2", "validate_action_impact_v2"), ("inventory", "weekly_demand", "weekly_supply"), True),
    ScenarioType.OBSOLETE_INVENTORY: RouteDefinition(("呆滞库存", "库龄", "报废"), ("get_excess_action_plan",), ("inventory_age", "lifecycle", "future_demand"), True),
    ScenarioType.NO_DEMAND_OPEN_PO: RouteDefinition(("无需求有po", "无需求但有在途", "无需求但有po"), ("get_po_cancellation_alerts", "validate_action_impact_v2"), ("weekly_demand", "po_schedule"), True),
    ScenarioType.EOL_INVENTORY: RouteDefinition(("eol库存", "停产库存", "eom库存"), ("get_excess_portfolio", "get_excess_action_plan"), ("lifecycle", "inventory", "future_demand"), True),
    ScenarioType.PO_EXPEDITE: RouteDefinition(("po提前", "提前po", "催交"), ("validate_action_impact_v2",), ("po_schedule", "weekly_projection"), True),
    ScenarioType.PO_DELAY: RouteDefinition(("po延期", "延期po"), ("validate_action_impact_v2",), ("po_schedule", "weekly_projection"), True),
    ScenarioType.PO_REDUCTION: RouteDefinition(("po减量", "减量po"), ("get_po_cancellation_alerts", "validate_action_impact_v2"), ("po_schedule", "weekly_projection"), True),
    ScenarioType.PO_CANCELLATION: RouteDefinition(("po取消", "取消po"), ("get_po_cancellation_alerts", "validate_action_impact_v2"), ("po_schedule", "weekly_projection"), True),
    ScenarioType.CROSS_PLANT_TRANSFER: RouteDefinition(("跨仓调拨", "跨厂调拨", "调拨"), ("get_transfer_opportunities", "validate_action_impact_v2"), ("source_projection", "target_projection", "inventory_status"), True),
    ScenarioType.SUBSTITUTE_MATERIAL: RouteDefinition(("替代料", "替代物料"), ("validate_action_impact_v2",), ("source_projection", "substitute_projection", "compatibility_status"), True),
    ScenarioType.ECN_SWITCH: RouteDefinition(("ecn", "工程变更", "切换消耗"), ("get_ecn_switch_candidates", "validate_action_impact_v2"), ("ecn_status", "source_projection", "target_projection"), True),
    ScenarioType.WHAT_IF_SIMULATION: RouteDefinition(("情景模拟", "what-if", "如果", "模拟"), ("validate_action_impact_v2",), ("baseline_projection", "scenario_inputs"), True),
    ScenarioType.PRODUCT_SUPPLY_RISK: RouteDefinition(("供给风险", "产品风险", "齐套风险"), ("diagnose_product_risk", "project_inventory_by_week_v2"), ("bom", "inventory", "weekly_demand", "weekly_supply"), True),
    ScenarioType.LONG_LT_SHORTAGE: RouteDefinition(("长lt", "长提前期", "长交期缺料"), ("diagnose_product_risk", "project_inventory_by_week_v2"), ("lead_time", "weekly_projection"), True),
    ScenarioType.PO_LATE: RouteDefinition(("po晚到", "晚到po"), ("list_exceptions", "project_inventory_by_week_v2"), ("po_schedule", "weekly_demand"), True),
    ScenarioType.PR_NOT_CONVERTED: RouteDefinition(("pr未转po", "采购申请未下单"), ("build_procurement_action_list",), ("procurement", "net_requirement"), True),
    ScenarioType.SHARED_MATERIAL_COMPETITION: RouteDefinition(("共用料竞争", "atp分配"), ("get_material_commonality",), ("product_priorities", "shared_demand", "available_supply"), True),
    ScenarioType.COMMON_MATERIAL_CONSUMPTION: RouteDefinition(("共用消耗", "自然消耗"), ("get_material_commonality", "get_excess_action_plan"), ("shared_models", "future_demand"), True),
    ScenarioType.SUPPLIER_RETURN: RouteDefinition(("供应商退换", "供应商返工", "退供应商"), ("get_excess_action_plan",), ("supplier_terms", "inventory_status"), True),
    ScenarioType.STRANDED_INVENTORY: RouteDefinition(("残余呆滞", "计提", "mrb"), ("get_excess_action_plan",), ("residual_inventory", "future_demand"), True),
}


def _facts_route(facts: dict[str, Any], rules: RulesConfig) -> tuple[ScenarioType, list[str]] | None:
    if facts.get("blocking_data_quality"):
        return ScenarioType.DATA_QUALITY, ["blocking_data_quality=true"]
    change = float(facts.get("demand_change", 0) or 0)
    rate = float(facts.get("demand_change_rate", 0) or 0)
    if change >= rules.demand_change.absolute_threshold or rate >= rules.demand_change.increase_rate:
        return ScenarioType.DEMAND_INCREASE, ["demand_change threshold"]
    if change <= -rules.demand_change.absolute_threshold or rate <= rules.demand_change.decrease_rate:
        return ScenarioType.DEMAND_DECREASE, ["demand_decrease threshold"]
    if facts.get("forecast_manual_adjustment"):
        return ScenarioType.FORECAST_MANUAL_ADJUSTMENT, ["manual adjustment present"]
    if facts.get("forecast_version_change"):
        return ScenarioType.FORECAST_VERSION_CHANGE, ["forecast version changed"]
    if facts.get("supplier_delay"):
        return ScenarioType.SUPPLY_DELAY, ["supplier_delay=true"]
    if float(facts.get("projected_inventory", 0) or 0) < 0:
        return ScenarioType.DYNAMIC_SHORTAGE, ["projected_inventory<0"]
    if float(facts.get("projected_inventory", 0) or 0) < float(facts.get("safety_stock", 0) or 0):
        return ScenarioType.BELOW_SAFETY_STOCK, ["projected_inventory<safety_stock"]
    if facts.get("no_demand") and float(facts.get("open_po", 0) or 0) > 0:
        return ScenarioType.NO_DEMAND_OPEN_PO, ["no demand and open PO"]
    if float(facts.get("excess_qty", 0) or 0) > 0:
        return ScenarioType.INVENTORY_EXCESS, ["excess_qty>0"]
    return None


def route_scenario(
    query: str,
    *,
    facts: dict[str, Any] | None = None,
    available_data: set[str] | None = None,
    rules: RulesConfig | None = None,
) -> Scenario:
    cfg = rules or load_rules()
    fact_values = facts or {}
    data = available_data or set()
    selected = _facts_route(fact_values, cfg)
    trigger_rules: list[str]
    confidence: float
    if selected:
        scenario_type, trigger_rules = selected
        confidence = 0.98
    else:
        normalized = query.lower().replace(" ", "")
        matches: list[tuple[int, ScenarioType, str]] = []
        for scenario_type, definition in ROUTES.items():
            for keyword in definition.keywords:
                if keyword.lower().replace(" ", "") in normalized:
                    matches.append((len(keyword), scenario_type, keyword))
        if matches:
            _, scenario_type, keyword = max(matches, key=lambda item: (item[0], item[1].value))
            trigger_rules = [f"keyword:{keyword}"]
            confidence = 0.85
        else:
            scenario_type = ScenarioType.PRODUCT_SUPPLY_RISK
            trigger_rules = ["fallback:generic supply-risk diagnosis"]
            confidence = 0.45
    definition = ROUTES[scenario_type]
    missing = sorted(set(definition.required_data) - data)
    return Scenario(
        scenario_type=scenario_type,
        confidence=confidence,
        trigger_rules=trigger_rules,
        required_tools=list(definition.tools),
        missing_data=missing,
        requires_human_confirmation=definition.human_confirmation or bool(missing) or confidence < 0.7,
        object_ids={str(key): str(value) for key, value in fact_values.get("object_ids", {}).items()},
    )

