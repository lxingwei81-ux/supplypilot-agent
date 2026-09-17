from __future__ import annotations
import time
from .repository import load_table
from .tools import get_excess_portfolio,get_po_cancellation_alerts,get_ecn_switch_candidates,simulate_excess_scenario

def main()->None:
    rows=load_table("excess_risks");errors=[]
    for r in rows:
        expected=max(0,int(r["on_hand"])+int(r["open_po"])-int(r["demand_12w"]))
        if expected!=int(r["book_excess_qty"]):errors.append((r["material_id"],r["plant"],"book_excess"))
        allocated=sum(int(a["action_qty"]) for a in load_table("excess_action_plan") if a["material_id"]==r["material_id"] and a["plant"]==r["plant"])
        if allocated!=int(r["decision_excess_qty"]):errors.append((r["material_id"],r["plant"],"action_waterfall"))
    start=time.perf_counter()
    for _ in range(20):
        get_excess_portfolio(top_n=10);get_po_cancellation_alerts(top_n=10);get_ecn_switch_candidates(top_n=10);simulate_excess_scenario(rows[0]["material_id"],rows[0]["plant"],-0.2,100,50,50)
    elapsed=time.perf_counter()-start
    print(f"Excess risk records: {len(rows)}")
    print(f"Formula/action consistency pass rate: {(len(rows)-len(errors))/max(len(rows),1):.1%}")
    print(f"ECN candidates: {len(load_table('ecn_candidates'))}")
    print(f"Mean deterministic tool latency: {elapsed/80*1000:.3f}ms")
    if errors:print("Errors:",errors[:10])
if __name__=="__main__":main()
