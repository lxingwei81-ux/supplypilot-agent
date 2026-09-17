from __future__ import annotations

from collections import Counter

from src.services.data_quality import assess_project_data, validate_data_quality


def codes(report):
    return Counter(issue.code for issue in report.issues)


def test_missing_required_field_blocks() -> None:
    report = validate_data_quality({"historical_demand": [{"item_id": "A", "week_start": "2026-01-05"}]})
    assert codes(report)["MISSING_REQUIRED_FIELD"] == 1
    assert not report.can_proceed


def test_duplicate_demand_blocks() -> None:
    row = {"item_id": "A", "week_start": "2026-01-05", "demand_qty": 1}
    report = validate_data_quality({"historical_demand": [row, row.copy()]})
    assert codes(report)["DUPLICATE_RECORD"] == 1
    assert not report.can_proceed


def test_invalid_date_and_numeric_block() -> None:
    report = validate_data_quality({"historical_demand": [{"item_id": "A", "week_start": "bad", "demand_qty": "x"}]})
    assert codes(report)["INVALID_DATE"] == 1
    assert codes(report)["INVALID_NUMERIC"] == 1


def test_negative_inventory_is_warning() -> None:
    report = validate_data_quality({"inventory": [{"material_id": "M", "plant": "P", "on_hand": -1}]})
    issue = next(issue for issue in report.issues if issue.code == "NEGATIVE_INVENTORY")
    assert not issue.blocking


def test_bom_cycle_blocks() -> None:
    bom = [
        {"parent_id": "A", "child_id": "B", "unit_usage": 1},
        {"parent_id": "B", "child_id": "A", "unit_usage": 1},
    ]
    report = validate_data_quality({"bom": bom})
    assert codes(report)["BOM_CYCLE"] == 1
    assert not report.can_proceed


def test_invalid_bom_dates_and_missing_conversion_block() -> None:
    bom = [{
        "parent_id": "A", "child_id": "B", "unit_usage": 1,
        "effective_date": "2026-02-01", "expiry_date": "2026-01-01",
        "unit": "KG", "base_unit": "G", "conversion_factor": "",
    }]
    report = validate_data_quality({"bom": bom})
    assert codes(report)["INVALID_BOM"] == 1
    assert codes(report)["MISSING_UNIT_CONVERSION"] == 1


def test_po_receipt_before_order_is_warning() -> None:
    po = [{
        "document_id": "PO1", "material_id": "M", "plant": "P", "open_qty": 1,
        "order_date": "2026-02-01", "receipt_date": "2026-01-01",
    }]
    report = validate_data_quality({"procurement": po})
    assert codes(report)["PO_RECEIPT_BEFORE_ORDER"] == 1


def test_short_history_is_nonblocking_warning() -> None:
    rows = [{"item_id": "A", "week_start": f"2026-01-{day:02d}", "demand_qty": 1} for day in range(1, 5)]
    report = validate_data_quality({"historical_demand": rows})
    assert codes(report)["INSUFFICIENT_HISTORY"] == 1
    assert report.can_proceed


def test_current_demo_exposes_duplicate_procurement_ids() -> None:
    report = assess_project_data()
    assert codes(report)["DUPLICATE_RECORD"] == 18
    assert not report.can_proceed

