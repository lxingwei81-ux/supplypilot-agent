from __future__ import annotations

import altair as alt
import pandas as pd

from ..models import DemandTrendPoint, InventoryProjectionResult, InventoryRiskCell
from .theme import RISK_COLORS


def demand_forecast_chart(points: list[DemandTrendPoint], *, horizon_weeks: int = 13) -> alt.Chart:
    rows = [point.model_dump(mode="json") for point in points]
    frame = pd.DataFrame(rows)
    forecast_weeks = sorted(frame.loc[frame["period_type"] == "FORECAST", "week_start"].unique())[:horizon_weeks]
    if len(forecast_weeks):
        frame = frame[(frame["period_type"] == "HISTORY") | frame["week_start"].isin(forecast_weeks)].copy()
    frame["week_start"] = pd.to_datetime(frame["week_start"])
    actual = alt.Chart(frame.dropna(subset=["actual_qty"])).mark_line(
        color="#0F172A", strokeWidth=2.4, point=alt.OverlayMarkDef(size=28, filled=True),
    ).encode(
        x=alt.X("week_start:T", title=None, axis=alt.Axis(format="%m/%d", labelAngle=0, tickCount=8)),
        y=alt.Y("actual_qty:Q", title="需求数量", scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("week_start:T", title="周", format="%Y-%m-%d"), alt.Tooltip("actual_qty:Q", title="实际", format=",.0f")],
    )
    forecast_frame = frame.dropna(subset=["forecast_qty"])
    band = alt.Chart(forecast_frame).mark_area(color="#93C5FD", opacity=0.24).encode(
        x="week_start:T",
        y=alt.Y("lower_bound:Q", title="需求数量"),
        y2="upper_bound:Q",
        tooltip=[
            alt.Tooltip("week_start:T", title="周", format="%Y-%m-%d"),
            alt.Tooltip("forecast_qty:Q", title="预测", format=",.0f"),
            alt.Tooltip("lower_bound:Q", title="情景下限", format=",.0f"),
            alt.Tooltip("upper_bound:Q", title="情景上限", format=",.0f"),
        ],
    )
    forecast = alt.Chart(forecast_frame).mark_line(
        color="#2563EB", strokeWidth=2.6, strokeDash=[7, 4], point=alt.OverlayMarkDef(size=34, filled=True),
    ).encode(x="week_start:T", y="forecast_qty:Q")
    boundary_date = forecast_frame["week_start"].min()
    boundary = alt.Chart(pd.DataFrame({"week_start": [boundary_date], "label": ["预测起点"]})).mark_rule(
        color="#64748B", strokeDash=[4, 4],
    ).encode(x="week_start:T", tooltip=["label:N"])
    return (band + actual + forecast + boundary).properties(height=310).configure_view(strokeWidth=0).interactive()


def inventory_heatmap_chart(cells: list[InventoryRiskCell]) -> alt.Chart:
    frame = pd.DataFrame([cell.model_dump(mode="json") for cell in cells])
    frame["week_start"] = pd.to_datetime(frame["week_start"])
    frame["week_label"] = frame["week_start"].dt.strftime("%m/%d")
    frame["row_label"] = frame["material_id"] + " · " + frame["plant"]
    frame["inventory_label"] = frame["ending_inventory"].map(lambda value: f"{value / 1000:.1f}K" if abs(value) >= 1000 else f"{value:.0f}")
    status_order = ["HEALTHY", "WATCH", "RISK", "CRITICAL", "UNKNOWN"]
    color_range = [RISK_COLORS[value] for value in status_order]
    week_order = list(dict.fromkeys(frame.sort_values("week_start")["week_label"]))
    base = alt.Chart(frame).encode(
        x=alt.X("week_label:N", title=None, sort=week_order, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("row_label:N", title=None, sort=None),
    )
    rect = base.mark_rect(cornerRadius=5, stroke="white", strokeWidth=2).encode(
        color=alt.Color(
            "status:N",
            title="风险状态",
            scale=alt.Scale(domain=status_order, range=color_range),
            legend=alt.Legend(orient="top", direction="horizontal"),
        ),
        tooltip=[
            alt.Tooltip("material_id:N", title="物料"),
            alt.Tooltip("plant:N", title="工厂"),
            alt.Tooltip("week_start:T", title="周", format="%Y-%m-%d"),
            alt.Tooltip("ending_inventory:Q", title="投影库存", format=",.0f"),
            alt.Tooltip("safety_stock:Q", title="安全库存", format=",.0f"),
            alt.Tooltip("gross_demand:Q", title="需求", format=",.0f"),
            alt.Tooltip("incoming_supply:Q", title="到货", format=",.0f"),
            alt.Tooltip("status_reason:N", title="判定依据"),
        ],
    )
    text = base.mark_text(color="white", fontSize=10, fontWeight="bold").encode(text="inventory_label:N")
    return (rect + text).properties(height=235).configure_view(strokeWidth=0)


def inventory_projection_chart(result: InventoryProjectionResult) -> alt.Chart:
    frame = pd.DataFrame([point.model_dump(mode="json") for point in result.points])
    frame["week_start"] = pd.to_datetime(frame["week_start"])
    frame["zero"] = 0.0
    base = alt.Chart(frame).encode(
        x=alt.X("week_start:T", title=None, axis=alt.Axis(format="%m/%d", labelAngle=0)),
    )
    inventory = base.mark_line(color="#2563EB", strokeWidth=3, point=alt.OverlayMarkDef(size=45, filled=True)).encode(
        y=alt.Y("ending_inventory:Q", title="库存数量"),
        tooltip=[
            alt.Tooltip("week_start:T", title="周", format="%Y-%m-%d"),
            alt.Tooltip("beginning_inventory:Q", title="期初", format=",.0f"),
            alt.Tooltip("ending_inventory:Q", title="期末", format=",.0f"),
            alt.Tooltip("gross_demand:Q", title="需求", format=",.0f"),
            alt.Tooltip("po_receipt:Q", title="PO到货", format=",.0f"),
        ],
    )
    safety = base.mark_line(color="#CA8A04", strokeWidth=2, strokeDash=[6, 4]).encode(y="safety_stock:Q")
    zero = base.mark_line(color="#DC2626", strokeWidth=1.4, strokeDash=[2, 3]).encode(y="zero:Q")
    receipts = base.transform_filter("datum.po_receipt > 0").mark_point(
        shape="triangle-up", color="#15803D", filled=True, size=150,
    ).encode(y="ending_inventory:Q", tooltip=[alt.Tooltip("po_receipt:Q", title="PO到货", format=",.0f")])
    labels = base.transform_filter("datum.po_receipt > 0").mark_text(
        dy=-15, color="#15803D", fontSize=10, fontWeight="bold",
    ).encode(y="ending_inventory:Q", text=alt.Text("po_receipt:Q", format="+,.0f"))
    return (inventory + safety + zero + receipts + labels).properties(height=330).configure_view(strokeWidth=0).interactive()
