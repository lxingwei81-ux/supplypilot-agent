from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from ..models import ControlTowerSnapshot
from ..services.control_tower import build_demo_control_tower_snapshot
from .charts import demand_forecast_chart, inventory_heatmap_chart, inventory_projection_chart
from .components import badge_html, render_action_card, render_insight_card, render_kpi_strip
from .navigation import navigate_to
from .theme import render_page_header, section_title


@st.cache_data(show_spinner=False)
def cached_control_tower(selected_product_id: str) -> dict:
    return build_demo_control_tower_snapshot(selected_product_id).model_dump(mode="json")


def get_control_tower(selected_product_id: str = "PRODUCT_B") -> ControlTowerSnapshot:
    return ControlTowerSnapshot.model_validate(cached_control_tower(selected_product_id))


def _risk_frame(snapshot: ControlTowerSnapshot) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "优先级": row.priority.value,
            "物料": row.material_id,
            "工厂": row.plant,
            "问题": row.issue,
            "影响数量": row.impact_quantity,
            "风险金额": row.impact_value,
            "风险日期": row.risk_date,
            "根因": row.root_cause,
            "建议动作": row.recommended_action.value,
            "最晚处理": row.latest_action_date,
        }
        for row in snapshot.risk_queue
    ])


@st.dialog("SKU 360° 详情", width="large")
def show_sku_detail(snapshot_payload: dict, material_id: str) -> None:
    snapshot = ControlTowerSnapshot.model_validate(snapshot_payload)
    projections = [item for item in snapshot.projections if item.material_id == material_id]
    risks = [item for item in snapshot.risks if item.material_id == material_id]
    actions = [item for item in snapshot.action_validations if item.action.material_id == material_id]
    st.markdown(f"## {material_id}")
    if not projections:
        st.info("当前筛选没有周度投影数据。")
        return
    projection = projections[0]
    first_row = st.columns(2)
    first_row[0].metric("工厂", projection.plant)
    first_row[1].metric("最大缺口", f"{projection.maximum_shortage_qty:,.0f}")
    second_row = st.columns(2)
    second_row[0].metric("首次低于安全库存", str(projection.first_below_safety_stock_week or "无"))
    second_row[1].metric("首次缺料", str(projection.first_shortage_week or "无"))
    st.altair_chart(inventory_projection_chart(projection), use_container_width=True)
    if risks:
        risk = risks[0]
        st.markdown(
            f"**风险与根因**　{badge_html(risk.level.value.replace('HIGH', 'RISK').replace('MEDIUM', 'WATCH').replace('LOW', 'HEALTHY'), risk.level.value)}",
            unsafe_allow_html=True,
        )
        st.write("；".join(risk.root_causes))
        st.caption(f"证据版本：{risk.source_version} · 责任部门：{risk.owner_department} · 最晚处理：{risk.latest_action_date}")
    if actions:
        st.markdown("### 已校验动作")
        render_action_card(actions[0], key_prefix=f"drawer_{material_id}")


def render_control_tower() -> None:
    header_snapshot = get_control_tower("PRODUCT_B")
    render_page_header(
        "Supply Chain Control Tower",
        "从需求信号到采购动作：识别风险、解释原因、验证影响，并把高影响决策交给人工审批。",
        eyebrow="Overview · See → Predict → Explain → Decide → Act",
        meta=f"演示快照：{header_snapshot.as_of.date()} · Asia/Shanghai",
    )

    filter_columns = st.columns([1.25, 1, 1, 1.3])
    product = filter_columns[0].selectbox(
        "需求对象",
        ["PRODUCT_B", "PRODUCT_A"],
        format_func=lambda value: {"PRODUCT_B": "PRODUCT_B · 上升场景", "PRODUCT_A": "PRODUCT_A · 稳定场景"}[value],
        key="ct_product",
    )
    horizon = filter_columns[1].selectbox("预测周期", [4, 8, 13, 26], index=2, format_func=lambda value: f"未来 {value} 周")
    risk_filter = filter_columns[2].multiselect(
        "风险等级",
        ["CRITICAL", "HIGH", "MEDIUM", "LOW"],
        default=["CRITICAL", "HIGH", "MEDIUM"],
    )
    detail_material = filter_columns[3].selectbox("SKU 360°", ["MAT-B", "MAT-C", "MAT-A"])
    snapshot = get_control_tower(product)
    auto_detail = st.query_params.get("detail")
    open_detail = filter_columns[3].button("打开详情", use_container_width=True)
    if auto_detail in {"MAT-A", "MAT-B", "MAT-C"}:
        del st.query_params["detail"]
        show_sku_detail(snapshot.model_dump(mode="json"), str(auto_detail))
    elif open_detail:
        show_sku_detail(snapshot.model_dump(mode="json"), detail_material)

    blocker_count = sum(
        1
        for issue in (snapshot.legacy_data_quality.issues if snapshot.legacy_data_quality else [])
        if issue.blocking
    )
    if blocker_count:
        st.markdown(
            f'<div class="sp-callout sp-warning"><strong>数据边界：</strong>控制塔所用 DEMO-* 数据包校验通过；旧 V2 兼容数据存在 {blocker_count} 个阻断项且未参与本页计算。生产流程会阻断受影响计算。</div>',
            unsafe_allow_html=True,
        )
    st.caption("口径说明：需求预测图与物料库存异常为两个独立、带版本号的 Demo 场景；本组合视图不代表已完成逐周 BOM 串联。")

    section_title("组合健康度", "指标来自确定性服务，不将 WAPE 包装成“准确率”")
    render_kpi_strip(snapshot.kpis, key_prefix="ct_kpi")

    left, right = st.columns([1.05, 0.95], gap="large")
    with left:
        section_title("Actual vs Forecast", f"{product} · {horizon} 周 · 阴影为规则情景区间")
        if snapshot.demand_trend:
            st.altair_chart(demand_forecast_chart(snapshot.demand_trend, horizon_weeks=horizon), use_container_width=True)
        else:
            st.info("当前筛选没有需求趋势数据。")
    with right:
        section_title("Inventory Risk Heatmap", "单元格数字为周末投影库存")
        cells = snapshot.inventory_heatmap
        if risk_filter:
            risk_map = {"CRITICAL": "CRITICAL", "HIGH": "RISK", "MEDIUM": "WATCH", "LOW": "HEALTHY"}
            selected_statuses = {risk_map[value] for value in risk_filter}
            selected_rows = {cell.material_id for cell in cells if cell.status.value in selected_statuses}
            cells = [cell for cell in cells if cell.material_id in selected_rows]
        if cells:
            st.altair_chart(inventory_heatmap_chart(cells), use_container_width=True)
        else:
            st.info("所选风险等级没有数据。")

    section_title("Top Supply Risks", "选择记录后可打开 SKU 360° 详情")
    risk_frame = _risk_frame(snapshot)
    if risk_filter:
        risk_frame = risk_frame[risk_frame["优先级"].isin(risk_filter)]
    if risk_frame.empty:
        st.info("所选风险等级没有风险记录。")
    else:
        event = st.dataframe(
            risk_frame,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "影响数量": st.column_config.NumberColumn(format="%,.0f"),
                "风险金额": st.column_config.NumberColumn(format="¥%,.0f"),
                "根因": st.column_config.TextColumn(width="large"),
            },
            key="ct_risk_table",
        )
        selected_rows = event.selection.rows if event else []
        selected_material = str(risk_frame.iloc[selected_rows[0]]["物料"]) if selected_rows else str(risk_frame.iloc[0]["物料"])
        b1, b2, _ = st.columns([1, 1, 4])
        if b1.button(f"查看 {selected_material}", use_container_width=True):
            show_sku_detail(snapshot.model_dump(mode="json"), selected_material)
        if b2.button("进入库存控制台", use_container_width=True):
            navigate_to("库存控制台", material=selected_material)

    section_title("Executive AI Insights", "What happened · Why · What should we do")
    insight_columns = st.columns(3, gap="small")
    for index, (column, insight) in enumerate(zip(insight_columns, snapshot.insights)):
        with column:
            render_insight_card(insight, key=f"ct_insight_{index}")

    section_title("Procurement Action Center", "动作已重算目标与关联工厂；批准按钮只更新演示状态")
    action_columns = st.columns(2, gap="large")
    for index, (column, validation) in enumerate(zip(action_columns, snapshot.action_validations)):
        with column:
            render_action_card(validation, key_prefix=f"ct_action_{index}")

    with st.expander("数据来源、公式与限制"):
        st.code("EndingInventory = BeginningInventory + POReceipt + ProductionReceipt + TransferIn - GrossDemand - ReservedDemand - TransferOut")
        st.code("Excess = max(0, EndingInventory - SafetyStock)")
        st.write("来源版本：", snapshot.source_versions)
        for limitation in snapshot.limitations:
            st.markdown(f"- {limitation}")
        st.download_button(
            "下载控制塔 JSON",
            json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, indent=2),
            "supplypilot_control_tower.json",
            "application/json",
        )
