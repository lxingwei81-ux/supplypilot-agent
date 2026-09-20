from __future__ import annotations

from src.ui.navigation import all_pages, canonicalize_page, module_for_page


def test_legacy_copilot_page_alias_is_preserved() -> None:
    assert canonicalize_page("智能问答（兼容页）") == "AI Copilot"
    assert module_for_page("智能问答（兼容页）") == "AI Copilot"


def test_navigation_has_five_primary_modules_and_keeps_legacy_pages() -> None:
    pages = all_pages()
    assert module_for_page("管理驾驶舱") == "Overview"
    assert module_for_page("预测对比与回测") == "Demand Forecast"
    assert module_for_page("周度库存投影") == "Inventory"
    assert module_for_page("供应商交期可靠性") == "Procurement"
    assert "Excel导入与字段映射" in pages
    assert "库存控制台" in pages
    assert "采购工作台" in pages

