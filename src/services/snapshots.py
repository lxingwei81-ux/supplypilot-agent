from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

from ..config import RulesConfig, load_rules
from ..models import SnapshotTrend, WeeklySnapshot


class SnapshotStore:
    def __init__(self, path: str | Path | None = None, rules: RulesConfig | None = None) -> None:
        self.path = Path(path) if path else None
        self.rules = rules or load_rules()
        self._items: list[WeeklySnapshot] = []
        if self.path and self.path.exists():
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self._items = [WeeklySnapshot.model_validate(item) for item in payload]

    def _persist(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([item.model_dump(mode="json") for item in self._items], ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, snapshot: WeeklySnapshot) -> WeeklySnapshot:
        if any(item.snapshot_id == snapshot.snapshot_id for item in self._items):
            raise ValueError(f"duplicate snapshot id {snapshot.snapshot_id}")
        self._items.append(snapshot)
        latest = max(item.as_of_week for item in self._items)
        cutoff = latest - timedelta(weeks=self.rules.snapshots.retention_weeks)
        self._items = [item for item in self._items if item.as_of_week >= cutoff]
        self._items.sort(key=lambda item: (item.as_of_week, item.entity_type, item.entity_id, item.plant or ""))
        self._persist()
        return snapshot

    def list(self, *, entity_id: str | None = None, plant: str | None = None) -> list[WeeklySnapshot]:
        rows = self._items
        if entity_id:
            rows = [row for row in rows if row.entity_id == entity_id]
        if plant:
            rows = [row for row in rows if row.plant == plant]
        return list(rows)

    def trends(self, entity_id: str, metric: str, window_weeks: int) -> SnapshotTrend:
        rows = [row for row in self._items if row.entity_id == entity_id and metric in row.metrics]
        rows.sort(key=lambda row: row.as_of_week)
        if not rows:
            raise KeyError(f"no snapshots for {entity_id}/{metric}")
        latest = rows[-1].as_of_week
        selected = [row for row in rows if row.as_of_week >= latest - timedelta(weeks=window_weeks - 1)]
        start = selected[0].metrics[metric]
        end = selected[-1].metrics[metric]
        change = end - start
        rate = change / abs(start) if start != 0 else None
        direction = "UP" if change > 0 else ("DOWN" if change < 0 else "FLAT")
        return SnapshotTrend(
            entity_id=entity_id, metric=metric, window_weeks=window_weeks,
            start_value=start, end_value=end, absolute_change=change,
            change_rate=rate, direction=direction, observations=len(selected),
        )

