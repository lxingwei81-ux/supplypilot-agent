from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src.demo import (
    demo_atp_demands, demo_bom_rows, demo_histories, demo_po_options,
    demo_price_breaks, demo_projection, demo_supplier_records,
    demo_transfer_network,
)
from src.models import (
    Action, ActionType, DemandScenario, ECNValidationStatus, Evidence,
    ECNWorkflow, FieldMapping, ForecastAdjustment, ForecastConfidence,
    InventoryDecision, WeeklySnapshot, WorkflowStatus,
)
from src.repository import load_table
from src.router import route_scenario
from src.services.action_validation import validate_action_impact
from src.services.allocation import allocate_shared_material_atp
from src.services.backtesting import rolling_backtest_trace
from src.services.bom import explode_bom
from src.services.data_quality import assess_project_data
from src.services.demand_classification import classify_demand
from src.services.forecasting import generate_forecast
from src.services.ecn_workflow import create_ecn_workflow, transition_ecn
from src.services.excel_import import import_excel, suggest_field_mapping
from src.services.forecast_adjustment_workflow import create_adjustment_workflow, transition_adjustment
from src.services.forecast_versioning import ForecastVersionService
from src.services.inventory_policy import calculate_inventory_policy
from src.services.inventory_projection import project_inventory_by_week
from src.services.procurement_optimization import optimize_po_reduction_plan, optimize_replenishment_order
from src.services.risks import identify_projection_risks
from src.services.scenario_optimization import optimize_inventory_across_scenarios
from src.services.snapshots import SnapshotStore
from src.services.supplier_reliability import calculate_supplier_reliability
from src.services.task_management import RiskTaskService
from src.services.transfer_optimization import optimize_cross_plant_transfer
from src.ui.control_tower import render_control_tower
from src.ui.copilot import render_copilot
from src.ui.navigation import render_navigation
from src.ui.theme import inject_theme
from src.ui.workspaces import (
    render_demand_workspace,
    render_inventory_workspace,
    render_procurement_workspace,
)


st.set_page_config(page_title="SupplyPilot Control Tower", page_icon="📦", layout="wide")
inject_theme()


def json_download(label: str, value: object, name: str) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    st.download_button(label, json.dumps(value, ensure_ascii=False, indent=2, default=str), name, "application/json")


def csv_download(label: str, frame: pd.DataFrame, name: str) -> None:
    st.download_button(label, frame.to_csv(index=False).encode("utf-8-sig"), name, "text/csv")


@st.cache_data
def histories_and_metadata() -> tuple[dict[str, list[float]], dict[str, dict[str, object]]]:
    return demo_histories()


def forecast_for(item_id: str):
    histories, metadata = histories_and_metadata()
    meta = metadata[item_id]
    classification = classify_demand(
        {item_id: histories[item_id]}, unit_costs={item_id: float(meta["unit_cost"])},
        lifecycles={item_id: str(meta["lifecycle"])}, source_version=str(meta["data_version"]),
    )[0]
    result = generate_forecast(
        item_id, histories[item_id], classification,
        last_history_week=date.fromisoformat(str(meta["last_history_week"])),
        history_source=str(meta["data_version"]), stockout_unit_cost=float(meta["unit_cost"]),
    )
    return classification, result


def projection_choice(label: str = "演示案例"):
    options = {
        "案例1：需求下降/冗余": ("CASE1", "MAT-A", "DEMO_PLANT"),
        "案例2：需求上升/缺料": ("CASE2", "MAT-B", "TARGET_PLANT"),
        "案例3：总量不缺/中间周缺料": ("CASE3", "MAT-C", "DEMO_PLANT"),
    }
    selected = st.selectbox(label, options)
    return options[selected]


requested_page = st.query_params.get("page")
page = render_navigation(requested_page)


if page == "管理驾驶舱":
    render_control_tower()

elif page == "库存控制台":
    render_inventory_workspace()

elif page == "采购工作台":
    render_procurement_workspace()

elif page == "AI Copilot":
    render_copilot()

elif page == "数据质量":
    report = assess_project_data()
    c1, c2, c3 = st.columns(3)
    c1.metric("检查表数", len(report.tables_checked))
    c2.metric("问题数", len(report.issues))
    c3.metric("允许继续", "是" if report.can_proceed else "否（存在阻断）")
    issue_frame = pd.DataFrame([issue.model_dump(mode="json", exclude={"evidence"}) for issue in report.issues])
    st.dataframe(issue_frame, use_container_width=True)
    st.warning("；".join(report.limitations) if report.limitations else "未发现数据限制")
    json_download("下载数据质量报告", report, "data_quality_report.json")

elif page == "需求分类":
    histories, metadata = histories_and_metadata()
    selected = st.multiselect("SKU/产品", list(histories), default=list(histories))
    classifications = classify_demand(
        {item: histories[item] for item in selected},
        unit_costs={item: float(metadata[item]["unit_cost"]) for item in selected},
        lifecycles={item: str(metadata[item]["lifecycle"]) for item in selected},
        source_version="DEMO-HISTORY-V1",
    ) if selected else []
    frame = pd.DataFrame([item.model_dump(mode="json") for item in classifications])
    st.dataframe(frame, use_container_width=True)
    if not frame.empty:
        csv_download("下载分类结果", frame, "demand_classification.csv")

elif page == "需求预测":
    render_demand_workspace()

elif page == "预测对比与回测":
    histories, _ = histories_and_metadata()
    item = st.selectbox("SKU/产品", list(histories))
    _, result = forecast_for(item)
    metric_frame = pd.DataFrame([metric.model_dump(mode="json") for metric in result.candidate_metrics])
    st.dataframe(metric_frame.sort_values("model_score"), use_container_width=True)
    if result.selected_model:
        trace = pd.DataFrame(rolling_backtest_trace(histories[item], result.selected_model))
        if not trace.empty:
            latest_fold = trace[trace["fold"] == trace["fold"].max()].set_index("target_index")
            st.line_chart(latest_fold[["actual", "forecast"]])
            st.caption("图中为最后一个滚动回测折；training_end_index 严格小于 target_index，避免未来数据泄漏。")
            csv_download("下载回测明细", trace, f"backtest_{item}.csv")

elif page == "预测版本及人工调整":
    histories, _ = histories_and_metadata()
    item = st.selectbox("SKU/产品", list(histories))
    _, result = forecast_for(item)
    base_point = result.points[0]
    adjusted_qty = st.number_input("首周人工调整数量", min_value=0.0, value=float(round(base_point.baseline_qty + 100, 2)))
    reason = st.text_input("调整原因", "客户项目确认变化（Demo）")
    if st.button("创建并审批Demo共识版本", type="primary"):
        service = ForecastVersionService()
        statistical = service.create_statistical(item, result.points)
        adjustment = ForecastAdjustment(
            adjustment_id="UI-ADJ-001", item_id=item, week_start=base_point.week_start,
            before_qty=base_point.baseline_qty, after_qty=adjusted_qty,
            reason_code="BUSINESS_EVIDENCE", reason=reason, adjusted_by="demo_planner",
            approved_by="demo_manager", effective_from=base_point.week_start,
            effective_to=base_point.week_start, confidence=ForecastConfidence.MEDIUM,
        )
        adjusted = service.create_adjusted(statistical.version_id, [adjustment], created_by="demo_planner")
        consensus = service.approve_consensus(adjusted.version_id, approved_by="demo_manager")
        st.success(f"共识版本 {consensus.version_id} 已生成；FVA状态为待实际值。")
        st.json(consensus.model_dump(mode="json"))

elif page == "BOM需求拆解":
    product = st.selectbox("成品", ["PRODUCT_A", "PRODUCT_B", "PRODUCT_C"])
    weekly_qty = st.number_input("每周成品预测", min_value=0.0, value=600.0)
    start = date(2026, 7, 27)
    weeks = {start + timedelta(days=7 * index): weekly_qty for index in range(13)}
    requirements = explode_bom(product, weeks, demo_bom_rows(), forecast_version_id="UI-CONSENSUS-DEMO")
    frame = pd.DataFrame([row.model_dump(mode="json") for row in requirements])
    st.dataframe(frame, use_container_width=True)
    csv_download("下载BOM毛需求", frame, f"bom_requirements_{product}.csv")

elif page == "周度库存投影":
    case_id, material, plant = projection_choice()
    result = project_inventory_by_week(demo_projection(case_id, material, plant))
    frame = pd.DataFrame([point.model_dump(mode="json") for point in result.points])
    st.line_chart(frame.set_index("week_start")[["ending_inventory", "safety_stock", "shortage_qty", "excess_qty"]])
    c1, c2, c3 = st.columns(3)
    c1.metric("首次低于安全库存周", str(result.first_below_safety_stock_week or "无"))
    c2.metric("首次缺料周", str(result.first_shortage_week or "无"))
    c3.metric("最大缺口", f"{result.maximum_shortage_qty:,.2f}")
    st.dataframe(frame, use_container_width=True)
    st.caption(f"数据版本：{frame.iloc[0]['data_version']}；计算时间：{result.calculated_at.isoformat()}")
    csv_download("下载周度投影", frame, f"projection_{material}_{plant}.csv")

elif page == "缺料风险":
    case_id, material, plant = projection_choice()
    result = project_inventory_by_week(demo_projection(case_id, material, plant))
    risks = identify_projection_risks(result, unit_cost=45, context={"po_late": True, "supplier_delay": case_id == "CASE2"})
    frame = pd.DataFrame([risk.model_dump(mode="json") for risk in risks if risk.risk_type.value in {"SHORTAGE", "BELOW_SAFETY_STOCK"}])
    st.dataframe(frame, use_container_width=True)
    if not frame.empty:
        csv_download("下载缺料风险", frame, "shortage_risks.csv")

elif page == "库存冗余":
    data = demo_projection("CASE1", "MAT-A", "DEMO_PLANT")
    result = project_inventory_by_week(data)
    risks = identify_projection_risks(result, unit_cost=18, context={"forecast_down_consecutive": True, "open_po": 16000})
    st.metric("期末决策冗余", f"{result.ending_excess_qty:,.0f}")
    st.dataframe(pd.DataFrame([risk.model_dump(mode="json") for risk in risks]), use_container_width=True)
    st.subheader("兼容版现有冗余组合")
    st.dataframe(pd.DataFrame(load_table("excess_risks")), use_container_width=True)

elif page == "PO行动清单":
    data = demo_projection("CASE1", "MAT-A", "DEMO_PLANT")
    receipt_week = data.weeks[3].week_start
    quantity = st.number_input("拟取消数量", min_value=0.0, max_value=8000.0, value=8000.0, step=500.0)
    action = Action(
        action_id="UI-CANCEL", action_type=ActionType.CANCEL_PO, object_id="PO-DEMO-A-1",
        material_id="MAT-A", plant="DEMO_PLANT", quantity=quantity, effective_week=receipt_week,
        reason="需求下调后的PO预防动作", execution_condition="供应商与计划确认",
        owner_department="采购", due_date=receipt_week - timedelta(days=14),
    )
    validation = validate_action_impact(action, data, unit_cost=18)
    st.write(f"建议执行：`{validation.recommended}`；制造新缺料：`{validation.creates_new_shortage}`")
    st.dataframe(pd.DataFrame([validation.action.model_dump(mode="json")]), use_container_width=True)
    st.dataframe(pd.DataFrame(load_table("po_flexibility")), use_container_width=True)
    json_download("下载动作校验", validation, "po_action_validation.json")

elif page == "情景模拟":
    case_id, material, plant = projection_choice()
    data = demo_projection(case_id, material, plant)
    action_name = st.selectbox("动作", ["PO取消", "PO提前", "安全库存调整"])
    quantity = st.number_input("动作数量", min_value=0.0, value=1000.0, step=100.0)
    if action_name == "PO取消":
        action_type, effective, target, parameters = ActionType.CANCEL_PO, data.weeks[3].week_start, None, {}
    elif action_name == "PO提前":
        receipt_rows = [row for row in data.weeks if row.po_receipt > 0]
        effective = receipt_rows[0].week_start if receipt_rows else data.weeks[-1].week_start
        action_type, target, parameters = ActionType.EXPEDITE_PO, data.weeks[1].week_start, {}
    else:
        action_type, effective, target, parameters = ActionType.SAFETY_STOCK_ADJUST, data.weeks[0].week_start, None, {"new_safety_stock": quantity}
    action = Action(
        action_id="UI-SCENARIO", action_type=action_type, object_id="DEMO-ACTION",
        material_id=material, plant=plant, quantity=quantity, effective_week=effective,
        target_week=target, reason="UI What-if", execution_condition="仅模拟，不写回",
        owner_department="计划", due_date=data.weeks[0].week_start, parameters=parameters,
    )
    validation = validate_action_impact(action, data, unit_cost=20)
    before = validation.baseline.points[-1]
    after = validation.scenario.points[-1]
    st.dataframe(pd.DataFrame([
        {"情景": "动作前", "最大缺口": validation.baseline.maximum_shortage_qty, "期末冗余": validation.baseline.ending_excess_qty, "期末库存": before.ending_inventory},
        {"情景": "动作后", "最大缺口": validation.scenario.maximum_shortage_qty, "期末冗余": validation.scenario.ending_excess_qty, "期末库存": after.ending_inventory},
    ]), use_container_width=True)
    st.write(f"建议执行：`{validation.recommended}`；拒绝原因：{validation.rejection_reasons or '无'}")

elif page == "审批与任务跟踪":
    actions = pd.DataFrame(load_table("excess_action_plan"))
    st.dataframe(actions, use_container_width=True)
    st.caption("所有取消PO、调拨、替代、ECN和报废均只生成建议与审批对象；本Demo不连接或写回ERP。")
    csv_download("下载审批任务", actions, "approval_tasks.csv")

elif page == "共用料ATP与客户分配":
    demands = demo_atp_demands()
    available = st.number_input("总有效供给", min_value=0.0, value=8000.0, step=500.0)
    protected = st.number_input("不可分配保护量", min_value=0.0, value=500.0, step=100.0)
    result = allocate_shared_material_atp(
        "COMMON-M", available_supply=available, protected_supply=protected,
        demands=demands, source_versions={"demand": "DEMO-ATP-V1"},
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("可分配", f"{result.allocatable_supply:,.0f}")
    c2.metric("已分配", f"{result.total_allocated:,.0f}")
    c3.metric("未满足", f"{result.total_unfulfilled:,.0f}")
    frame = pd.DataFrame([row.model_dump(mode="json") for row in result.allocations])
    st.bar_chart(frame.set_index("demand_id")[["requested_qty", "allocated_qty", "unfulfilled_qty"]])
    st.dataframe(frame, use_container_width=True)
    st.caption("客户优先级5为最高；冻结订单、停线损失、需求日期和生命周期共同形成可追溯分配分数。")
    csv_download("下载ATP分配", frame, "atp_allocation.csv")

elif page == "多工厂调拨优化":
    sources, targets, lanes = demo_transfer_network()
    result = optimize_cross_plant_transfer(
        "MAT-B", as_of_date=date(2026, 7, 21), sources=sources, targets=targets, lanes=lanes,
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("调拨前缺口", f"{result.total_shortage_before:,.0f}")
    c2.metric("调拨后缺口", f"{result.total_shortage_after:,.0f}")
    c3.metric("总调拨成本", f"¥{result.total_cost:,.2f}")
    frame = pd.DataFrame([row.model_dump(mode="json") for row in result.recommendations])
    st.dataframe(frame, use_container_width=True)
    st.info("求解器：确定性最小成本流。来源可用量已扣除保护量、未来需求和最低覆盖；晚于需求日或不兼容通道不会进入解。")
    if result.infeasible_reasons:
        st.warning("；".join(result.infeasible_reasons))
    csv_download("下载调拨方案", frame, "transfer_plan.csv")

elif page == "采购成本与批量优化":
    st.subheader("PO取消/延期成本优化")
    excess = st.number_input("决策冗余", min_value=0.0, value=9000.0, step=500.0)
    po_result = optimize_po_reduction_plan(
        "MAT-A", "DEMO_PLANT", excess_qty=excess, po_options=demo_po_options(),
        as_of_date=date(2026, 7, 21), horizon_weeks=13,
    )
    st.dataframe(pd.DataFrame([row.model_dump(mode="json") for row in po_result.adjustments]), use_container_width=True)
    st.write(f"动作后冗余：`{po_result.excess_after:,.0f}`；取消罚金：`¥{po_result.total_penalty_cost:,.2f}`；净收益：`¥{po_result.net_benefit:,.2f}`")
    st.subheader("MOQ/MPQ/包装/价格阶梯联合优化")
    required = st.number_input("净需求数量", min_value=0.0, value=4700.0, step=100.0)
    breaks, lots = demo_price_breaks()
    replenishment = optimize_replenishment_order("MAT-B", required_qty=required, price_breaks=breaks, **lots)
    st.json(replenishment.model_dump(mode="json"))

elif page == "ECN验证状态机":
    if "ecn_demo_workflow" not in st.session_state:
        st.session_state.ecn_demo_workflow = create_ecn_workflow(
            "ECN-DEMO-001", "MAT-A", "MAT-A-NEW", affected_products=["PRODUCT_A"],
            customer_characteristic=False, owner_department="研发", due_date=date(2026, 9, 1),
            data_version="DEMO-ECN-V1",
        ).model_dump(mode="json")
    workflow = ECNWorkflow.model_validate(st.session_state.ecn_demo_workflow)
    next_steps = {
        ECNValidationStatus.CANDIDATE: (ECNValidationStatus.SPEC_REVIEW, "研发", {"drawing_comparison": "DEMO-DRAWING", "specification_comparison": "DEMO-SPEC"}),
        ECNValidationStatus.SPEC_REVIEW: (ECNValidationStatus.TRIAL, "研发", {"trial_plan": "DEMO-TRIAL-PLAN"}),
        ECNValidationStatus.TRIAL: (ECNValidationStatus.QUALITY_APPROVAL, "质量", {"trial_result": "PASS", "quality_report": "DEMO-QUALITY"}),
        ECNValidationStatus.QUALITY_APPROVAL: (ECNValidationStatus.APPROVED, "计划", {"effective_batch": "BATCH-2026-09", "traceability_rule": "OLD_FIRST"}),
    }
    st.write(f"当前状态：`{workflow.current_status.value}`")
    if workflow.current_status in next_steps and st.button("推进到下一验证节点"):
        target, role, evidence = next_steps[workflow.current_status]
        workflow = transition_ecn(
            workflow, target, actor=f"demo_{role}", role=role, evidence_updates=evidence,
            effective_batch=evidence.get("effective_batch"), traceability_rule=evidence.get("traceability_rule"),
        )
        st.session_state.ecn_demo_workflow = workflow.model_dump(mode="json")
        st.rerun()
    st.json(workflow.model_dump(mode="json"))

elif page == "预测调整工作流":
    evidence = [Evidence(source="DEMO_CUSTOMER_CONFIRMATION", description="客户项目确认变化", value="CONFIRMED")]
    workflow = create_adjustment_workflow(
        "FAW-DEMO-001", "PRODUCT_A", "STAT-001", requested_by="demo_planner",
        reason_code="CUSTOMER_COMMITMENT", evidence=evidence,
        effective_from=date(2026, 8, 3), effective_to=date(2026, 8, 31), due_date=date(2026, 7, 30),
    )
    workflow = transition_adjustment(workflow, WorkflowStatus.SUBMITTED, actor="demo_planner", role="计划")
    workflow = transition_adjustment(workflow, WorkflowStatus.COMMERCIAL_REVIEW, actor="demo_sales", role="销售")
    workflow = transition_adjustment(workflow, WorkflowStatus.SUPPLY_REVIEW, actor="demo_supply", role="计划")
    workflow = transition_adjustment(workflow, WorkflowStatus.PENDING_APPROVAL, actor="demo_supply", role="计划")
    workflow = transition_adjustment(workflow, WorkflowStatus.APPROVED, actor="demo_manager", role="计划经理", adjusted_version_id="ADJ-DEMO-001")
    st.json(workflow.model_dump(mode="json"))
    st.caption("人工调整必须经过商业和供应评审；实际需求产生前FVA保持PENDING_ACTUALS。")

elif page == "周度快照与趋势":
    store = SnapshotStore()
    for index, value in enumerate([12000, 11000, 9000, 7200, 6000]):
        store.add(WeeklySnapshot(
            snapshot_id=f"SNAP-{index}", as_of_week=date(2026, 6, 29) + timedelta(weeks=index),
            entity_type="MATERIAL", entity_id="MAT-A", plant="DEMO_PLANT",
            metrics={"excess_qty": float(value), "risk_value": float(value * 18)},
            source_versions={"inventory": f"DEMO-W{index}"},
        ))
    frame = pd.DataFrame([row.model_dump(mode="json") for row in store.list(entity_id="MAT-A")])
    metric_frame = pd.DataFrame([{"as_of_week": row["as_of_week"], **row["metrics"]} for row in frame.to_dict("records")])
    st.line_chart(metric_frame.set_index("as_of_week")[["excess_qty", "risk_value"]])
    st.json(store.trends("MAT-A", "excess_qty", 4).model_dump(mode="json"))

elif page == "Excel导入与字段映射":
    uploaded = st.file_uploader("上传Excel（.xlsx/.xlsm）", type=["xlsx", "xlsm"])
    target_fields = ["item_id", "week_start", "demand_qty", "plant", "customer"]
    if uploaded is None:
        sample_columns = ["物料编码", "周开始", "需求数量", "工厂", "客户"]
        st.write("自动映射预览：", suggest_field_mapping(sample_columns, target_fields))
        st.info("上传后只在内存返回校验结果，不写回ERP。")
    else:
        import tempfile
        from pathlib import Path
        suffix = Path(uploaded.name).suffix
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
                handle.write(uploaded.getvalue())
                temp_path = Path(handle.name)
            excel = pd.ExcelFile(temp_path)
            sheet = st.selectbox("工作表", excel.sheet_names)
            columns = list(pd.read_excel(temp_path, sheet_name=sheet, nrows=0).columns)
            suggested = suggest_field_mapping(columns, target_fields)
            mappings = [FieldMapping(target_field=field, source_column=suggested.get(field, ""), required=field in {"item_id", "week_start", "demand_qty"}, data_type="date" if field == "week_start" else ("float" if field == "demand_qty" else "str")) for field in target_fields]
            result = import_excel(temp_path, sheet_name=sheet, mappings=mappings, data_version="UPLOADED-DEMO")
            st.json(result.model_dump(mode="json", exclude={"rows"}))
            if result.rows:
                st.dataframe(pd.DataFrame(result.rows), use_container_width=True)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()

elif page == "任务提醒与升级":
    projection = project_inventory_by_week(demo_projection("CASE2", "MAT-B", "TARGET_PLANT"))
    risks = identify_projection_risks(projection, unit_cost=45, context={"supplier_delay": True})
    service = RiskTaskService()
    for risk in risks:
        service.create_from_risk(risk, assignee="demo_buyer", approvers=["采购经理", "计划经理"])
    as_of = st.date_input("模拟检查日期", value=date(2026, 8, 25))
    notifications = service.generate_notifications(as_of)
    st.dataframe(pd.DataFrame([task.model_dump(mode="json") for task in service.list_tasks()]), use_container_width=True)
    st.dataframe(pd.DataFrame([item.model_dump(mode="json") for item in notifications]), use_container_width=True)
    st.caption("本页只生成提醒和升级记录，不发送邮件、消息或外部通知。")

elif page == "供应商交期可靠性":
    records = demo_supplier_records()
    suppliers = sorted({record.supplier_id for record in records})
    results = [calculate_supplier_reliability(supplier, records) for supplier in suppliers]
    frame = pd.DataFrame([result.model_dump(mode="json") for result in results])
    st.dataframe(frame, use_container_width=True)
    st.bar_chart(frame.set_index("supplier_id")[["on_time_rate", "quantity_fill_rate", "lead_time_stability_score", "reliability_score"]])
    csv_download("下载供应商可靠性", frame, "supplier_reliability.csv")

elif page == "多情景库存成本优化":
    baseline = demo_projection("CASE3", "MAT-C", "DEMO_PLANT")
    scenarios = [
        DemandScenario(scenario_id="LOW", probability=0.2, demand_multiplier=0.8, description="需求下降"),
        DemandScenario(scenario_id="BASE", probability=0.5, demand_multiplier=1.0, description="基准"),
        DemandScenario(scenario_id="HIGH_DELAY", probability=0.3, demand_multiplier=1.15, po_delay_weeks=1, description="需求上升且PO延期"),
    ]
    decisions = [
        InventoryDecision(decision_id="NO_ACTION"),
        InventoryDecision(decision_id="ORDER_4000", order_qty=4000, order_week=baseline.weeks[1].week_start, action_cost=200),
        InventoryDecision(decision_id="TRANSFER_5000", transfer_in_qty=5000, transfer_week=baseline.weeks[1].week_start, action_cost=500),
    ]
    result = optimize_inventory_across_scenarios(baseline, scenarios=scenarios, decisions=decisions)
    st.write(f"推荐方案：`{result.selected_decision_id}`；状态：`{result.status.value}`")
    st.dataframe(pd.DataFrame([row.model_dump(mode="json") for row in result.evaluations]), use_container_width=True)
    st.json(result.expected_cost_by_decision)
