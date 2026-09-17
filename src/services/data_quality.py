from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from ..config import RulesConfig, load_rules
from ..models import (
    DataQualityIssue,
    DataQualityReport,
    DataQualitySeverity,
    Evidence,
)
from ..repository import load_table


NUMERIC_FIELDS = {
    "quantity", "qty", "demand_qty", "actual_qty", "forecast_qty", "unit_cost",
    "unit_price", "on_hand", "frozen", "quality_hold", "allocated", "open_qty",
    "open_po_qty", "in_transit_po", "unit_usage", "loss_rate", "conversion_factor",
    "safety_stock", "lead_time_days", "cancelable_qty", "reschedulable_qty",
}
DATE_FIELDS = {
    "date", "week_start", "effective_date", "expiry_date", "effective_from",
    "effective_to", "order_date", "receipt_date", "eta_date",
}


class DataQualityBlockedError(ValueError):
    def __init__(self, report: DataQualityReport):
        self.report = report
        super().__init__("blocking data-quality issues prevent calculation")


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _issue(
    code: str,
    message: str,
    table: str,
    *,
    rules: RulesConfig,
    row_index: int | None = None,
    field: str | None = None,
    value: Any = None,
    impact: str = "",
    force_blocking: bool | None = None,
) -> DataQualityIssue:
    blocking = code in rules.data_quality.blocking_codes if force_blocking is None else force_blocking
    severity = DataQualitySeverity.BLOCKING if blocking else DataQualitySeverity.WARNING
    return DataQualityIssue(
        code=code,
        severity=severity,
        message=message,
        table=table,
        row_index=row_index,
        field=field,
        value=value,
        blocking=blocking,
        impact=impact,
        evidence=[Evidence(
            source=table,
            source_record_id=str(row_index) if row_index is not None else None,
            field=field,
            value=value,
            description=message,
        )],
    )


def _cycle_nodes(rows: Iterable[dict[str, Any]]) -> list[str]:
    graph: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        parent = str(row.get("parent_id", "")).strip()
        child = str(row.get("child_id", "")).strip()
        if parent and child:
            graph[parent].append(child)
    visited: set[str] = set()
    active: set[str] = set()

    def visit(node: str, path: list[str]) -> list[str]:
        if node in active:
            return path[path.index(node):] + [node]
        if node in visited:
            return []
        visited.add(node)
        active.add(node)
        for child in graph.get(node, []):
            cycle = visit(child, path + [child])
            if cycle:
                return cycle
        active.remove(node)
        return []

    for node in list(graph):
        cycle = visit(node, [node])
        if cycle:
            return cycle
    return []


def validate_data_quality(
    tables: dict[str, list[dict[str, Any]]],
    *,
    data_version: str = "UNVERSIONED",
    rules: RulesConfig | None = None,
    required_tables: list[str] | None = None,
) -> DataQualityReport:
    cfg = rules or load_rules()
    issues: list[DataQualityIssue] = []
    required_tables = required_tables or []

    for table in required_tables:
        if table not in tables:
            issues.append(_issue(
                "MISSING_REQUIRED_TABLE", f"缺少计算所需数据表 {table}", table,
                rules=cfg, impact="无法执行对应领域计算", force_blocking=True,
            ))

    for table, rows in tables.items():
        required_fields = cfg.data_quality.required_fields.get(table, [])
        available_fields = set().union(*(row.keys() for row in rows)) if rows else set()
        for field in required_fields:
            if field not in available_fields:
                issues.append(_issue(
                    "MISSING_REQUIRED_FIELD", f"缺少必填字段 {field}", table,
                    rules=cfg, field=field, impact="关键计算输入不完整",
                ))
        for index, row in enumerate(rows, start=2):
            for field in required_fields:
                if field in row and _is_blank(row.get(field)):
                    issues.append(_issue(
                        "MISSING_REQUIRED_FIELD", f"必填字段 {field} 为空", table,
                        rules=cfg, row_index=index, field=field, value=row.get(field),
                        impact="该记录不能参与计算",
                    ))
            for field, value in row.items():
                lowered = field.lower()
                if _is_blank(value):
                    continue
                if lowered in NUMERIC_FIELDS or lowered.endswith("_qty") or lowered.endswith("_cost"):
                    try:
                        float(value)
                    except (TypeError, ValueError):
                        issues.append(_issue(
                            "INVALID_NUMERIC", f"字段 {field} 不是有效数值", table,
                            rules=cfg, row_index=index, field=field, value=value,
                            impact="数量或金额计算不可靠",
                        ))
                if lowered in DATE_FIELDS or lowered.endswith("_date"):
                    try:
                        _as_date(value)
                    except (TypeError, ValueError):
                        issues.append(_issue(
                            "INVALID_DATE", f"字段 {field} 不是 ISO 日期", table,
                            rules=cfg, row_index=index, field=field, value=value,
                            impact="时序计算不可执行",
                        ))

        duplicate_keys: list[str] = []
        if table == "historical_demand":
            duplicate_keys = [key for key in ("item_id", "customer", "plant", "week_start") if key in available_fields]
        elif table == "bom":
            duplicate_keys = [key for key in ("product_id", "parent_id", "child_id", "bom_version", "effective_date") if key in available_fields]
        elif table == "procurement":
            duplicate_keys = [key for key in ("document_id",) if key in available_fields]
        elif table == "forecast_versions":
            duplicate_keys = [key for key in ("version_id", "item_id", "week_start") if key in available_fields]
        if duplicate_keys:
            counts = Counter(tuple(str(row.get(key, "")) for key in duplicate_keys) for row in rows)
            for key, count in counts.items():
                if count > 1:
                    issues.append(_issue(
                        "DUPLICATE_RECORD", f"按 {duplicate_keys} 发现 {count} 条重复记录", table,
                        rules=cfg, value=dict(zip(duplicate_keys, key)), impact="需求或供给会被重复计算",
                    ))

    inventory_rows = tables.get("inventory", tables.get("inventory_positions", []))
    for index, row in enumerate(inventory_rows, start=2):
        for field in ("on_hand", "frozen", "quality_hold", "allocated"):
            if field in row and not _is_blank(row.get(field)):
                try:
                    if float(row[field]) < 0:
                        issues.append(_issue(
                            "NEGATIVE_INVENTORY", f"库存字段 {field} 为负数", "inventory",
                            rules=cfg, row_index=index, field=field, value=row[field],
                            impact="需确认冲销或库存状态", force_blocking=False,
                        ))
                except (TypeError, ValueError):
                    pass

    for index, row in enumerate(tables.get("procurement", []), start=2):
        order_date = row.get("order_date")
        receipt_date = row.get("receipt_date") or row.get("eta_date")
        if order_date and receipt_date:
            try:
                if _as_date(receipt_date) < _as_date(order_date):
                    issues.append(_issue(
                        "PO_RECEIPT_BEFORE_ORDER", "PO到货日期早于下单日期", "procurement",
                        rules=cfg, row_index=index, value={"order_date": order_date, "receipt_date": receipt_date},
                        impact="PO时序不可信", force_blocking=False,
                    ))
            except (TypeError, ValueError):
                pass

    bom_rows = tables.get("bom", [])
    cycle = _cycle_nodes(bom_rows)
    if cycle:
        issues.append(_issue(
            "BOM_CYCLE", f"检测到BOM循环：{' -> '.join(cycle)}", "bom",
            rules=cfg, value=cycle, impact="递归拆解无法终止",
        ))
    for index, row in enumerate(bom_rows, start=2):
        effective = row.get("effective_date") or row.get("effective_from")
        expiry = row.get("expiry_date") or row.get("effective_to")
        if effective and expiry:
            try:
                if _as_date(expiry) < _as_date(effective):
                    issues.append(_issue(
                        "INVALID_BOM", "BOM失效日期早于生效日期", "bom",
                        rules=cfg, row_index=index, value={"effective": effective, "expiry": expiry},
                        impact="BOM版本区间无效",
                    ))
            except (TypeError, ValueError):
                pass
        unit = row.get("unit")
        base_unit = row.get("base_unit")
        if unit and base_unit and unit != base_unit and _is_blank(row.get("conversion_factor")):
            issues.append(_issue(
                "MISSING_UNIT_CONVERSION", "跨单位BOM缺少换算系数", "bom",
                rules=cfg, row_index=index, field="conversion_factor",
                value={"unit": unit, "base_unit": base_unit}, impact="毛需求数量无法统一单位",
            ))

    products = tables.get("products", [])
    for index, row in enumerate(products, start=2):
        if _is_blank(row.get("lifecycle")):
            issues.append(_issue(
                "MISSING_LIFECYCLE", "产品生命周期缺失", "products",
                rules=cfg, row_index=index, field="lifecycle",
                impact="无法应用NPI/EOL差异化策略", force_blocking=False,
            ))

    histories: dict[str, set[str]] = defaultdict(set)
    for row in tables.get("historical_demand", []):
        item = str(row.get("item_id", ""))
        if item and row.get("week_start"):
            histories[item].add(str(row["week_start"]))
    for item, weeks in histories.items():
        if len(weeks) < cfg.data_quality.minimum_history_periods:
            issues.append(_issue(
                "INSUFFICIENT_HISTORY", f"{item} 仅有 {len(weeks)} 个历史周期", "historical_demand",
                rules=cfg, value=len(weeks), impact="预测候选模型和回测次数受限", force_blocking=False,
            ))

    forecast_rows = tables.get("forecast_versions", [])
    version_periods: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in forecast_rows:
        version_periods[(str(row.get("item_id", "")), str(row.get("version_id", "")))].add(str(row.get("week_start", "")))
    item_versions: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for (item, version), periods in version_periods.items():
        item_versions[item].append((version, len(periods)))
    for item, versions in item_versions.items():
        lengths = {length for _, length in versions}
        if len(lengths) > 1:
            issues.append(_issue(
                "FORECAST_VERSION_GAP", f"{item} 的预测版本周期数不一致", "forecast_versions",
                rules=cfg, value=versions, impact="版本间变化不可直接比较", force_blocking=False,
            ))

    actuals = {(str(r.get("item_id")), str(r.get("week_start"))): r for r in tables.get("actual_shipments", [])}
    for index, row in enumerate(forecast_rows, start=2):
        key = (str(row.get("item_id")), str(row.get("week_start")))
        actual = actuals.get(key)
        if actual and row.get("forecast_qty") not in (None, "") and actual.get("actual_qty") not in (None, ""):
            forecast_qty = float(row["forecast_qty"])
            actual_qty = float(actual["actual_qty"])
            deviation = abs(actual_qty - forecast_qty) / max(abs(forecast_qty), 1.0)
            if deviation > cfg.demand_change.actual_forecast_deviation_warning:
                issues.append(_issue(
                    "ACTUAL_DEMAND_DEVIATION", "实际出货与预测异常偏离", "actual_shipments",
                    rules=cfg, row_index=index, value=deviation,
                    impact="需确认促销、取消或数据口径", force_blocking=False,
                ))

    for index, row in enumerate(tables.get("demand_transactions", []), start=2):
        transaction_type = str(row.get("transaction_type", "")).upper()
        if transaction_type in {"RETURN", "REVERSAL", "CANCEL"}:
            try:
                if float(row.get("quantity", 0)) > 0:
                    issues.append(_issue(
                        "UNRESTORED_REVERSAL", "退货/冲销/取消记录未还原为负向需求", "demand_transactions",
                        rules=cfg, row_index=index, field="quantity", value=row.get("quantity"),
                        impact="历史需求被高估", force_blocking=False,
                    ))
            except (TypeError, ValueError):
                pass

    limitations = []
    if "historical_demand" not in tables:
        limitations.append("未提供历史周需求，不能执行预测与回测")
    if not any("frozen" in row for row in inventory_rows):
        limitations.append("库存状态未拆分冻结、质检、分配和可复用退货")
    return DataQualityReport(
        report_id=f"DQ-{data_version}",
        data_version=data_version,
        issues=issues,
        tables_checked=sorted(tables),
        limitations=limitations,
    )


def ensure_calculation_allowed(report: DataQualityReport) -> None:
    if not report.can_proceed:
        raise DataQualityBlockedError(report)


def assess_project_data(data_dir: str | Path | None = None) -> DataQualityReport:
    directory = Path(data_dir) if data_dir else Path(__file__).resolve().parents[2] / "data"
    tables: dict[str, list[dict[str, Any]]] = {}
    for path in directory.glob("*.csv"):
        tables[path.stem] = load_table(path.stem)
    return validate_data_quality(tables, data_version="DEMO-CURRENT")
