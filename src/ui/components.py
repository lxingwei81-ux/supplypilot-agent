from __future__ import annotations

from html import escape

import streamlit as st

from ..models import (
    ActionValidation,
    ControlTowerKPI,
    ControlTowerStatus,
    InsightCard,
    StructuredCopilotResponse,
)
from .navigation import navigate_to
from .theme import RISK_COLORS


STATUS_LABELS = {
    "HEALTHY": "健康",
    "WATCH": "关注",
    "RISK": "高风险",
    "CRITICAL": "严重",
    "UNKNOWN": "无数据",
}

RISK_LEVEL_TO_STATUS = {
    "LOW": "HEALTHY",
    "MEDIUM": "WATCH",
    "HIGH": "RISK",
    "CRITICAL": "CRITICAL",
}


def _status_value(status: ControlTowerStatus | str) -> str:
    return status.value if isinstance(status, ControlTowerStatus) else str(status)


def badge_html(status: ControlTowerStatus | str, label: str | None = None) -> str:
    value = _status_value(status)
    color = RISK_COLORS.get(value, RISK_COLORS["UNKNOWN"])
    text = label or STATUS_LABELS.get(value, value)
    return f'<span class="sp-badge" style="color:{color}"><span class="sp-dot"></span>{escape(text)}</span>'


def render_kpi_strip(kpis: list[ControlTowerKPI], *, key_prefix: str) -> None:
    columns = st.columns(len(kpis), gap="small")
    for index, (column, kpi) in enumerate(zip(columns, kpis)):
        status = _status_value(kpi.status)
        accent = RISK_COLORS.get(status, RISK_COLORS["UNKNOWN"])
        with column:
            st.markdown(
                f"""
                <div class="sp-card sp-kpi" style="--sp-accent:{accent}">
                  <div class="sp-kpi-label">{escape(kpi.label)}</div>
                  <div class="sp-kpi-value">{escape(kpi.display_value)}</div>
                  <div class="sp-kpi-detail">{escape(kpi.detail)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if kpi.drilldown_page and st.button(
                "查看详情 →",
                key=f"{key_prefix}_{index}_{kpi.key}",
                use_container_width=True,
            ):
                navigate_to(kpi.drilldown_page)


def render_insight_card(insight: InsightCard, *, key: str) -> None:
    st.markdown(
        f"""
        <div class="sp-card sp-insight">
          {badge_html(insight.status)}
          <h3>{escape(insight.title)}</h3>
          <p><strong>发生了什么：</strong>{escape(insight.what_happened)}</p>
          <p><strong>为什么：</strong>{escape(insight.why)}</p>
          <p><strong>建议：</strong>{escape(insight.recommendation)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("查看分析", key=key, use_container_width=True):
        navigate_to(insight.drilldown_page, material=insight.object_id)


def render_action_card(validation: ActionValidation, *, key_prefix: str) -> None:
    action = validation.action
    before = validation.baseline
    after = validation.scenario
    approval = action.approval
    state_key = f"sp_action_state_{action.action_id}"
    current_state = st.session_state.get(state_key, "AI_RECOMMENDED")
    state_label = {
        "AI_RECOMMENDED": "AI 已建议",
        "APPROVED": "已批准（演示）",
        "MODIFY": "待修改（演示）",
        "REJECTED": "已拒绝（演示）",
    }[current_state]
    status = "CRITICAL" if not validation.recommended else ("WATCH" if validation.residual_risks else "HEALTHY")
    gate_label = "拒绝" if not validation.recommended else ("通过（部分缓解）" if validation.residual_risks else "通过")
    badge_label = (
        "制造新缺料"
        if validation.creates_new_shortage
        else ("未制造新缺料 · 仍有残余风险" if validation.residual_risks else "未制造新缺料")
    )
    residual_html = ""
    if validation.residual_risks:
        residual_html = (
            '<p class="sp-subtle"><strong>残余风险：</strong>'
            + escape("；".join(validation.residual_risks))
            + "</p>"
        )
    related_html = ""
    if validation.related_entity_results:
        related_html = '<p class="sp-subtle"><strong>关联实体复核：</strong>' + escape("；".join(
            f"{item.material_id}@{item.plant} 最大缺口 {item.maximum_shortage_qty:,.0f}，"
            f"首次低安全库存 {item.first_below_safety_stock_week or '无'}"
            for item in validation.related_entity_results
        )) + "</p>"
    st.markdown(
        f"""
        <div class="sp-card">
          <div class="sp-action-title">
            <div><div class="sp-subtle">RECOMMENDED ACTION</div><h3>{escape(action.material_id)} · {escape(action.plant)}</h3></div>
            <span class="sp-action-type">{escape(action.action_type.value)}</span>
          </div>
          <div class="sp-action-grid">
            <div class="sp-action-cell"><span>动作数量</span><strong>{action.quantity:,.0f}</strong></div>
            <div class="sp-action-cell"><span>最大缺口</span><strong>{before.maximum_shortage_qty:,.0f} → {after.maximum_shortage_qty:,.0f}</strong></div>
            <div class="sp-action-cell"><span>期末冗余</span><strong>{before.ending_excess_qty:,.0f} → {after.ending_excess_qty:,.0f}</strong></div>
            <div class="sp-action-cell"><span>安全门禁</span><strong>{escape(gate_label)}</strong></div>
          </div>
          <p class="sp-subtle">{escape(action.reason)} · 责任部门：{escape(action.owner_department)} · 截止：{action.due_date}</p>
          <div class="sp-flow"><b>风险识别</b> → <b>动作建议</b> → <b>{escape(state_label)}</b> → <b>外部系统人工执行</b></div>
          {badge_html(status, badge_label)}
          {residual_html}
          {related_html}
        </div>
        """,
        unsafe_allow_html=True,
    )
    if approval:
        st.caption(f"审批对象：{'、'.join(approval.approvers)}；状态：{approval.status.value}。本操作只更新前端演示状态，不写回 ERP。")
    c1, c2, c3 = st.columns(3)
    if c1.button("批准", key=f"{key_prefix}_approve", type="primary", use_container_width=True, disabled=not validation.recommended):
        st.session_state[state_key] = "APPROVED"
        st.rerun()
    if c2.button("修改", key=f"{key_prefix}_modify", use_container_width=True):
        st.session_state[state_key] = "MODIFY"
        st.rerun()
    if c3.button("拒绝", key=f"{key_prefix}_reject", use_container_width=True):
        st.session_state[state_key] = "REJECTED"
        st.rerun()
    if current_state == "MODIFY":
        st.info("请进入“情景模拟”调整数量并重新运行库存投影；未重算前不会形成新的建议。")


def render_structured_response(response: StructuredCopilotResponse) -> None:
    status = RISK_LEVEL_TO_STATUS.get(response.risk_level.value, "UNKNOWN")
    st.markdown(f"### 分析结论　{badge_html(status, response.risk_level.value)}", unsafe_allow_html=True)
    st.markdown(f'<div class="sp-callout">{escape(response.summary)}</div>', unsafe_allow_html=True)
    st.markdown("#### 业务证据")
    evidence_html = "".join(
        f'<div class="sp-evidence"><span>{escape(item.label)}</span><strong>{escape(item.value)}</strong><span>{escape(item.source)} · {escape(item.source_version)}</span></div>'
        for item in response.evidence
    )
    st.markdown(f'<div class="sp-evidence-grid">{evidence_html}</div>', unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        st.markdown("#### 根因")
        for item in response.root_causes:
            st.markdown(f"- {item}")
        st.markdown("#### 触发规则")
        for item in response.business_rules:
            st.markdown(f"- `{item}`")
    with right:
        st.markdown("#### 建议动作")
        for item in response.recommendations:
            st.markdown(f"- {item}")
        st.markdown("#### 预期影响")
        for item in response.expected_impact:
            st.markdown(f"- {item}")
    if response.limitations:
        st.caption("限制：" + "；".join(response.limitations))
