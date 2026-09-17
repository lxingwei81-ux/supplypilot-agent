from __future__ import annotations

from collections import Counter
from typing import Sequence

from ..models import (
    DataQualityReport,
    ForecastResult,
    ManagementDashboard,
    Risk,
    RiskTask,
    RiskType,
    SupplierReliabilityResult,
    TaskStatus,
)


def build_management_dashboard(
    *,
    data_quality: DataQualityReport,
    forecasts: Sequence[ForecastResult],
    risks: Sequence[Risk],
    tasks: Sequence[RiskTask],
    suppliers: Sequence[SupplierReliabilityResult],
    source_versions: dict[str, str],
) -> ManagementDashboard:
    wapes = [result.selected_metrics.wape for result in forecasts if result.selected_metrics and result.selected_metrics.wape is not None]
    shortage = [risk for risk in risks if risk.risk_type in {RiskType.SHORTAGE, RiskType.BELOW_SAFETY_STOCK, RiskType.LATE_SUPPLY}]
    excess = [risk for risk in risks if risk.risk_type in {RiskType.EXCESS, RiskType.OBSOLETE}]
    closed = {TaskStatus.COMPLETED, TaskStatus.VERIFIED, TaskStatus.CLOSED, TaskStatus.CANCELLED}
    open_tasks = [task for task in tasks if task.status not in closed]
    pending = [task for task in tasks if task.status == TaskStatus.PENDING_APPROVAL]
    severity_rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
    top = sorted(
        risks,
        key=lambda risk: (severity_rank[risk.level.value], risk.value, risk.risk_id),
        reverse=True,
    )[:10]
    return ManagementDashboard(
        data_quality_blockers=sum(1 for issue in data_quality.issues if issue.blocking),
        forecast_items=len(forecasts),
        forecast_review_rate=sum(1 for result in forecasts if result.requires_manual_review) / len(forecasts) if forecasts else 0.0,
        average_wape=sum(wapes) / len(wapes) if wapes else None,
        shortage_risk_count=len(shortage), excess_risk_count=len(excess),
        shortage_value=sum(risk.value for risk in shortage), excess_value=sum(risk.value for risk in excess),
        open_task_count=len(open_tasks),
        overdue_task_count=sum(1 for task in open_tasks if task.escalation_level > 0),
        pending_approval_count=len(pending),
        supplier_grade_distribution=dict(Counter(result.grade for result in suppliers)),
        top_risks=[risk.model_dump(mode="json") for risk in top],
        source_versions=source_versions,
    )
