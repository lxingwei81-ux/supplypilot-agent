from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Iterable, Mapping

from ..models import BOMRequirement


class BOMError(ValueError):
    pass


class BOMCycleError(BOMError):
    pass


class InvalidBOMError(BOMError):
    pass


def _date_or(value: Any, fallback: date) -> date:
    if value in (None, ""):
        return fallback
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _active(row: Mapping[str, Any], as_of: date) -> bool:
    start = _date_or(row.get("effective_from") or row.get("effective_date"), date.min)
    end = _date_or(row.get("effective_to") or row.get("expiry_date"), date.max)
    return start <= as_of <= end and str(row.get("status", "ACTIVE")).upper() not in {"INVALID", "INACTIVE", "EXPIRED"}


def _select_edges(rows: Iterable[dict[str, Any]], product_id: str, as_of: date) -> list[dict[str, Any]]:
    def belongs(row: dict[str, Any]) -> bool:
        products = [value.strip() for value in str(row.get("product_id", "")).split(";") if value.strip()]
        return not products or product_id in products

    eligible = [
        row for row in rows
        if _active(row, as_of) and belongs(row)
    ]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        grouped[(str(row.get("parent_id", "")), str(row.get("child_id", "")))].append(row)
    selected: list[dict[str, Any]] = []
    for edge_rows in grouped.values():
        selected.append(max(
            edge_rows,
            key=lambda row: (
                _date_or(row.get("effective_from") or row.get("effective_date"), date.min),
                str(row.get("bom_version", "")),
            ),
        ))
    return selected


def explode_bom(
    product_id: str,
    weekly_forecast: Mapping[date, float],
    bom_rows: Iterable[dict[str, Any]],
    *,
    forecast_version_id: str,
    source: str = "bom",
    include_intermediate: bool = False,
) -> list[BOMRequirement]:
    rows = list(bom_rows)
    if not rows:
        raise InvalidBOMError("BOM data is empty")
    requirements: list[BOMRequirement] = []
    for demand_week, forecast_qty_raw in sorted(weekly_forecast.items()):
        forecast_qty = max(0.0, float(forecast_qty_raw))
        edges = _select_edges(rows, product_id, demand_week)
        graph: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in edges:
            parent = str(edge.get("parent_id", "")).strip()
            child = str(edge.get("child_id", "")).strip()
            if not parent or not child:
                raise InvalidBOMError("BOM parent_id and child_id are required")
            try:
                usage = float(edge.get("unit_usage", 0))
            except (TypeError, ValueError) as exc:
                raise InvalidBOMError(f"invalid unit_usage for {parent}->{child}") from exc
            if usage <= 0:
                raise InvalidBOMError(f"unit_usage must be positive for {parent}->{child}")
            graph[parent].append(edge)
        if product_id not in graph:
            raise InvalidBOMError(f"no active BOM for {product_id} on {demand_week}")

        def visit(
            parent: str,
            path: list[str],
            base_multiplier: float,
            gross_multiplier: float,
            inherited_version: str,
        ) -> None:
            if parent in path[:-1]:
                start = path.index(parent)
                raise BOMCycleError(" -> ".join(path[start:] + [parent]))
            children = sorted(graph.get(parent, []), key=lambda row: str(row.get("child_id")))
            for edge in children:
                child = str(edge["child_id"])
                if child in path:
                    raise BOMCycleError(" -> ".join(path + [child]))
                conversion = float(edge.get("conversion_factor", 1) or 1)
                if conversion <= 0:
                    raise InvalidBOMError(f"conversion_factor must be positive for {parent}->{child}")
                usage = float(edge["unit_usage"]) * conversion
                loss_rate = float(edge.get("loss_rate", 0) or 0)
                if loss_rate < 0:
                    raise InvalidBOMError(f"loss_rate cannot be negative for {parent}->{child}")
                next_base = base_multiplier * usage
                next_gross = gross_multiplier * usage * (1 + loss_rate)
                bom_version = str(edge.get("bom_version") or inherited_version or "UNVERSIONED")
                is_leaf = child not in graph
                if include_intermediate or is_leaf:
                    base_quantity = forecast_qty * next_base
                    gross_requirement = forecast_qty * next_gross
                    requirements.append(BOMRequirement(
                        finished_good_id=product_id,
                        material_id=child,
                        demand_week=demand_week,
                        bom_path=path + [child],
                        bom_version=bom_version,
                        base_usage=usage,
                        cumulative_usage=next_gross,
                        loss_rate=max(0.0, next_gross / next_base - 1) if next_base else 0.0,
                        base_quantity=base_quantity,
                        loss_quantity=max(0.0, gross_requirement - base_quantity),
                        gross_requirement=gross_requirement,
                        unit=str(edge.get("base_unit") or edge.get("unit") or "EA"),
                        conversion_factor=conversion,
                        forecast_version_id=forecast_version_id,
                        source=source,
                    ))
                if not is_leaf:
                    visit(child, path + [child], next_base, next_gross, bom_version)

        visit(product_id, [product_id], 1.0, 1.0, "")
    return requirements


def cumulative_usage_by_material(
    product_id: str,
    bom_rows: Iterable[dict[str, Any]],
    *,
    as_of: date,
) -> dict[str, float]:
    exploded = explode_bom(
        product_id,
        {as_of: 1.0},
        bom_rows,
        forecast_version_id="UNIT_USAGE",
    )
    output: dict[str, float] = defaultdict(float)
    for row in exploded:
        output[row.material_id] += row.gross_requirement
    return dict(output)
