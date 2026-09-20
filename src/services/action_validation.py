from __future__ import annotations

from datetime import date
from typing import Iterable

from ..config import RulesConfig, load_rules
from ..models import (
    Action,
    ActionType,
    ActionValidation,
    Approval,
    ApprovalStatus,
    InventoryProjectionInput,
    InventoryProjectionResult,
    WeeklyInventoryInput,
)
from .inventory_projection import project_inventory_by_week


def _week(data: InventoryProjectionInput, week_start: date) -> WeeklyInventoryInput:
    for row in data.weeks:
        if row.week_start == week_start:
            return row
    row = WeeklyInventoryInput(week_start=week_start)
    data.weeks.append(row)
    data.weeks.sort(key=lambda item: item.week_start)
    return row


def _reduce_po(data: InventoryProjectionInput, start_week: date, quantity: float) -> float:
    remaining = max(0.0, quantity)
    for row in sorted((row for row in data.weeks if row.week_start >= start_week), key=lambda item: item.week_start):
        reduction = min(row.po_receipt, remaining)
        row.po_receipt -= reduction
        remaining -= reduction
        if remaining <= 1e-9:
            break
    return remaining


def _reduce_demand(data: InventoryProjectionInput, start_week: date, quantity: float) -> float:
    remaining = max(0.0, quantity)
    for row in sorted((row for row in data.weeks if row.week_start >= start_week), key=lambda item: item.week_start):
        reduction = min(row.gross_demand, remaining)
        row.gross_demand -= reduction
        remaining -= reduction
        if remaining <= 1e-9:
            break
    return remaining


def _apply_action(
    action: Action,
    target: InventoryProjectionInput,
    related: list[InventoryProjectionInput],
) -> list[str]:
    warnings: list[str] = []
    if action.action_type in {ActionType.CANCEL_PO, ActionType.REDUCE_PO}:
        unallocated = _reduce_po(target, action.effective_week, action.quantity)
        if unallocated > 1e-9:
            warnings.append(f"可调整PO少于动作数量，尚有 {unallocated:.2f} 未应用")
    elif action.action_type in {ActionType.EXPEDITE_PO, ActionType.DELAY_PO}:
        if not action.target_week:
            raise ValueError("PO提前/延期动作必须提供target_week")
        original = _week(target, action.effective_week)
        moved = min(original.po_receipt, action.quantity)
        original.po_receipt -= moved
        _week(target, action.target_week).po_receipt += moved
        if moved < action.quantity:
            warnings.append("原到货周数量不足，仅移动可用PO数量")
    elif action.action_type == ActionType.SPLIT_PO:
        if not action.target_week:
            raise ValueError("PO拆单动作必须提供target_week")
        original = _week(target, action.effective_week)
        moved = min(original.po_receipt, action.quantity)
        original.po_receipt -= moved
        _week(target, action.target_week).po_receipt += moved
    elif action.action_type == ActionType.TRANSFER:
        _week(target, action.effective_week).transfer_in += action.quantity
        source = next((item for item in related if item.plant == action.source_plant and item.material_id == action.material_id), None)
        if source is None:
            warnings.append("缺少来源工厂投影，无法校验调拨是否制造来源缺料")
        else:
            _week(source, action.effective_week).transfer_out += action.quantity
    elif action.action_type == ActionType.ECN_SWITCH and action.parameters.get("mode") == "consume_source_excess":
        consumed = action.quantity
        _week(target, action.effective_week).gross_demand += consumed
        displaced = next((item for item in related if item.material_id == action.target_material_id and item.plant == action.plant), None)
        if displaced is None:
            warnings.append("缺少被替换新料投影，不能确认ECN跨物料影响")
        else:
            _reduce_demand(displaced, action.effective_week, consumed)
    elif action.action_type in {ActionType.SUBSTITUTE, ActionType.ECN_SWITCH}:
        unallocated = _reduce_demand(target, action.effective_week, action.quantity)
        consumed = action.quantity - unallocated
        substitute = next((item for item in related if item.material_id == action.target_material_id and item.plant == action.plant), None)
        if substitute is None:
            warnings.append("缺少替代/ECN目标料投影，不能确认目标料数量是否充足")
        else:
            _week(substitute, action.effective_week).gross_demand += consumed
    elif action.action_type == ActionType.DEMAND_ADJUST:
        delta = float(action.parameters.get("delta_qty", action.quantity))
        row = _week(target, action.effective_week)
        row.gross_demand = max(0.0, row.gross_demand + delta)
    elif action.action_type == ActionType.SAFETY_STOCK_ADJUST:
        new_value = float(action.parameters.get("new_safety_stock", action.quantity))
        for row in target.weeks:
            if row.week_start >= action.effective_week:
                row.safety_stock = max(0.0, new_value)
    elif action.action_type in {ActionType.DELETE_PR, ActionType.FREEZE_PURCHASE, ActionType.SUPPLIER_RETURN, ActionType.SCRAP}:
        warnings.append("该动作不改变已排程供需；仅记录审批和执行约束")
    else:
        raise ValueError(f"unsupported action type {action.action_type}")
    return warnings


def _last_coverage(result: InventoryProjectionResult) -> float | None:
    return result.points[-1].coverage_weeks if result.points else None


def validate_action_impact(
    action: Action,
    baseline_input: InventoryProjectionInput,
    *,
    related_inputs: Iterable[InventoryProjectionInput] = (),
    unit_cost: float = 0.0,
    rules: RulesConfig | None = None,
) -> ActionValidation:
    cfg = rules or load_rules()
    if baseline_input.material_id != action.material_id or baseline_input.plant != action.plant:
        raise ValueError("action object does not match baseline material and plant")
    baseline = project_inventory_by_week(baseline_input)
    scenario_input = baseline_input.model_copy(deep=True)
    related_originals = list(related_inputs)
    related_baselines = [project_inventory_by_week(item) for item in related_originals]
    related_copies = [item.model_copy(deep=True) for item in related_originals]
    warnings = _apply_action(action, scenario_input, related_copies)
    scenario = project_inventory_by_week(scenario_input)
    related_results = [project_inventory_by_week(item) for item in related_copies]
    shortage_delta = scenario.maximum_shortage_qty - baseline.maximum_shortage_qty
    excess_delta = scenario.ending_excess_qty - baseline.ending_excess_qty
    inventory_value_delta = (
        scenario.points[-1].ending_inventory - baseline.points[-1].ending_inventory
    ) * max(0.0, unit_cost)
    baseline_coverage = _last_coverage(baseline)
    scenario_coverage = _last_coverage(scenario)
    coverage_delta = None if baseline_coverage is None or scenario_coverage is None else scenario_coverage - baseline_coverage
    related_shortage = any(result.maximum_shortage_qty > 0 for result in related_results)
    creates_new_shortage = shortage_delta > 1e-9 or related_shortage
    affects_other = bool(related_results) or action.action_type in {ActionType.TRANSFER, ActionType.SUBSTITUTE, ActionType.ECN_SWITCH}
    rejection_reasons: list[str] = []
    if creates_new_shortage:
        rejection_reasons.append("动作制造新的或更大的缺料")
    if any("缺少" in warning and "校验" in warning for warning in warnings):
        rejection_reasons.append("跨实体数据不完整，无法证明动作安全")
    if action.action_type in {ActionType.SUBSTITUTE, ActionType.ECN_SWITCH} and action.target_material_id is None:
        rejection_reasons.append("未提供目标替代料/ECN物料")
    approvers = cfg.approvals.matrix.get(action.action_type.value, [])
    approval_required = bool(approvers)
    if action.approval is None and approval_required:
        action = action.model_copy(update={"approval": Approval(
            approval_id=f"APR-{action.action_id}",
            action_id=action.action_id,
            required=True,
            approvers=approvers,
            owner_department=action.owner_department,
            status=ApprovalStatus.PENDING,
            due_date=action.due_date,
        )})
    residual_risks = warnings[:]
    for before_related, after_related in zip(related_baselines, related_results):
        if (
            before_related.first_below_safety_stock_week is None
            and after_related.first_below_safety_stock_week is not None
        ):
            residual_risks.append(
                f"关联实体 {after_related.material_id}@{after_related.plant} 新增低于安全库存风险，"
                f"首次发生于 {after_related.first_below_safety_stock_week}"
            )
    if scenario.maximum_shortage_qty > 0:
        residual_risks.append(f"动作后最大缺口仍为 {scenario.maximum_shortage_qty:.2f}")
    if scenario.ending_excess_qty > 0:
        residual_risks.append(f"动作后期末冗余仍为 {scenario.ending_excess_qty:.2f}")
    return ActionValidation(
        validation_id=f"VAL-{action.action_id}",
        action=action,
        baseline=baseline,
        scenario=scenario,
        shortage_delta=shortage_delta,
        excess_delta=excess_delta,
        inventory_value_delta=inventory_value_delta,
        ending_coverage_delta=coverage_delta,
        creates_new_shortage=creates_new_shortage,
        affects_other_entities=affects_other,
        related_entity_results=related_results,
        recommended=not rejection_reasons,
        rejection_reasons=rejection_reasons,
        residual_risks=residual_risks,
        approval_required=approval_required,
    )
