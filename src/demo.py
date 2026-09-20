from __future__ import annotations

from collections import defaultdict
from typing import Any

from .models import (
    ATPDemand,
    InventoryProjectionInput,
    POOption,
    PriceBreak,
    SupplierDeliveryRecord,
    TransferLane,
    TransferSource,
    TransferTarget,
    WeeklyInventoryInput,
)
from .repository import load_table


def demo_histories() -> tuple[dict[str, list[float]], dict[str, dict[str, Any]]]:
    rows = sorted(load_table("demo_historical_demand"), key=lambda row: (str(row["item_id"]), str(row["week_start"])))
    histories: dict[str, list[float]] = defaultdict(list)
    metadata: dict[str, dict[str, Any]] = {}
    for row in rows:
        item_id = str(row["item_id"])
        histories[item_id].append(float(row["demand_qty"]))
        metadata[item_id] = {
            "unit_cost": float(row["unit_cost"]),
            "lifecycle": str(row["lifecycle"]),
            "last_history_week": str(row["week_start"]),
            "data_version": str(row["data_version"]),
        }
    return dict(histories), metadata


def demo_projection(case_id: str, material_id: str, plant: str) -> InventoryProjectionInput:
    rows = [
        row for row in load_table("demo_weekly_inventory")
        if str(row["case_id"]) == case_id and str(row["material_id"]) == material_id and str(row["plant"]) == plant
    ]
    if not rows:
        raise KeyError(f"no demo projection for {case_id}/{material_id}/{plant}")
    rows.sort(key=lambda row: str(row["week_start"]))
    first = rows[0]
    return InventoryProjectionInput(
        material_id=material_id,
        plant=plant,
        on_hand=float(first["on_hand"]),
        frozen=float(first["frozen"]),
        quality_hold=float(first["quality_hold"]),
        allocated=float(first["allocated"]),
        reusable_return=float(first["reusable_return"]),
        weeks=[WeeklyInventoryInput(
            week_start=row["week_start"],
            gross_demand=float(row["gross_demand"]),
            reserved_demand=float(row["reserved_demand"]),
            safety_stock=float(row["safety_stock"]),
            po_receipt=float(row["po_receipt"]),
            production_receipt=float(row["production_receipt"]),
            transfer_in=float(row["transfer_in"]),
            transfer_out=float(row["transfer_out"]),
        ) for row in rows],
        data_version=str(first["data_version"]),
        source_versions={"weekly_inventory": str(first["data_version"])},
    )


def demo_bom_rows() -> list[dict[str, Any]]:
    return load_table("demo_bom_extended")


def demo_planning_parameters(item_id: str) -> dict[str, Any]:
    rows = [row for row in load_table("demo_item_planning") if str(row["item_id"]) == item_id]
    if not rows:
        raise KeyError(item_id)
    return rows[0]


def _bool(value: Any) -> bool:
    return str(value).strip().upper() in {"Y", "YES", "TRUE", "1"}


def demo_atp_demands(material_id: str = "COMMON-M") -> list[ATPDemand]:
    return [ATPDemand(
        demand_id=str(row["demand_id"]), material_id=str(row["material_id"]),
        customer_id=str(row["customer_id"]), product_id=str(row["product_id"]),
        plant=str(row["plant"]), need_week=row["need_week"],
        requested_qty=float(row["requested_qty"]), frozen_order=_bool(row["frozen_order"]),
        customer_priority=int(row["customer_priority"]),
        shortage_penalty_per_unit=float(row["shortage_penalty_per_unit"]),
        lifecycle=str(row["lifecycle"]), source_version=str(row["source_version"]),
    ) for row in load_table("demo_atp_demand") if str(row["material_id"]) == material_id]


def demo_transfer_network(material_id: str = "MAT-B") -> tuple[list[TransferSource], list[TransferTarget], list[TransferLane]]:
    sources = [TransferSource.model_validate({key: value for key, value in row.items() if key != "source_type"}) for row in load_table("demo_transfer_sources") if str(row["material_id"]) == material_id]
    targets = [TransferTarget.model_validate({key: value for key, value in row.items() if key != "source_type"}) for row in load_table("demo_transfer_targets") if str(row["material_id"]) == material_id]
    lanes = [TransferLane(
        source_plant=str(row["source_plant"]), target_plant=str(row["target_plant"]),
        lead_time_days=int(row["lead_time_days"]), unit_cost=float(row["unit_cost"]),
        fixed_cost=float(row["fixed_cost"]), compatible=_bool(row["compatible"]),
    ) for row in load_table("demo_transfer_lanes")]
    return sources, targets, lanes


def demo_po_options(material_id: str = "MAT-A", plant: str = "DEMO_PLANT") -> list[POOption]:
    return [POOption.model_validate({key: value for key, value in row.items() if key != "source_type"})
            for row in load_table("demo_po_optimization")
            if str(row["material_id"]) == material_id and str(row["plant"]) == plant]


def demo_price_breaks(material_id: str = "MAT-B") -> tuple[list[PriceBreak], dict[str, float]]:
    rows = [row for row in load_table("demo_price_breaks") if str(row["material_id"]) == material_id]
    if not rows:
        raise KeyError(material_id)
    breaks = [PriceBreak(
        minimum_qty=float(row["minimum_qty"]), unit_price=float(row["unit_price"]),
        data_version=str(row["data_version"]),
    ) for row in rows]
    first = rows[0]
    return breaks, {"moq": float(first["moq"]), "mpq": float(first["mpq"]), "package_multiple": float(first["package_multiple"])}


def demo_supplier_records() -> list[SupplierDeliveryRecord]:
    rows = []
    for row in load_table("demo_supplier_deliveries"):
        rows.append(SupplierDeliveryRecord(
            supplier_id=str(row["supplier_id"]), document_id=str(row["document_id"]),
            promised_date=row["promised_date"], confirmed_date=row.get("confirmed_date") or None,
            actual_date=row["actual_date"], ordered_qty=float(row["ordered_qty"]),
            received_qty=float(row["received_qty"]), order_date=row["order_date"],
            data_version=str(row["data_version"]),
        ))
    return rows


def demo_supplier_assignments() -> list[dict[str, Any]]:
    """Return the versioned demo material-to-supplier master mapping."""

    return load_table("demo_supplier_assignments")
