from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Sequence

from ..config import RulesConfig, load_rules
from ..models import (
    ForecastAdjustment,
    ForecastPoint,
    ForecastVersion,
    ForecastVersionStatus,
    ForecastVersionType,
)
from .forecast_metrics import wape


class ForecastVersionService:
    """Deterministic in-process repository; production adapters may persist to a database."""

    def __init__(self, rules: RulesConfig | None = None) -> None:
        self.rules = rules or load_rules()
        self._versions: dict[str, ForecastVersion] = {}
        self._sequences: defaultdict[str, int] = defaultdict(int)

    def _next_id(self, item_id: str, version_type: ForecastVersionType) -> str:
        self._sequences[item_id] += 1
        return f"{item_id}-{version_type.value[:4]}-{self._sequences[item_id]:04d}"

    def create_statistical(
        self,
        item_id: str,
        points: list[ForecastPoint],
        *,
        created_by: str = "SYSTEM",
    ) -> ForecastVersion:
        if not points:
            raise ValueError("statistical forecast version requires points")
        version = ForecastVersion(
            version_id=self._next_id(item_id, ForecastVersionType.STATISTICAL),
            item_id=item_id,
            version_type=ForecastVersionType.STATISTICAL,
            status=ForecastVersionStatus.APPROVED,
            created_by=created_by,
            approved_by="DETERMINISTIC_ENGINE",
            points=points,
            effective_from=min(point.week_start for point in points),
            effective_to=max(point.week_start for point in points),
        )
        self._versions[version.version_id] = version
        return version

    def create_adjusted(
        self,
        base_version_id: str,
        adjustments: list[ForecastAdjustment],
        *,
        created_by: str,
    ) -> ForecastVersion:
        base = self._versions[base_version_id]
        adjustment_map = {(adjustment.item_id, adjustment.week_start): adjustment for adjustment in adjustments}
        points: list[ForecastPoint] = []
        for point in base.points:
            adjustment = adjustment_map.get((point.item_id, point.week_start))
            quantity = adjustment.after_qty if adjustment else point.baseline_qty
            scale = quantity / point.baseline_qty if point.baseline_qty > 0 else 1.0
            points.append(point.model_copy(update={
                "baseline_qty": quantity,
                "optimistic_qty": max(quantity, point.optimistic_qty * scale),
                "pessimistic_qty": min(quantity, point.pessimistic_qty * scale),
                "lower_bound": min(quantity, point.lower_bound * scale),
                "upper_bound": max(quantity, point.upper_bound * scale),
                "model_name": "MANUAL_ADJUSTMENT",
            }))
        version = ForecastVersion(
            version_id=self._next_id(base.item_id, ForecastVersionType.MANUAL_ADJUSTMENT),
            item_id=base.item_id,
            version_type=ForecastVersionType.MANUAL_ADJUSTMENT,
            status=ForecastVersionStatus.PENDING_APPROVAL,
            created_by=created_by,
            source_version_ids=[base.version_id],
            points=points,
            adjustments=adjustments,
            effective_from=base.effective_from,
            effective_to=base.effective_to,
        )
        self._versions[version.version_id] = version
        return version

    def approve_consensus(self, adjusted_version_id: str, *, approved_by: str) -> ForecastVersion:
        adjusted = self._versions[adjusted_version_id]
        adjusted.status = ForecastVersionStatus.APPROVED
        adjusted.approved_by = approved_by
        consensus = ForecastVersion(
            version_id=self._next_id(adjusted.item_id, ForecastVersionType.CONSENSUS),
            item_id=adjusted.item_id,
            version_type=ForecastVersionType.CONSENSUS,
            status=ForecastVersionStatus.APPROVED,
            created_by=adjusted.created_by,
            approved_by=approved_by,
            source_version_ids=[adjusted.version_id, *adjusted.source_version_ids],
            points=adjusted.points,
            adjustments=adjusted.adjustments,
            effective_from=adjusted.effective_from,
            effective_to=adjusted.effective_to,
        )
        self._versions[consensus.version_id] = consensus
        return consensus

    def planning_version(self, item_id: str) -> tuple[ForecastVersion, str]:
        versions = [version for version in self._versions.values() if version.item_id == item_id]
        consensus = [version for version in versions if version.version_type == ForecastVersionType.CONSENSUS and version.status == ForecastVersionStatus.APPROVED]
        if consensus:
            return max(consensus, key=lambda version: version.created_at), "APPROVED_CONSENSUS"
        statistical = [version for version in versions if version.version_type == ForecastVersionType.STATISTICAL and version.status == ForecastVersionStatus.APPROVED]
        if not statistical:
            raise KeyError(f"no approved forecast for {item_id}")
        return max(statistical, key=lambda version: version.created_at), "LATEST_STATISTICAL_FALLBACK"

    def evaluate_fva(
        self,
        statistical_version_id: str,
        adjusted_version_id: str,
        actual_by_week: dict[date, float],
    ) -> dict[str, float | str | None]:
        statistical = self._versions[statistical_version_id]
        adjusted = self._versions[adjusted_version_id]
        common_weeks = sorted(set(actual_by_week) & {point.week_start for point in statistical.points} & {point.week_start for point in adjusted.points})
        if not common_weeks:
            adjusted.fva_status = "PENDING_ACTUALS"
            return {"fva": None, "status": "PENDING_ACTUALS"}
        actual = [actual_by_week[week] for week in common_weeks]
        stat_map = {point.week_start: point.baseline_qty for point in statistical.points}
        adjusted_map = {point.week_start: point.baseline_qty for point in adjusted.points}
        before = wape(actual, [stat_map[week] for week in common_weeks])
        after = wape(actual, [adjusted_map[week] for week in common_weeks])
        if before is None or after is None:
            fva = None
            status = "NOT_EVALUABLE_ZERO_ACTUAL"
        else:
            fva = before - after
            tolerance = self.rules.forecast.fva_tolerance
            status = "IMPROVED" if fva > tolerance else ("WORSENED" if fva < -tolerance else "NO_MATERIAL_CHANGE")
        adjusted.fva = fva
        adjusted.fva_status = status
        return {"fva": fva, "status": status, "error_before": before, "error_after": after}

    def list_versions(self, item_id: str | None = None) -> list[ForecastVersion]:
        versions = list(self._versions.values())
        if item_id:
            versions = [version for version in versions if version.item_id == item_id]
        return sorted(versions, key=lambda version: (version.item_id, version.created_at, version.version_id))
