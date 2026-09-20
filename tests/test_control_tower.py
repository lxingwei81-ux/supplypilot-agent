from __future__ import annotations

from fastapi.testclient import TestClient

from src.api import StructuredCopilotRequest, app, control_tower, structured_copilot
from src.models import ControlTowerSnapshot, ControlTowerStatus
from src.services.control_tower import (
    answer_control_tower_question,
    build_demo_control_tower_snapshot,
    resolve_question_product_id,
)


def _snapshot() -> ControlTowerSnapshot:
    return build_demo_control_tower_snapshot("PRODUCT_B")


def test_control_tower_kpis_reconcile_to_domain_results() -> None:
    snapshot = _snapshot()
    kpis = {item.key: item for item in snapshot.kpis}
    assert kpis["average_wape"].display_value == "40.6%"
    assert kpis["shortage_risks"].value == 2
    assert kpis["excess_value"].value == 162000
    assert kpis["open_actions"].value == 3
    assert kpis["supplier_otd"].value == 0.5
    assert snapshot.source_versions["inventory"] == "DEMO-INV-V1"


def test_demand_trend_has_clear_actual_forecast_boundary_and_valid_band() -> None:
    snapshot = _snapshot()
    actual = [point for point in snapshot.demand_trend if point.period_type == "HISTORY"]
    forecast = [point for point in snapshot.demand_trend if point.period_type == "FORECAST"]
    assert len(actual) == 16
    assert len(forecast) == 26
    assert max(point.week_start for point in actual) < min(point.week_start for point in forecast)
    assert all(point.lower_bound <= point.forecast_qty <= point.upper_bound for point in forecast)


def test_inventory_heatmap_uses_deterministic_risk_boundaries() -> None:
    snapshot = _snapshot()
    cells = {(cell.material_id, str(cell.week_start)): cell for cell in snapshot.inventory_heatmap}
    assert cells[("MAT-B", "2026-07-27")].status == ControlTowerStatus.HEALTHY
    assert cells[("MAT-B", "2026-08-10")].status == ControlTowerStatus.RISK
    assert cells[("MAT-B", "2026-08-24")].status == ControlTowerStatus.CRITICAL
    assert cells[("MAT-C", "2026-09-14")].status == ControlTowerStatus.HEALTHY


def test_action_center_recalculates_target_and_related_plant() -> None:
    snapshot = _snapshot()
    transfer = snapshot.action_validations[0]
    assert transfer.baseline.maximum_shortage_qty == 8800
    assert transfer.action.quantity == 1800
    assert transfer.scenario.maximum_shortage_qty == 7000
    assert str(transfer.baseline.first_shortage_week) == "2026-08-24"
    assert str(transfer.scenario.first_shortage_week) == "2026-09-21"
    assert not transfer.creates_new_shortage
    assert transfer.recommended
    assert transfer.approval_required
    assert transfer.related_entity_results[0].maximum_shortage_qty == 0
    assert transfer.related_entity_results[0].first_below_safety_stock_week is None
    assert transfer.related_entity_results[0].points[-1].ending_inventory == 1000


def test_excess_action_reduces_excess_without_shortage() -> None:
    cancellation = _snapshot().action_validations[1]
    assert cancellation.baseline.ending_excess_qty == 9000
    assert cancellation.scenario.ending_excess_qty == 1000
    assert cancellation.inventory_value_delta == -144000
    assert cancellation.scenario.maximum_shortage_qty == 0
    assert cancellation.recommended


def test_structured_copilot_has_evidence_rules_impact_and_no_reasoning_chain() -> None:
    response = _snapshot().structured_response
    assert response.summary
    assert response.evidence
    assert response.root_causes
    assert response.recommendations
    assert response.expected_impact
    assert response.business_rules
    serialized = response.model_dump_json().lower()
    assert "chain of thought" not in serialized
    assert "step 1" not in serialized


def test_structured_copilot_routes_excess_and_supplier_questions() -> None:
    snapshot = _snapshot()
    excess = answer_control_tower_question(snapshot, "哪些物料存在冗余，可以取消 PO？")
    supplier = answer_control_tower_question(snapshot, "哪个供应商交付风险最高？")
    assert "MAT-A" in excess.summary
    assert excess.action_validation_id == "VAL-CT-CANCEL-MAT-A-8000"
    assert "SUP-DEMO-B" in supplier.summary
    assert supplier.action_validation_id is None


def test_control_tower_and_copilot_api_contracts_are_validated() -> None:
    snapshot = ControlTowerSnapshot.model_validate(control_tower("PRODUCT_B"))
    assert snapshot.selected_material_id == "MAT-B"
    response = structured_copilot(StructuredCopilotRequest(question="为什么 MAT-B 有缺料风险？"))
    assert response["risk_level"] == "CRITICAL"
    assert response["evidence"]
    product_a = structured_copilot(StructuredCopilotRequest(question="PRODUCT_A 未来 13 周预测是多少？"))
    assert "PRODUCT_A" in product_a["summary"]


def test_control_tower_separates_demo_and_legacy_data_quality_scopes() -> None:
    snapshot = _snapshot()
    assert snapshot.data_quality.can_proceed
    assert not snapshot.data_quality.issues
    assert snapshot.legacy_data_quality is not None
    assert not snapshot.legacy_data_quality.can_proceed
    assert sum(issue.blocking for issue in snapshot.legacy_data_quality.issues) == 18


def test_shortage_evidence_has_versioned_material_supplier_mapping() -> None:
    response = _snapshot().structured_response
    mapping = next(item for item in response.evidence if item.source == "demo_supplier_assignments")
    assert mapping.value == "MAT-B → SUP-DEMO-B"
    assert mapping.source_version == "DEMO-SUPMAP-V1"


def test_product_a_snapshot_uses_matching_excess_response() -> None:
    snapshot = build_demo_control_tower_snapshot("PRODUCT_A")
    assert snapshot.selected_material_id == "MAT-A"
    assert "MAT-A" in snapshot.structured_response.summary


def test_product_a_copilot_default_question_stays_in_selected_scope() -> None:
    response = structured_copilot(StructuredCopilotRequest(
        question="为什么这个产品有风险？",
        selected_product_id="PRODUCT_A",
    ))
    assert "MAT-A" in response["summary"]
    assert response["action_validation_id"] == "VAL-CT-CANCEL-MAT-A-8000"


def test_copilot_routes_forecast_timing_and_unknown_questions_without_scope_leakage() -> None:
    product_a = build_demo_control_tower_snapshot("PRODUCT_A")
    forecast = answer_control_tower_question(product_a, "未来 13 周预测是多少？")
    supplier = answer_control_tower_question(product_a, "哪个供应商交付风险最高？")
    timing = answer_control_tower_question(product_a, "为什么 MAT-C 总量不缺但中间周缺料？")
    unsupported = answer_control_tower_question(product_a, "什么是量子纠缠？")

    assert "PRODUCT_A" in forecast.summary
    assert "SUP-DEMO-B" in supplier.summary
    assert "MAT-C" in timing.summary
    assert "未匹配" in unsupported.summary
    assert unsupported.action_validation_id is None
    assert resolve_question_product_id("PRODUCT_A未来13周预测") == "PRODUCT_A"
    assert resolve_question_product_id("Product A 未来 13 周预测") == "PRODUCT_A"
    assert resolve_question_product_id("Product-B 缺料风险") == "PRODUCT_B"
    mismatched = answer_control_tower_question(product_a, "PRODUCT_B 未来13周预测是多少？")
    assert "未匹配" in mismatched.summary


def test_control_tower_api_rejects_unknown_products_with_422() -> None:
    client = TestClient(app)
    assert client.get("/v3/control-tower", params={"selected_product_id": "BAD"}).status_code == 422
    assert client.post(
        "/v3/copilot/structured",
        json={"question": "test", "selected_product_id": "BAD"},
    ).status_code == 422
