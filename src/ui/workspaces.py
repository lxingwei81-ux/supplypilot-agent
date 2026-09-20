from __future__ import annotations

from datetime import date, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from ..config import load_rules
from ..demo import demo_histories, demo_po_options
from ..models import (
    ControlTowerKPI,
    ControlTowerStatus,
    DemandTrendPoint,
    RiskLevel,
)
from ..services.demand_classification import classify_demand
from ..services.forecasting import generate_forecast
from .charts import demand_forecast_chart, inventory_projection_chart
from .components import badge_html, render_action_card, render_kpi_strip
from .control_tower import get_control_tower, show_sku_detail
from .theme import render_page_header, section_title


@st.cache_data(show_spinner=False)
def _demand_workspace_payload(item_id: str) -> dict:
    histories, metadata = demo_histories()
    history = histories[item_id]
    meta = metadata[item_id]
    classification = classify_demand(
        {item_id: history},
        unit_costs={item_id: float(meta["unit_cost"])},
        lifecycles={item_id: str(meta["lifecycle"])},
        source_version=str(meta["data_version"]),
    )[0]
    result = generate_forecast(
        item_id,
        history,
        classification,
        last_history_week=date.fromisoformat(str(meta["last_history_week"])),
        history_source=str(meta["data_version"]),
        stockout_unit_cost=float(meta["unit_cost"]),
    )
    last_week = date.fromisoformat(str(meta["last_history_week"]))
    visible_history = history[-20:]
    first_week = last_week - timedelta(weeks=len(visible_history) - 1)
    trend = [DemandTrendPoint(
        item_id=item_id,
        week_start=first_week + timedelta(weeks=index),
        actual_qty=quantity,
        period_type="HISTORY",
        source_version=str(meta["data_version"]),
    ) for index, quantity in enumerate(visible_history)]
    trend.extend(DemandTrendPoint(
        item_id=item_id,
        week_start=point.week_start,
        forecast_qty=point.baseline_qty,
        lower_bound=point.lower_bound,
        upper_bound=point.upper_bound,
        period_type="FORECAST",
        source_version=point.source_version,
    ) for point in result.points)
    return {
        "classification": classification.model_dump(mode="json"),
        "forecast": result.model_dump(mode="json"),
        "trend": [point.model_dump(mode="json") for point in trend],
    }


def render_demand_workspace() -> None:
    cfg = load_rules()
    render_page_header(
        "Demand Forecast Intelligence",
        "以历史基线、滚动回测和规则情景区间支持需求评审；人工判断只处理有业务证据的高影响例外。",
        eyebrow="Demand Forecast · First Line of Defense",
        meta="52 周历史 · 4/8/13/26 周预测",
    )
    histories, _ = demo_histories()
    filters = st.columns([1.2, 1, 1, 1])
    item_id = filters[0].selectbox("需求对象", list(histories), index=list(histories).index("PRODUCT_B"))
    horizon = filters[1].selectbox("预测周期", [4, 8, 13, 26], index=2, format_func=lambda value: f"{value} 周")
    filters[2].selectbox("工厂", ["全部（Demo）"], disabled=True)
    filters[3].selectbox("版本", ["最新统计预测"], disabled=True)
    payload = _demand_workspace_payload(item_id)
    from ..models import DemandClassification, ForecastResult

    classification = DemandClassification.model_validate(payload["classification"])
    result = ForecastResult.model_validate(payload["forecast"])
    trend = [DemandTrendPoint.model_validate(point) for point in payload["trend"]]
    selected = result.selected_metrics
    kpis = [
        ControlTowerKPI(
            key="model", label="最佳模型", value=0, display_value=result.selected_model or "N/A",
            detail=f"{classification.xyz_class.value} · {classification.intermittency_class.value}",
            status=ControlTowerStatus.HEALTHY,
        ),
        ControlTowerKPI(
            key="wape", label="WAPE", value=selected.wape or 0, display_value="N/A" if selected.wape is None else f"{selected.wape:.1%}",
            detail="滚动起点回测；越低越好",
            status=(
                ControlTowerStatus.HEALTHY
                if selected.wape is not None and selected.wape <= cfg.control_tower.item_wape_healthy_threshold
                else ControlTowerStatus.RISK
            ),
        ),
        ControlTowerKPI(
            key="bias", label="Bias", value=selected.bias or 0, display_value="N/A" if selected.bias is None else f"{selected.bias:+.1%}",
            detail="正值高估，负值低估",
            status=(
                ControlTowerStatus.WATCH
                if abs(selected.bias or 0) > cfg.control_tower.item_bias_watch_threshold
                else ControlTowerStatus.HEALTHY
            ),
        ),
        ControlTowerKPI(
            key="horizon", label=f"未来 {horizon} 周", value=result.horizon_totals[horizon], display_value=f"{result.horizon_totals[horizon]:,.0f}",
            detail=f"置信等级 {result.confidence.value}", status=ControlTowerStatus.WATCH if result.requires_manual_review else ControlTowerStatus.HEALTHY,
        ),
    ]
    render_kpi_strip(kpis, key_prefix="demand_kpi")
    section_title("Actual vs Forecast", "历史实际 · 未来预测 · 规则情景区间 · 预测起点")
    st.altair_chart(demand_forecast_chart(trend, horizon_weeks=horizon), use_container_width=True)
    st.caption("阴影是由历史波动和配置规则生成的情景区间，不是未经校准的统计置信区间。")
    left, right = st.columns([1.25, 0.75], gap="large")
    with left:
        section_title("候选模型回测", "同一滚动窗口、无未来数据泄漏")
        metrics = pd.DataFrame([metric.model_dump(mode="json") for metric in result.candidate_metrics])
        st.dataframe(
            metrics[["model_name", "wape", "bias", "mae", "model_score", "backtest_count", "data_coverage"]].sort_values("model_score"),
            use_container_width=True,
            hide_index=True,
            column_config={
                "wape": st.column_config.NumberColumn("WAPE", format="percent"),
                "bias": st.column_config.NumberColumn("Bias", format="percent"),
                "model_score": st.column_config.NumberColumn("综合得分", format="%.3f"),
                "data_coverage": st.column_config.ProgressColumn("覆盖率", min_value=0, max_value=1, format="percent"),
            },
        )
    with right:
        section_title("分类与评审策略")
        st.markdown(
            f"""
            <div class="sp-card">
              <p><strong>ABC / XYZ</strong><br>{classification.abc_class.value} / {classification.xyz_class.value}</p>
              <p><strong>ADI / CV²</strong><br>{classification.adi if classification.adi is not None else 'N/A'} / {classification.cv_squared if classification.cv_squared is not None else 'N/A'}</p>
              <p><strong>生命周期</strong><br>{classification.lifecycle.value}</p>
              <p><strong>候选模型</strong><br>{' / '.join(classification.recommended_forecast_models) or '人工评审'}</p>
              <p><strong>库存策略</strong><br>{classification.inventory_strategy}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if result.requires_manual_review:
            st.warning("需要人工复核：" + "；".join(result.review_reasons))
        else:
            st.success("当前统计基线满足配置的自动发布条件；业务例外仍需有证据的人工评审。")
        st.caption(f"来源：{result.history_source} · 规则：{result.rules_version} · 计算：{result.calculated_at.isoformat()}")


def render_inventory_workspace() -> None:
    snapshot = get_control_tower("PRODUCT_B")
    render_page_header(
        "Inventory Control",
        "用逐周投影识别首次缺料、低安全库存和决策冗余，并在建议动作后重新计算供需水位。",
        eyebrow="Inventory · Second Line of Defense",
        meta="13 周逐周投影 · 动作前后校验",
    )
    material_options = [projection.material_id for projection in snapshot.projections]
    requested = st.query_params.get("material")
    default_index = material_options.index(requested) if requested in material_options else material_options.index("MAT-B")
    filters = st.columns([1.2, 1.2, 1, 1])
    material = filters[0].selectbox("物料", material_options, index=default_index)
    projection = next(item for item in snapshot.projections if item.material_id == material)
    filters[1].selectbox("工厂", [projection.plant], disabled=True)
    filters[2].selectbox("计划周期", ["13 周"], disabled=True)
    filters[3].selectbox("视图", ["基准投影"], disabled=True)
    matching_risks = [risk for risk in snapshot.risks if risk.material_id == material]
    risk = matching_risks[0] if matching_risks else None
    ending = projection.points[-1]
    kpis = [
        ControlTowerKPI(key="initial", label="初始有效库存", value=projection.initial_available_inventory, display_value=f"{projection.initial_available_inventory:,.0f}", detail="已扣冻结、质检与分配", status=ControlTowerStatus.HEALTHY),
        ControlTowerKPI(key="first_below", label="首次低安全库存", value=0, display_value=str(projection.first_below_safety_stock_week or "无"), detail=f"安全库存 {ending.safety_stock:,.0f}", status=ControlTowerStatus.RISK if projection.first_below_safety_stock_week else ControlTowerStatus.HEALTHY),
        ControlTowerKPI(key="first_short", label="首次缺料", value=0, display_value=str(projection.first_shortage_week or "无"), detail=f"最大缺口 {projection.maximum_shortage_qty:,.0f}", status=ControlTowerStatus.CRITICAL if projection.first_shortage_week else ControlTowerStatus.HEALTHY),
        ControlTowerKPI(key="excess", label="期末决策冗余", value=projection.ending_excess_qty, display_value=f"{projection.ending_excess_qty:,.0f}", detail=f"期末库存 {ending.ending_inventory:,.0f}", status=ControlTowerStatus.WATCH if projection.ending_excess_qty else ControlTowerStatus.HEALTHY),
    ]
    render_kpi_strip(kpis, key_prefix="inventory_kpi")
    section_title("Projected Inventory", "蓝：周末库存 · 黄：安全库存 · 红：零库存 · 绿三角：PO 到货")
    st.altair_chart(inventory_projection_chart(projection), use_container_width=True)
    with st.expander("Explain · 投影库存如何计算"):
        st.code("AvailableInventory = OnHand - Frozen - QualityHold - Allocated + ReusableReturn")
        st.code("EndingInventory[t] = Beginning[t] + PO[t] + Production[t] + TransferIn[t] - Demand[t] - TransferOut[t]")
        st.code("NetAvailable[t] = EndingInventory[t] - SafetyStock[t]")
        st.caption("逐周递推能够识别总量充足但中间周缺料；静态“库存 + 总 PO - 总需求”不能替代此计算。")
    left, right = st.columns([0.8, 1.2], gap="large")
    with left:
        section_title("风险诊断")
        if risk:
            status = {RiskLevel.CRITICAL: "CRITICAL", RiskLevel.HIGH: "RISK", RiskLevel.MEDIUM: "WATCH", RiskLevel.LOW: "HEALTHY"}[risk.level]
            st.markdown(f"{badge_html(status, risk.level.value)}", unsafe_allow_html=True)
            st.markdown(f"**{risk.risk_type.value}** · {risk.quantity:,.0f} 件 · ¥{risk.value:,.0f}")
            for cause in risk.root_causes:
                st.markdown(f"- {cause}")
            st.caption(f"责任：{risk.owner_department} · 最晚处理：{risk.latest_action_date} · 来源：{risk.source_version}")
        else:
            st.success("当前场景未触发结构化风险规则。")
        if st.button("打开 SKU 360°", use_container_width=True):
            show_sku_detail(snapshot.model_dump(mode="json"), material)
    with right:
        section_title("动作前后验证")
        action = next((item for item in snapshot.action_validations if item.action.material_id == material), None)
        if action:
            render_action_card(action, key_prefix=f"inventory_action_{material}")
        else:
            st.info("当前物料没有预置动作。请在情景模拟页创建动作并重新投影。")
    section_title("每周明细", "可下载核对每一周的供需变化")
    frame = pd.DataFrame([point.model_dump(mode="json") for point in projection.points])
    st.dataframe(frame, use_container_width=True, hide_index=True)
    st.download_button("下载投影 CSV", frame.to_csv(index=False).encode("utf-8-sig"), f"projection_{material}.csv", "text/csv")


def _po_timeline_chart() -> alt.Chart:
    events = pd.DataFrame([
        {"event": "计划快照", "date": "2026-07-21", "status": "INFO", "detail": "供应链评审"},
        {"event": "调拨建议到货", "date": "2026-08-10", "status": "HEALTHY", "detail": "TRANSFER 1,800"},
        {"event": "首次缺料", "date": "2026-08-24", "status": "CRITICAL", "detail": "MAT-B -1,500"},
        {"event": "PO 计划到货", "date": "2026-08-31", "status": "RISK", "detail": "PO +5,000（晚于风险周）"},
    ])
    events["date"] = pd.to_datetime(events["date"])
    colors = alt.Scale(domain=["INFO", "HEALTHY", "RISK", "CRITICAL"], range=["#2563EB", "#15803D", "#EA580C", "#DC2626"])
    line = alt.Chart(pd.DataFrame({"start": [events["date"].min()], "end": [events["date"].max()]})).mark_rule(color="#CBD5E1", strokeWidth=3).encode(x="start:T", x2="end:T")
    points = alt.Chart(events).mark_point(size=180, filled=True).encode(
        x=alt.X("date:T", title=None, axis=alt.Axis(format="%m/%d", labelAngle=0)),
        y=alt.value(70),
        color=alt.Color("status:N", scale=colors, legend=None),
        tooltip=[alt.Tooltip("date:T", title="日期", format="%Y-%m-%d"), alt.Tooltip("event:N", title="事件"), alt.Tooltip("detail:N", title="说明")],
    )
    labels = alt.Chart(events).mark_text(dy=-22, fontSize=11, fontWeight="bold").encode(x="date:T", y=alt.value(70), text="event:N", color=alt.Color("status:N", scale=colors, legend=None))
    return (line + points + labels).properties(height=150).configure_view(strokeWidth=0)


def render_procurement_workspace() -> None:
    snapshot = get_control_tower("PRODUCT_B")
    render_page_header(
        "Procurement Decision Workspace",
        "把风险队列转化为可验证的 PO、调拨和供应商协同行动；AI 推荐，人工决策。",
        eyebrow="Procurement · Third Line of Defense",
        meta="建议与审批 · 不执行 ERP 写回",
    )
    approval_actions = sum(1 for item in snapshot.action_validations if item.approval_required)
    risky_suppliers = sum(1 for item in snapshot.suppliers if item.grade in {"C", "D"})
    late_risk = next(risk for risk in snapshot.risks if risk.material_id == "MAT-B")
    kpis = [
        ControlTowerKPI(key="validated", label="已校验动作", value=len(snapshot.action_validations), display_value=f"{len(snapshot.action_validations)} 项", detail="已完成动作前后投影", status=ControlTowerStatus.HEALTHY),
        ControlTowerKPI(key="approval", label="待人工审批", value=approval_actions, display_value=f"{approval_actions} 项", detail="高影响动作不可自动执行", status=ControlTowerStatus.WATCH),
        ControlTowerKPI(key="late", label="供应晚到敞口", value=late_risk.value, display_value=f"¥{late_risk.value / 1000:,.0f}K", detail=f"{late_risk.material_id} · {late_risk.first_event_week}", status=ControlTowerStatus.CRITICAL),
        ControlTowerKPI(key="supplier", label="供应商风险", value=risky_suppliers, display_value=f"{risky_suppliers} 家", detail="评级 C / D", status=ControlTowerStatus.RISK if risky_suppliers else ControlTowerStatus.HEALTHY),
    ]
    render_kpi_strip(kpis, key_prefix="proc_kpi")
    tab_actions, tab_timeline, tab_suppliers, tab_po = st.tabs(["Action Center", "MAT-B 时间轴", "供应商 Scorecard", "开放 PO"])
    with tab_actions:
        section_title("Recommended Actions", "先重算，再建议；所有批准状态仅保存在当前会话")
        columns = st.columns(2, gap="large")
        for index, (column, validation) in enumerate(zip(columns, snapshot.action_validations)):
            with column:
                render_action_card(validation, key_prefix=f"proc_action_{index}")
    with tab_timeline:
        section_title("PO & Risk Timeline", "MAT-B · 到货晚于需求窗口时直接标红")
        st.altair_chart(_po_timeline_chart(), use_container_width=True)
        st.markdown('<div class="sp-callout sp-warning"><strong>诊断：</strong>MAT-B 首次缺料为 2026-08-24，而 5,000 件 PO 计划于 2026-08-31 到货。跨厂调拨 1,800 件可推迟首次缺料，同时保留来源工厂安全库存，但目标侧仍有 7,000 件残余缺口。</div>', unsafe_allow_html=True)
    with tab_suppliers:
        section_title("Supplier Scorecard", "综合分来自 OTD、数量满足率、交期稳定性和确认遵从率")
        supplier_frame = pd.DataFrame([supplier.model_dump(mode="json") for supplier in snapshot.suppliers])
        st.dataframe(
            supplier_frame[["supplier_id", "grade", "sample_count", "on_time_rate", "quantity_fill_rate", "mean_lead_time_days", "mean_lateness_days", "reliability_score", "warnings"]],
            use_container_width=True,
            hide_index=True,
            column_config={
                "on_time_rate": st.column_config.ProgressColumn("OTD", min_value=0, max_value=1, format="percent"),
                "quantity_fill_rate": st.column_config.ProgressColumn("数量满足率", min_value=0, max_value=1, format="percent"),
                "reliability_score": st.column_config.ProgressColumn("综合分", min_value=0, max_value=1, format="percent"),
                "warnings": st.column_config.ListColumn("数据警告"),
            },
        )
    with tab_po:
        section_title("Open PO Flexibility", "单据级候选；安全性结论必须再经过周度动作校验")
        frame = pd.DataFrame([option.model_dump(mode="json") for option in demo_po_options()])
        st.dataframe(frame, use_container_width=True, hide_index=True)
        st.caption("PO 优化器提供取消/延期候选；控制塔动作卡调用 validate_action_impact() 后才声称“不制造新缺料”。")
