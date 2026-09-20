from __future__ import annotations

from collections.abc import Mapping, Sequence

import streamlit as st


NAV_MODULES: Mapping[str, Sequence[str]] = {
    "Overview": ("管理驾驶舱", "数据质量", "周度快照与趋势"),
    "Demand Forecast": (
        "需求预测",
        "需求分类",
        "预测对比与回测",
        "预测版本及人工调整",
        "预测调整工作流",
    ),
    "Inventory": (
        "库存控制台",
        "周度库存投影",
        "缺料风险",
        "库存冗余",
        "BOM需求拆解",
        "情景模拟",
        "多情景库存成本优化",
    ),
    "Procurement": (
        "采购工作台",
        "PO行动清单",
        "共用料ATP与客户分配",
        "多工厂调拨优化",
        "采购成本与批量优化",
        "供应商交期可靠性",
        "ECN验证状态机",
        "审批与任务跟踪",
        "任务提醒与升级",
        "Excel导入与字段映射",
    ),
    "AI Copilot": ("AI Copilot",),
}

PAGE_ALIASES = {
    "智能问答（兼容页）": "AI Copilot",
}

MODULE_LABELS = {
    "Overview": "Overview · 控制塔",
    "Demand Forecast": "Demand · 需求预测",
    "Inventory": "Inventory · 库存",
    "Procurement": "Procurement · 采购协同",
    "AI Copilot": "AI Copilot · 决策助手",
}


def canonicalize_page(page: str | None) -> str:
    if not page:
        return "管理驾驶舱"
    return PAGE_ALIASES.get(page, page)


def module_for_page(page: str | None) -> str:
    canonical = canonicalize_page(page)
    for module, pages in NAV_MODULES.items():
        if canonical in pages:
            return module
    return "Overview"


def all_pages() -> list[str]:
    return [page for pages in NAV_MODULES.values() for page in pages]


def render_navigation(requested_page: str | None) -> str:
    pending_target = st.session_state.pop("_sp_nav_target", None)
    if pending_target:
        requested_page = str(pending_target)
        pending_module = module_for_page(requested_page)
        st.session_state["sp_nav_module"] = pending_module
        st.session_state[f"sp_nav_page_{pending_module}"] = canonicalize_page(requested_page)
    canonical = canonicalize_page(requested_page)
    modules = list(NAV_MODULES)
    default_module = module_for_page(canonical)

    st.sidebar.markdown(
        """
        <div class="sp-sidebar-brand">
          <div class="sp-brand-mark">SP</div>
          <div><strong>SupplyPilot</strong><span>Decision Intelligence</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    selected_module = st.sidebar.radio(
        "工作区",
        modules,
        index=modules.index(default_module),
        format_func=lambda value: MODULE_LABELS[value],
        key="sp_nav_module",
    )
    pages = list(NAV_MODULES[selected_module])
    default_page = canonical if canonical in pages else pages[0]
    page = st.sidebar.selectbox(
        "业务能力",
        pages,
        index=pages.index(default_page),
        key=f"sp_nav_page_{selected_module}",
    )
    st.sidebar.markdown("---")
    st.sidebar.caption("Demo 数据 · 只读决策支持 · 不写回 ERP")
    if st.query_params.get("page") != page:
        st.query_params["page"] = page
    return page


def navigate_to(page: str, **query: str) -> None:
    target = canonicalize_page(page)
    st.session_state["_sp_nav_target"] = target
    st.query_params["page"] = target
    for key, value in query.items():
        st.query_params[key] = value
    st.rerun()
