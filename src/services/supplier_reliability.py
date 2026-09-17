from __future__ import annotations

from statistics import fmean, pvariance
from typing import Sequence

from ..config import RulesConfig, load_rules
from ..models import SupplierDeliveryRecord, SupplierReliabilityResult


def calculate_supplier_reliability(
    supplier_id: str,
    records: Sequence[SupplierDeliveryRecord],
    *,
    rules: RulesConfig | None = None,
) -> SupplierReliabilityResult:
    cfg = rules or load_rules()
    supplier_records = [record for record in records if record.supplier_id == supplier_id]
    if not supplier_records:
        raise ValueError(f"no delivery records for supplier {supplier_id}")
    tolerance = cfg.supplier_reliability.on_time_tolerance_days
    lateness = [(record.actual_date - record.promised_date).days for record in supplier_records]
    lead_times = [max(0, (record.actual_date - record.order_date).days) for record in supplier_records]
    on_time = sum(1 for days in lateness if days <= tolerance) / len(supplier_records)
    ordered = sum(record.ordered_qty for record in supplier_records)
    fill = min(1.0, sum(record.received_qty for record in supplier_records) / ordered) if ordered else 0.0
    confirmed = [record for record in supplier_records if record.confirmed_date is not None]
    confirmation_adherence = (
        sum(1 for record in confirmed if (record.actual_date - record.confirmed_date).days <= tolerance) / len(supplier_records)
        if supplier_records else 0.0
    )
    mean_lead = fmean(lead_times)
    variance = pvariance(lead_times) if len(lead_times) > 1 else 0.0
    stability = 1.0 / (1.0 + (variance ** 0.5) / max(mean_lead, 1.0))
    weights = cfg.supplier_reliability.weights
    score = (
        on_time * weights.on_time_rate
        + fill * weights.quantity_fill_rate
        + stability * weights.lead_time_stability
        + confirmation_adherence * weights.confirmation_adherence
    )
    thresholds = cfg.supplier_reliability.grade_thresholds
    grade = "A" if score >= thresholds["A"] else ("B" if score >= thresholds["B"] else ("C" if score >= thresholds["C"] else "D"))
    warnings = []
    if len(supplier_records) < cfg.supplier_reliability.minimum_samples:
        warnings.append(f"样本数{len(supplier_records)}低于配置下限{cfg.supplier_reliability.minimum_samples}，评级置信度有限")
    if len(confirmed) < len(supplier_records):
        warnings.append("部分订单缺少供应商确认日期，确认遵从率按未遵从处理")
    return SupplierReliabilityResult(
        supplier_id=supplier_id, sample_count=len(supplier_records), on_time_rate=on_time,
        quantity_fill_rate=fill, confirmation_adherence=confirmation_adherence,
        mean_lead_time_days=mean_lead, lead_time_variance=variance,
        mean_lateness_days=fmean(lateness), lead_time_stability_score=stability,
        reliability_score=score, grade=grade, warnings=warnings,
        source_versions=sorted({record.data_version for record in supplier_records}),
        rules_version=cfg.metadata.version,
    )
