from __future__ import annotations

from statistics import fmean

from ..models import (
    InventoryProjection,
    InventoryProjectionInput,
    InventoryProjectionResult,
)


def available_inventory(data: InventoryProjectionInput) -> float:
    return data.on_hand - data.frozen - data.quality_hold - data.allocated + data.reusable_return


def project_inventory_by_week(data: InventoryProjectionInput) -> InventoryProjectionResult:
    warnings: list[str] = []
    if not data.weeks:
        raise ValueError("weekly projection requires at least one week")
    if data.frozen == data.quality_hold == data.allocated == data.reusable_return == 0:
        warnings.append("库存状态分项均为0；请确认不是因源数据缺失而使用默认值")
    weeks = sorted(data.weeks, key=lambda row: row.week_start)
    beginning = available_inventory(data)
    points: list[InventoryProjection] = []
    first_below = None
    first_shortage = None
    maximum_shortage = 0.0
    maximum_shortage_week = None
    for index, row in enumerate(weeks):
        incoming = row.po_receipt + row.production_receipt + row.transfer_in
        outgoing = row.gross_demand + row.reserved_demand + row.transfer_out
        ending = beginning + incoming - outgoing
        shortage = max(0.0, -ending)
        below_safety = max(0.0, row.safety_stock - ending)
        available_to_promise = max(0.0, ending - row.safety_stock)
        net_requirement = max(0.0, outgoing + row.safety_stock - beginning - incoming)
        excess = max(0.0, ending - row.safety_stock)
        future_demand = [week.gross_demand + week.reserved_demand for week in weeks[index:]]
        positive_demand = [quantity for quantity in future_demand if quantity > 0]
        coverage = max(0.0, ending) / fmean(positive_demand) if positive_demand else None
        point = InventoryProjection(
            material_id=data.material_id,
            plant=data.plant,
            week_start=row.week_start,
            beginning_inventory=beginning,
            gross_demand=row.gross_demand,
            reserved_demand=row.reserved_demand,
            safety_stock=row.safety_stock,
            po_receipt=row.po_receipt,
            production_receipt=row.production_receipt,
            transfer_in=row.transfer_in,
            transfer_out=row.transfer_out,
            ending_inventory=ending,
            available_to_promise=available_to_promise,
            net_requirement=net_requirement,
            shortage_qty=shortage,
            below_safety_stock_qty=below_safety,
            excess_qty=excess,
            coverage_weeks=coverage,
            data_version=data.data_version,
            calculation_basis="Ending=Beginning+PO+Production+TransferIn-GrossDemand-ReservedDemand-TransferOut",
        )
        points.append(point)
        if below_safety > 0 and first_below is None:
            first_below = row.week_start
        if shortage > 0 and first_shortage is None:
            first_shortage = row.week_start
        if shortage > maximum_shortage:
            maximum_shortage = shortage
            maximum_shortage_week = row.week_start
        beginning = ending
    return InventoryProjectionResult(
        material_id=data.material_id,
        plant=data.plant,
        points=points,
        first_below_safety_stock_week=first_below,
        first_shortage_week=first_shortage,
        maximum_shortage_qty=maximum_shortage,
        maximum_shortage_week=maximum_shortage_week,
        ending_excess_qty=points[-1].excess_qty,
        initial_available_inventory=available_inventory(data),
        warnings=warnings,
        source_versions=data.source_versions,
    )

