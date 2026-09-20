from __future__ import annotations

import streamlit as st

from ..services.control_tower import answer_control_tower_question, resolve_question_product_id
from .components import render_action_card, render_structured_response
from .control_tower import get_control_tower
from .theme import render_page_header, section_title


SUGGESTED_QUESTIONS = (
    "未来一个月哪些物料最可能缺料？",
    "为什么 MAT-B 有缺料风险？",
    "哪些 PO 或调拨动作需要优先处理？",
    "哪些物料存在冗余，可以取消 PO？",
    "哪个供应商的交付风险最高？",
)


def render_copilot() -> None:
    render_page_header(
        "AI Decision Copilot",
        "左侧提出业务问题，右侧查看结构化风险、证据、规则、动作和预期影响；不展示思维链，不让模型计算库存。",
        eyebrow="AI Copilot · Evidence → Decision",
        meta="确定性分析默认可用 · LLM 非必需",
    )
    if "sp_copilot_question" not in st.session_state:
        st.session_state.sp_copilot_question = SUGGESTED_QUESTIONS[1]
    if "sp_copilot_history" not in st.session_state:
        st.session_state.sp_copilot_history = []

    conversation, analysis = st.columns([0.38, 0.62], gap="large")
    with conversation:
        section_title("Conversation", "建议问题可一键运行")
        for index, question in enumerate(SUGGESTED_QUESTIONS):
            if st.button(question, key=f"copilot_suggest_{index}", use_container_width=True):
                st.session_state.sp_copilot_question = question
                st.session_state.sp_copilot_history.append({"role": "user", "content": question})
                st.rerun()
        st.markdown("---")
        for message in st.session_state.sp_copilot_history[-4:]:
            with st.chat_message(message["role"]):
                st.write(message["content"])
        if not st.session_state.sp_copilot_history:
            with st.chat_message("assistant"):
                st.write("我会先读取需求、库存、PO 和供应商证据，再用确定性服务形成建议。")
        custom_question = st.chat_input("输入供应链问题，例如：为什么 MAT-B 会缺料？")
        if custom_question:
            st.session_state.sp_copilot_question = custom_question
            st.session_state.sp_copilot_history.append({"role": "user", "content": custom_question})
            st.rerun()
        st.markdown(
            '<div class="sp-callout"><strong>职责边界：</strong>Agent 负责意图识别与解释；预测、库存、金额和动作影响全部来自 Python 服务。</div>',
            unsafe_allow_html=True,
        )

    question = str(st.session_state.sp_copilot_question)
    selected_product_id = resolve_question_product_id(question, "PRODUCT_B")
    snapshot = get_control_tower(selected_product_id)
    response = answer_control_tower_question(snapshot, question)
    with analysis:
        section_title(
            "Analysis Workspace",
            f"{selected_product_id} · Summary · Evidence · Root Cause · Recommendation · Impact",
        )
        render_structured_response(response)
        validation = next(
            (item for item in snapshot.action_validations if item.validation_id == response.action_validation_id),
            None,
        )
        if validation:
            st.markdown("---")
            render_action_card(validation, key_prefix="copilot_action")
        st.caption(
            "Evidence Used：需求历史、周度库存投影、在途 PO、供应商交付记录；"
            "输出为 Demo 决策支持，不连接或写回 ERP。"
        )
