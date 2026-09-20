from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ..config import load_rules
from ..demo import (
    demo_histories,
    demo_planning_parameters,
    demo_projection,
    demo_supplier_assignments,
    demo_supplier_records,
)
from ..models import (
    Action,
    ActionType,
    ActionValidation,
    ControlTowerKPI,
    ControlTowerSnapshot,
    ControlTowerStatus,
    CopilotEvidenceItem,
    DataQualityReport,
    DemandTrendPoint,
    InsightCard,
    InventoryProjectionResult,
    InventoryRiskCell,
    Risk,
    RiskLevel,
    RiskQueueItem,
    RiskType,
    StructuredCopilotResponse,
    SupplierReliabilityResult,
)
from ..repository import load_table
from .action_validation import validate_action_impact
from .dashboard import build_management_dashboard
from .data_quality import assess_project_data, validate_data_quality
from .demand_classification import classify_demand
from .forecasting import generate_forecast
from .inventory_projection import project_inventory_by_week
from .risks import identify_projection_risks
from .supplier_reliability import calculate_supplier_reliability
from .task_management import RiskTaskService


PRODUCT_TO_MATERIAL = {
    "PRODUCT_A": "MAT-A",
    "PRODUCT_B": "MAT-B",
}

CASE_DEFINITIONS = (
    (
        "CASE1",
        "MAT-A",
        "DEMO_PLANT",
        {"forecast_down_consecutive": True, "open_po": 16000},
    ),
    (
        "CASE2",
        "MAT-B",
        "TARGET_PLANT",
        {"supplier_delay": True, "demand_change_rate": 0.18, "lead_time_days": 36},
    ),
    (
        "CASE3",
        "MAT-C",
        "DEMO_PLANT",
        {"po_late": True},
    ),
)


def _demo_data_quality() -> DataQualityReport:
    """Validate only the versioned inputs consumed by this control-tower view."""

    return validate_data_quality(
        {
            "historical_demand": load_table("demo_historical_demand"),
            "inventory": load_table("demo_weekly_inventory"),
            "bom": load_table("demo_bom_extended"),
            "products": load_table("demo_item_planning"),
            "supplier_assignments": demo_supplier_assignments(),
        },
        data_version="DEMO-CT-V1",
        required_tables=["historical_demand", "inventory", "bom", "supplier_assignments"],
    )


def _supplier_for_material(
    material_id: str,
    suppliers: list[SupplierReliabilityResult],
    *,
    as_of_date: date,
) -> tuple[SupplierReliabilityResult, str]:
    assignments = demo_supplier_assignments()
    assignment = next(
        row
        for row in assignments
        if str(row["material_id"]) == material_id
        and date.fromisoformat(str(row["valid_from"])) <= as_of_date <= date.fromisoformat(str(row["valid_to"]))
    )
    supplier = next(row for row in suppliers if row.supplier_id == str(assignment["supplier_id"]))
    return supplier, str(assignment["data_version"])


def _forecast_all():
    histories, metadata = demo_histories()
    results = {}
    for item_id, history in histories.items():
        meta = metadata[item_id]
        classification = classify_demand(
            {item_id: history},
            unit_costs={item_id: float(meta["unit_cost"])},
            lifecycles={item_id: str(meta["lifecycle"])},
            source_version=str(meta["data_version"]),
        )[0]
        results[item_id] = generate_forecast(
            item_id,
            history,
            classification,
            last_history_week=date.fromisoformat(str(meta["last_history_week"])),
            history_source=str(meta["data_version"]),
            stockout_unit_cost=float(meta["unit_cost"]),
        )
    return histories, metadata, results


def _demand_trend(
    item_id: str,
    histories: dict[str, list[float]],
    metadata: dict[str, dict[str, object]],
    forecasts: dict[str, object],
) -> list[DemandTrendPoint]:
    history = histories[item_id]
    meta = metadata[item_id]
    last_week = date.fromisoformat(str(meta["last_history_week"]))
    source_version = str(meta["data_version"])
    points: list[DemandTrendPoint] = []
    visible_history = history[-16:]
    first_week = last_week - timedelta(weeks=len(visible_history) - 1)
    for index, quantity in enumerate(visible_history):
        points.append(DemandTrendPoint(
            item_id=item_id,
            week_start=first_week + timedelta(weeks=index),
            actual_qty=quantity,
            period_type="HISTORY",
            source_version=source_version,
        ))
    result = forecasts[item_id]
    for point in result.points:
        points.append(DemandTrendPoint(
            item_id=item_id,
            week_start=point.week_start,
            forecast_qty=point.baseline_qty,
            lower_bound=point.lower_bound,
            upper_bound=point.upper_bound,
            period_type="FORECAST",
            source_version=point.source_version,
        ))
    return points


def _risk_cell(
    projection: InventoryProjectionResult,
    *,
    unit_cost: float,
    forecast_down: bool,
) -> list[InventoryRiskCell]:
    rules = load_rules()
    cells: list[InventoryRiskCell] = []
    for point in projection.points:
        incoming = point.po_receipt + point.production_receipt + point.transfer_in
        excess_value = point.excess_qty * unit_cost
        if point.ending_inventory < 0:
            status = ControlTowerStatus.CRITICAL
            reason = f"投影库存为 {point.ending_inventory:,.0f}，发生缺料"
        elif point.ending_inventory < point.safety_stock:
            status = ControlTowerStatus.RISK
            reason = f"投影库存低于安全库存 {point.safety_stock:,.0f}"
        elif point.ending_inventory < point.safety_stock * rules.control_tower.inventory_watch_buffer_multiplier:
            status = ControlTowerStatus.WATCH
            reason = "安全库存缓冲偏低"
        elif forecast_down and excess_value >= rules.risk.excess.critical_value:
            status = ControlTowerStatus.CRITICAL
            reason = f"预测下调且决策冗余金额为 ¥{excess_value:,.0f}"
        elif forecast_down and excess_value >= rules.risk.excess.high_value:
            status = ControlTowerStatus.RISK
            reason = f"预测下调且决策冗余金额为 ¥{excess_value:,.0f}"
        elif forecast_down and excess_value >= rules.risk.excess.medium_value:
            status = ControlTowerStatus.WATCH
            reason = f"预测下调且决策冗余金额为 ¥{excess_value:,.0f}"
        else:
            status = ControlTowerStatus.HEALTHY
            reason = "投影库存高于安全库存且未触发冗余规则"
        cells.append(InventoryRiskCell(
            material_id=projection.material_id,
            plant=projection.plant,
            week_start=point.week_start,
            ending_inventory=point.ending_inventory,
            safety_stock=point.safety_stock,
            gross_demand=point.gross_demand + point.reserved_demand,
            incoming_supply=incoming,
            shortage_qty=point.shortage_qty,
            excess_qty=point.excess_qty,
            coverage_weeks=point.coverage_weeks,
            status=status,
            status_reason=reason,
            source_version=point.data_version,
        ))
    return cells


def _risk_queue(risks: list[Risk]) -> list[RiskQueueItem]:
    type_label = {
        RiskType.SHORTAGE: "动态缺料",
        RiskType.BELOW_SAFETY_STOCK: "低于安全库存",
        RiskType.LATE_SUPPLY: "供应晚到",
        RiskType.EXCESS: "库存冗余",
        RiskType.OBSOLETE: "呆滞/过时",
    }
    severity = {RiskLevel.CRITICAL: 4, RiskLevel.HIGH: 3, RiskLevel.MEDIUM: 2, RiskLevel.LOW: 1}
    ordered = sorted(risks, key=lambda risk: (severity[risk.level], risk.value), reverse=True)
    return [RiskQueueItem(
        risk_id=risk.risk_id,
        priority=risk.level,
        material_id=risk.material_id,
        plant=risk.plant,
        issue=type_label.get(risk.risk_type, risk.risk_type.value),
        impact_quantity=risk.quantity,
        impact_value=risk.value,
        risk_date=risk.first_event_week,
        root_cause="；".join(risk.root_causes),
        recommended_action=risk.suggested_actions[0],
        owner_department=risk.owner_department,
        latest_action_date=risk.latest_action_date,
        source_version=risk.source_version,
    ) for risk in ordered]


def _validated_actions() -> list[ActionValidation]:
    shortage_target = demo_projection("CASE2", "MAT-B", "TARGET_PLANT")
    shortage_source = demo_projection("CASE2", "MAT-B", "SOURCE_PLANT")
    shortage_unit_cost = float(demo_planning_parameters("MAT-B")["unit_cost"])
    transfer_week = shortage_target.weeks[2].week_start
    transfer = Action(
        action_id="CT-TRANSFER-MAT-B-1800",
        action_type=ActionType.TRANSFER,
        object_id="MAT-B@SOURCE_PLANT→TARGET_PLANT",
        material_id="MAT-B",
        plant="TARGET_PLANT",
        quantity=1800,
        effective_week=transfer_week,
        source_plant="SOURCE_PLANT",
        estimated_value=1800 * shortage_unit_cost,
        reason="目标工厂需求上升且供应商交期延误",
        execution_condition="来源工厂逐周投影不产生缺料且完成跨厂审批",
        owner_department="计划/物流",
        due_date=transfer_week - timedelta(days=7),
    )
    transfer_validation = validate_action_impact(
        transfer,
        shortage_target,
        related_inputs=[shortage_source],
        unit_cost=shortage_unit_cost,
    )

    excess = demo_projection("CASE1", "MAT-A", "DEMO_PLANT")
    excess_unit_cost = float(demo_planning_parameters("MAT-A")["unit_cost"])
    cancel_week = next(row.week_start for row in excess.weeks if row.po_receipt >= 8000)
    cancellation = Action(
        action_id="CT-CANCEL-MAT-A-8000",
        action_type=ActionType.CANCEL_PO,
        object_id="PO-DEMO-A-1",
        material_id="MAT-A",
        plant="DEMO_PLANT",
        quantity=8000,
        effective_week=cancel_week,
        estimated_value=8000 * excess_unit_cost,
        reason="预测连续下调后减少未锁定在途供给",
        execution_condition="供应商确认可取消且采购/计划完成审批",
        owner_department="采购",
        due_date=cancel_week - timedelta(days=14),
    )
    cancellation_validation = validate_action_impact(cancellation, excess, unit_cost=excess_unit_cost)
    return [transfer_validation, cancellation_validation]


def _shortage_response(
    validation: ActionValidation,
    risk: Risk,
    supplier: SupplierReliabilityResult,
    supplier_assignment_version: str,
    *,
    question: str,
) -> StructuredCopilotResponse:
    before = validation.baseline
    after = validation.scenario
    first_before = before.first_shortage_week
    first_after = after.first_shortage_week
    improvement = before.maximum_shortage_qty - after.maximum_shortage_qty
    return StructuredCopilotResponse(
        question=question,
        summary=(
            f"MAT-B 在 {first_before} 首次发生缺料，最大缺口 {before.maximum_shortage_qty:,.0f} 件；"
            "主要驱动为需求爬升与供应商交期延误。"
        ),
        risk_level=risk.level,
        evidence=[
            CopilotEvidenceItem(
                label="首次缺料周",
                value=str(first_before),
                source="weekly_inventory_projection",
                source_version="DEMO-INV-V1",
            ),
            CopilotEvidenceItem(
                label="最大缺口",
                value=f"{before.maximum_shortage_qty:,.0f} 件",
                source="weekly_inventory_projection",
                source_version="DEMO-INV-V1",
            ),
            CopilotEvidenceItem(
                label="在途 PO",
                value="5,000 件 / 2026-08-31",
                source="demo_weekly_inventory",
                source_version="DEMO-INV-V1",
            ),
            CopilotEvidenceItem(
                label="供应商表现",
                value=f"{supplier.supplier_id} OTD {supplier.on_time_rate:.0%}，平均晚到 {supplier.mean_lateness_days:.1f} 天",
                source="supplier_reliability",
                source_version=",".join(supplier.source_versions),
            ),
            CopilotEvidenceItem(
                label="物料-供应商映射",
                value=f"MAT-B → {supplier.supplier_id}",
                source="demo_supplier_assignments",
                source_version=supplier_assignment_version,
            ),
        ],
        root_causes=[
            "周需求由 800 件逐步升至 1,800 件",
            "5,000 件 PO 到货晚于首次风险周",
            f"{supplier.supplier_id} 的演示交付记录显示持续晚到",
        ],
        recommendations=[
            f"从 SOURCE_PLANT 调拨 {validation.action.quantity:,.0f} 件至 TARGET_PLANT",
            "同步采购确认 5,000 件 PO 的可提前到货窗口",
            "动作执行前保留来源工厂保护量并完成计划/物流审批",
        ],
        expected_impact=[
            f"最大缺口减少 {improvement:,.0f} 件（{before.maximum_shortage_qty:,.0f} → {after.maximum_shortage_qty:,.0f}）",
            f"首次缺料由 {first_before} 推迟至 {first_after}",
            "来源工厂校验后未产生新缺料",
        ],
        business_rules=[
            "EndingInventory = Beginning + PO + Production + TransferIn - Demand - TransferOut",
            "EndingInventory < 0 → 动态缺料风险",
            "跨厂调拨必须重算来源与目标工厂，制造新缺料时拒绝",
        ],
        action_validation_id=validation.validation_id,
        limitations=[
            "风险为确定性规则分级，不输出未经校准的缺货概率",
            "成品预测与物料库存为两个独立、带版本号的 Demo 场景，不声称已逐周 BOM 贯通",
        ],
        source_versions={
            "inventory": "DEMO-INV-V1",
            "supplier": ",".join(supplier.source_versions),
            "supplier_assignment": supplier_assignment_version,
            "rules": load_rules().metadata.version,
        },
    )


def _excess_response(validation: ActionValidation, risk: Risk, *, question: str) -> StructuredCopilotResponse:
    before = validation.baseline
    after = validation.scenario
    unit_cost = risk.value / risk.quantity if risk.quantity else 0.0
    return StructuredCopilotResponse(
        question=question,
        summary=f"MAT-A 期末决策冗余为 {before.ending_excess_qty:,.0f} 件，金额 ¥{before.ending_excess_qty * unit_cost:,.0f}。",
        risk_level=risk.level,
        evidence=[
            CopilotEvidenceItem(label="期末冗余", value=f"{before.ending_excess_qty:,.0f} 件", source="weekly_inventory_projection", source_version="DEMO-INV-V1"),
            CopilotEvidenceItem(label="可取消 PO", value="8,000 件", source="action_validation", source_version="DEMO-INV-V1"),
        ],
        root_causes=["预测连续下调", "在途 PO 仍按原计划到货"],
        recommendations=["取消 8,000 件未锁定 PO，并完成采购经理与计划经理审批"],
        expected_impact=[f"期末冗余由 {before.ending_excess_qty:,.0f} 降至 {after.ending_excess_qty:,.0f} 件", "动作后不产生缺料"],
        business_rules=["Excess = max(0, EndingInventory - SafetyStock)", "取消 PO 后必须重新运行逐周投影"],
        action_validation_id=validation.validation_id,
        source_versions={"inventory": "DEMO-INV-V1", "rules": load_rules().metadata.version},
    )


def _supplier_response(snapshot: ControlTowerSnapshot, *, question: str) -> StructuredCopilotResponse:
    supplier = min(snapshot.suppliers, key=lambda row: row.reliability_score)
    return StructuredCopilotResponse(
        question=question,
        summary=f"{supplier.supplier_id} 是当前演示数据中交付风险最高的供应商，评级 {supplier.grade}。",
        risk_level=RiskLevel.HIGH,
        evidence=[
            CopilotEvidenceItem(label="OTD", value=f"{supplier.on_time_rate:.0%}", source="supplier_reliability", source_version=",".join(supplier.source_versions)),
            CopilotEvidenceItem(label="数量满足率", value=f"{supplier.quantity_fill_rate:.1%}", source="supplier_reliability", source_version=",".join(supplier.source_versions)),
            CopilotEvidenceItem(label="平均晚到", value=f"{supplier.mean_lateness_days:.1f} 天", source="supplier_reliability", source_version=",".join(supplier.source_versions)),
        ],
        root_causes=["准时交付率偏低", "部分订单缺少供应商确认日期", "数量满足率低于 100%"],
        recommendations=["优先确认 MAT-B 在途 PO 到货承诺", "对晚到订单建立例外任务，不自动修改采购单"],
        expected_impact=["形成可追溯的供应商协同任务；实际改善需等待后续交付记录验证"],
        business_rules=["ReliabilityScore = OTD、Fill Rate、交期稳定性与确认遵从率的配置加权"],
        limitations=supplier.warnings,
        source_versions={"supplier": ",".join(supplier.source_versions), "rules": supplier.rules_version},
    )


def _forecast_response(snapshot: ControlTowerSnapshot, *, question: str) -> StructuredCopilotResponse:
    points = [point for point in snapshot.demand_trend if point.period_type == "FORECAST"][:13]
    total = sum(point.forecast_qty or 0.0 for point in points)
    lower = sum(point.lower_bound or 0.0 for point in points)
    upper = sum(point.upper_bound or 0.0 for point in points)
    item_id = snapshot.selected_product_id
    source_version = points[0].source_version if points else snapshot.source_versions["demand"]
    return StructuredCopilotResponse(
        question=question,
        summary=f"{item_id} 未来 13 周统计预测合计 {total:,.0f} 件；上下限是规则情景带，不是统计置信区间。",
        risk_level=RiskLevel.LOW,
        evidence=[
            CopilotEvidenceItem(label="13周基准预测", value=f"{total:,.0f} 件", source="forecast_service", source_version=source_version),
            CopilotEvidenceItem(label="规则情景区间", value=f"{lower:,.0f} – {upper:,.0f} 件", source="forecast_service", source_version=source_version),
            CopilotEvidenceItem(label="预测周期", value=f"{points[0].week_start} – {points[-1].week_start}", source="control_tower_snapshot", source_version="DEMO-CT-V1"),
        ],
        root_causes=["统计基线由历史需求和已配置的候选模型、滚动回测规则生成"],
        recommendations=["进入 Demand Forecast 工作区查看候选模型、WAPE、Bias 与人工复核原因"],
        expected_impact=["该结果只更新需求判断；未应用人工调整，也未自动改变库存或 PO"],
        business_rules=["预测模型不得使用未来数据训练或评价", "情景下限 ≤ 基准预测 ≤ 情景上限"],
        limitations=["控制塔快照未携带全部候选模型回测明细；请在需求预测工作区下钻"],
        source_versions={"demand": source_version, "rules": snapshot.source_versions["rules"]},
    )


def _timing_shortage_response(snapshot: ControlTowerSnapshot, *, question: str) -> StructuredCopilotResponse:
    projection = next(item for item in snapshot.projections if item.material_id == "MAT-C")
    risk = next(item for item in snapshot.risks if item.material_id == "MAT-C")
    incoming = sum(point.po_receipt + point.production_receipt + point.transfer_in for point in projection.points)
    outgoing = sum(point.gross_demand + point.reserved_demand + point.transfer_out for point in projection.points)
    static_surplus = projection.initial_available_inventory + incoming - outgoing
    return StructuredCopilotResponse(
        question=question,
        summary=(
            f"MAT-C 静态总量仍结余 {static_surplus:,.0f} 件，但在 {projection.first_shortage_week} "
            f"发生中间周缺料，最大缺口 {projection.maximum_shortage_qty:,.0f} 件。"
        ),
        risk_level=risk.level,
        evidence=[
            CopilotEvidenceItem(label="静态期末结余", value=f"{static_surplus:,.0f} 件", source="weekly_inventory_projection", source_version=risk.source_version),
            CopilotEvidenceItem(label="首次缺料周", value=str(projection.first_shortage_week), source="weekly_inventory_projection", source_version=risk.source_version),
            CopilotEvidenceItem(label="最大缺口", value=f"{projection.maximum_shortage_qty:,.0f} 件", source="weekly_inventory_projection", source_version=risk.source_version),
        ],
        root_causes=["10,000 件 PO 在 2026-09-14 才到货，晚于前序需求发生周", "静态总量抵消了跨周供需错配"],
        recommendations=["模拟 PO 提前或拆单，并在建议前重新运行逐周库存投影"],
        expected_impact=["提前到货可消除中间周缺口；实际可行性仍需供应商确认和采购审批"],
        business_rules=["EndingInventory[t] 必须逐周递推", "总量不缺不能替代首次缺料周检查"],
        limitations=["当前控制塔未预置 MAT-C 的审批动作卡，需在情景模拟页创建并校验"],
        source_versions={"inventory": risk.source_version, "rules": snapshot.source_versions["rules"]},
    )


def _unsupported_response(snapshot: ControlTowerSnapshot, *, question: str) -> StructuredCopilotResponse:
    return StructuredCopilotResponse(
        question=question,
        summary="当前 Demo 未匹配到可验证的业务场景，因此没有执行数量计算或生成动作建议。",
        risk_level=RiskLevel.LOW,
        evidence=[
            CopilotEvidenceItem(
                label="当前选择",
                value=f"{snapshot.selected_product_id} / {snapshot.selected_material_id}",
                source="control_tower_scope",
                source_version=snapshot.source_versions["control_tower"],
            ),
        ],
        root_causes=["问题中缺少已支持的对象或意图"],
        recommendations=["可询问需求预测、MAT-B 缺料、MAT-C 中间周缺料、MAT-A 冗余或供应商交付风险"],
        expected_impact=["未改变任何预测、库存、PO 或审批状态"],
        business_rules=["数据不完整或场景不明确时不得静默补齐关键业务数据"],
        limitations=["结构化 Copilot 当前使用确定性 Demo 路由，不是开放域问答"],
        source_versions={"control_tower": snapshot.source_versions["control_tower"], "rules": snapshot.source_versions["rules"]},
    )


def resolve_question_product_id(question: str, fallback: str = "PRODUCT_B") -> str:
    """Resolve an explicitly named Demo product without guessing from unrelated text."""

    normalized = question.upper().replace("-", "_")
    compact = normalized.replace(" ", "").replace("_", "")
    if "PRODUCT_A" in normalized or "PRODUCTA" in compact:
        return "PRODUCT_A"
    if "PRODUCT_B" in normalized or "PRODUCTB" in compact:
        return "PRODUCT_B"
    return fallback


def answer_control_tower_question(snapshot: ControlTowerSnapshot, question: str) -> StructuredCopilotResponse:
    if resolve_question_product_id(question, snapshot.selected_product_id) != snapshot.selected_product_id:
        return _unsupported_response(snapshot, question=question)
    normalized = question.lower()
    if any(token in normalized for token in ("supplier", "供应商", "otd", "交付")):
        return _supplier_response(snapshot, question=question)
    if any(token in normalized for token in ("预测", "forecast", "未来13周", "未来 13 周")):
        return _forecast_response(snapshot, question=question)
    if any(token in normalized for token in ("mat-c", "中间周", "总量不缺")):
        return _timing_shortage_response(snapshot, question=question)
    if any(token in normalized for token in ("冗余", "excess", "cancel", "取消", "mat-a")):
        risk = next(item for item in snapshot.risks if item.material_id == "MAT-A")
        return _excess_response(snapshot.action_validations[1], risk, question=question)
    shortage_intent = any(token in normalized for token in ("缺料", "shortage", "mat-b", "调拨", "po", "风险"))
    if shortage_intent:
        if snapshot.selected_product_id == "PRODUCT_A" and "mat-b" not in normalized:
            risk = next(item for item in snapshot.risks if item.material_id == "MAT-A")
            return _excess_response(snapshot.action_validations[1], risk, question=question)
        risk = next(item for item in snapshot.risks if item.material_id == "MAT-B")
        supplier, assignment_version = _supplier_for_material(
            "MAT-B",
            snapshot.suppliers,
            as_of_date=snapshot.as_of.date(),
        )
        return _shortage_response(
            snapshot.action_validations[0],
            risk,
            supplier,
            assignment_version,
            question=question,
        )
    return _unsupported_response(snapshot, question=question)


def build_demo_control_tower_snapshot(selected_product_id: str = "PRODUCT_B") -> ControlTowerSnapshot:
    """Build one traceable demo story from existing deterministic services."""

    cfg = load_rules()
    histories, metadata, forecasts = _forecast_all()
    if selected_product_id not in PRODUCT_TO_MATERIAL:
        raise ValueError(f"control tower product must be one of {sorted(PRODUCT_TO_MATERIAL)}")

    projections: list[InventoryProjectionResult] = []
    risks: list[Risk] = []
    heatmap: list[InventoryRiskCell] = []
    for case_id, material_id, plant, context in CASE_DEFINITIONS:
        unit_cost = float(demo_planning_parameters(material_id)["unit_cost"])
        projection = project_inventory_by_week(demo_projection(case_id, material_id, plant))
        projections.append(projection)
        risks.extend(identify_projection_risks(projection, unit_cost=unit_cost, context=context))
        heatmap.extend(_risk_cell(
            projection,
            unit_cost=unit_cost,
            forecast_down=bool(context.get("forecast_down_consecutive")),
        ))

    # The planning snapshot is taken six days before the first weekly inventory
    # bucket. This keeps the date tied to the versioned demo inputs.
    source_as_of = min(
        point.week_start
        for projection in projections
        for point in projection.points
    ) - timedelta(days=6)

    task_service = RiskTaskService()
    for risk in risks:
        task_service.create_from_risk(risk, assignee="demo_owner")
    task_service.generate_notifications(date(2026, 8, 25))

    supplier_records = demo_supplier_records()
    supplier_ids = sorted({record.supplier_id for record in supplier_records})
    suppliers = [calculate_supplier_reliability(supplier, supplier_records) for supplier in supplier_ids]
    data_quality = _demo_data_quality()
    legacy_data_quality = assess_project_data()
    forecast_results = list(forecasts.values())
    dashboard = build_management_dashboard(
        data_quality=data_quality,
        forecasts=forecast_results,
        risks=risks,
        tasks=task_service.list_tasks(),
        suppliers=suppliers,
        source_versions={"dashboard": "DEMO-CT-V1"},
    )
    actions = _validated_actions()
    weighted_otd = sum(result.on_time_rate * result.sample_count for result in suppliers) / sum(result.sample_count for result in suppliers)
    critical_shortages = sum(1 for risk in risks if risk.risk_type == RiskType.SHORTAGE and risk.level == RiskLevel.CRITICAL)
    kpis = [
        ControlTowerKPI(
            key="average_wape",
            label="平均 WAPE",
            value=dashboard.average_wape or 0.0,
            display_value=f"{(dashboard.average_wape or 0):.1%}",
            detail=f"{dashboard.forecast_items} 个需求序列；越低越好",
            status=(
                ControlTowerStatus.RISK
                if (dashboard.average_wape or 0) > cfg.control_tower.portfolio_wape_risk_threshold
                else ControlTowerStatus.HEALTHY
            ),
            drilldown_page="需求预测",
        ),
        ControlTowerKPI(
            key="shortage_risks",
            label="缺料风险",
            value=float(dashboard.shortage_risk_count),
            display_value=f"{dashboard.shortage_risk_count} 项",
            detail=f"{critical_shortages} 项 Critical · ¥{dashboard.shortage_value:,.0f}",
            status=ControlTowerStatus.CRITICAL if critical_shortages else ControlTowerStatus.WATCH,
            drilldown_page="库存控制台",
        ),
        ControlTowerKPI(
            key="excess_value",
            label="冗余敞口",
            value=dashboard.excess_value,
            display_value=f"¥{dashboard.excess_value / 1000:,.0f}K",
            detail=f"{dashboard.excess_risk_count} 项规则触发",
            status=ControlTowerStatus.RISK if dashboard.excess_value else ControlTowerStatus.HEALTHY,
            drilldown_page="库存冗余",
        ),
        ControlTowerKPI(
            key="open_actions",
            label="待协同行动",
            value=float(dashboard.open_task_count),
            display_value=f"{dashboard.open_task_count} 项",
            detail=f"{len(actions)} 项已完成动作前后校验",
            status=ControlTowerStatus.WATCH if dashboard.open_task_count else ControlTowerStatus.HEALTHY,
            drilldown_page="采购工作台",
        ),
        ControlTowerKPI(
            key="supplier_otd",
            label="供应商 OTD",
            value=weighted_otd,
            display_value=f"{weighted_otd:.0%}",
            detail=f"{sum(1 for row in suppliers if row.grade in {'C', 'D'})} 家低于 B 级",
            status=(
                ControlTowerStatus.RISK
                if weighted_otd < cfg.control_tower.supplier_otd_risk_threshold
                else ControlTowerStatus.HEALTHY
            ),
            drilldown_page="供应商交期可靠性",
        ),
    ]

    transfer_validation, cancellation_validation = actions
    mat_b_risk = next(risk for risk in risks if risk.material_id == "MAT-B")
    mat_c_risk = next(risk for risk in risks if risk.material_id == "MAT-C")
    mat_a_risk = next(risk for risk in risks if risk.material_id == "MAT-A")
    mat_b_supplier, supplier_assignment_version = _supplier_for_material(
        "MAT-B",
        suppliers,
        as_of_date=source_as_of,
    )
    insights = [
        InsightCard(
            insight_id="INSIGHT-MAT-B",
            status=ControlTowerStatus.CRITICAL,
            title="MAT-B 将发生动态缺料",
            what_happened=f"{mat_b_risk.first_event_week} 首次缺料，最大缺口 {mat_b_risk.quantity:,.0f} 件。",
            why="需求爬升，同时供应商交期延误且 PO 晚于风险窗口。",
            recommendation=(
                f"调拨 {transfer_validation.action.quantity:,.0f} 件；校验后首次缺料推迟至 {transfer_validation.scenario.first_shortage_week}，"
                f"最大缺口降至 {transfer_validation.scenario.maximum_shortage_qty:,.0f} 件。"
            ),
            drilldown_page="库存控制台",
            object_id="MAT-B",
        ),
        InsightCard(
            insight_id="INSIGHT-MAT-C",
            status=ControlTowerStatus.RISK,
            title="MAT-C 总量充足但中间周缺料",
            what_happened=f"{mat_c_risk.first_event_week} 首次缺料，最大缺口 {mat_c_risk.quantity:,.0f} 件。",
            why="10,000 件 PO 在 2026-09-14 才到货，晚于需求发生。",
            recommendation="优先评估 PO 提前或拆单，不能用静态总量替代逐周投影。",
            drilldown_page="库存控制台",
            object_id="MAT-C",
        ),
        InsightCard(
            insight_id="INSIGHT-MAT-A",
            status=ControlTowerStatus.WATCH,
            title="MAT-A 预测下调形成冗余",
            what_happened=f"期末冗余 {mat_a_risk.quantity:,.0f} 件，金额 ¥{mat_a_risk.value:,.0f}。",
            why="预测连续下调，但原在途 PO 未同步收缩。",
            recommendation=(
                f"取消 8,000 件后，期末冗余降至 {cancellation_validation.scenario.ending_excess_qty:,.0f} 件，且不制造缺料。"
            ),
            drilldown_page="库存冗余",
            object_id="MAT-A",
        ),
    ]

    snapshot = ControlTowerSnapshot(
        as_of=datetime.combine(source_as_of, datetime.min.time(), tzinfo=ZoneInfo(cfg.reporting.timezone)),
        selected_product_id=selected_product_id,
        selected_material_id=PRODUCT_TO_MATERIAL[selected_product_id],
        kpis=kpis,
        demand_trend=_demand_trend(selected_product_id, histories, metadata, forecasts),
        inventory_heatmap=heatmap,
        projections=projections,
        risks=risks,
        risk_queue=_risk_queue(risks),
        insights=insights,
        action_validations=actions,
        suppliers=suppliers,
        structured_response=(
            _shortage_response(
                transfer_validation,
                mat_b_risk,
                mat_b_supplier,
                supplier_assignment_version,
                question="为什么 MAT-B 有缺料风险？",
            )
            if selected_product_id == "PRODUCT_B"
            else _excess_response(cancellation_validation, mat_a_risk, question="为什么 MAT-A 有冗余风险？")
        ),
        data_quality=data_quality,
        legacy_data_quality=legacy_data_quality,
        limitations=[
            "数据均为合成 Demo；金额、阈值和服务水平需在生产使用前校准。",
            "原 V2 兼容表保留重复单据用于数据质量演示；控制塔计算使用隔离的 DEMO-* 数据版本。",
            "需求图使用 DEMO-HISTORY-V1，库存热力与动作中心使用独立的 DEMO-INV-V1 异常场景；当前组合视图不声称二者已逐周 BOM 贯通。",
            "动作仅为内存模拟和审批建议，不写回 ERP。",
        ],
        source_versions={
            "demand": str(metadata[selected_product_id]["data_version"]),
            "inventory": "DEMO-INV-V1",
            "supplier": "DEMO-SUP-V1",
            "supplier_assignment": supplier_assignment_version,
            "control_tower": "DEMO-CT-V1",
            "rules": cfg.metadata.version,
        },
    )
    return snapshot
