from __future__ import annotations
import json
from collections import defaultdict
from datetime import date, timedelta
from typing import Any
from .repository import load_table,table_index
from .models import (
    ABCClass, Action, ATPDemand, DemandClassification, DemandScenario,
    ECNValidationStatus, ECNWorkflow, FieldMapping, InventoryDecision,
    InventoryProjectionInput, POOption, PriceBreak, ProductLifecycle,
    SupplierDeliveryRecord, TransferLane, TransferSource, TransferTarget, XYZClass,
)
from .router import route_scenario
from .services.action_validation import validate_action_impact
from .services.allocation import allocate_shared_material_atp
from .services.bom import cumulative_usage_by_material, explode_bom
from .services.data_quality import assess_project_data
from .services.demand_classification import classify_demand
from .services.forecasting import generate_forecast
from .services.ecn_workflow import transition_ecn
from .services.excel_import import import_excel
from .services.inventory_policy import calculate_inventory_policy
from .services.inventory_projection import project_inventory_by_week
from .services.procurement_optimization import optimize_po_reduction_plan, optimize_replenishment_order
from .services.risks import identify_projection_risks
from .services.scenario_optimization import optimize_inventory_across_scenarios
from .services.supplier_reliability import calculate_supplier_reliability
from .services.transfer_optimization import optimize_cross_plant_transfer

def _json(data:Any)->str:return json.dumps(data,ensure_ascii=False,indent=2,default=str)

def get_mps_changes(top_n:int=10,direction:str="全部")->str:
    rows=load_table("mps_compare")
    if direction in {"增加","减少"}:rows=[r for r in rows if r["change_direction"]==direction]
    return _json(sorted(rows,key=lambda r:abs(float(r["reconciled_change"])),reverse=True)[:top_n])

def get_product_bom(product_id:str)->str:
    bom=load_table("bom");l1=[r for r in bom if r["level"]==1 and r["product_id"]==product_id]
    assemblies={r["child_id"] for r in l1};l2=[r for r in bom if r["level"]==2 and r["parent_id"] in assemblies]
    effective_dates=[date.fromisoformat(str(r["effective_date"])[:10]) for r in l1 if r.get("effective_date")]
    recursive=cumulative_usage_by_material(product_id,bom,as_of=min(effective_dates) if effective_dates else date.today()) if l1 else {}
    return _json({"product_id":product_id,"level1":l1,"level2":l2,"recursive_cumulative_usage":recursive,"contract_version":"legacy-compatible-v2"})

def get_material_commonality(material_id:str)->str:
    row=table_index("materials","material_id").get(material_id)
    if not row:return _json({"error":f"未找到物料 {material_id}"})
    products=table_index("products","product_id");ids=[x for x in str(row.get("shared_models","")).split(";") if x]
    return _json({"material_id":material_id,"dedication_type":row.get("dedication_type"),"lead_time_days":row.get("lead_time_days"),"shared_models":[{"product_id":pid,"product_name":products.get(pid,{}).get("product_name",""),"lifecycle":products.get(pid,{}).get("lifecycle",""),"priority":products.get(pid,{}).get("priority","")} for pid in ids]})

def diagnose_product_risk(product_id:str,lt_threshold:int=30)->str:
    materials=table_index("materials","material_id");inv=load_table("inventory_positions");exceptions=load_table("exceptions")
    bom=json.loads(get_product_bom(product_id));raw_ids={r["child_id"] for r in bom.get("level2",[])};result=[]
    for mid in raw_ids:
        m=materials.get(mid,{});positions=[r for r in inv if r["material_id"]==mid]
        related=[e for e in exceptions if e["object_id"]==mid and product_id in str(e.get("related_models","")).split(";")]
        if int(m.get("lead_time_days",0) or 0)>lt_threshold or related:result.append({"material":m,"inventory_positions":positions,"exceptions":related})
    return _json({"product_id":product_id,"risk_materials":result})

def list_exceptions(exception_type:str="",severity:str="",plant:str="",limit:int=50)->str:
    rows=load_table("exceptions")
    if exception_type:rows=[r for r in rows if r["exception_type"]==exception_type]
    if severity:rows=[r for r in rows if r["severity"]==severity]
    if plant:rows=[r for r in rows if r["plant"]==plant]
    return _json(sorted(rows,key=lambda r:float(r["risk_score"]),reverse=True)[:limit])

def build_procurement_action_list(plant:str="")->str:
    types={"PR_NOT_CONVERTED","PO_LATE","LONG_LT_SHORTAGE","DEDICATED_EOL_EXCESS","INVENTORY_EXCESS_RISK"}
    rows=[r for r in load_table("exceptions") if r["exception_type"] in types and (not plant or r["plant"]==plant)]
    return _json(sorted(rows,key=lambda r:float(r["risk_score"]),reverse=True))

def get_transfer_opportunities(target_plant:str="")->str:
    return _json([r for r in load_table("exceptions") if r["exception_type"]=="TRANSFER_OPPORTUNITY" and (not target_plant or r["plant"]==target_plant)])

def get_excess_portfolio(plant:str="",severity:str="",risk_type:str="",top_n:int=20)->str:
    """查询库存冗余组合，区分账面冗余、决策冗余、可取消/延期在途与最终滞留数量。"""
    rows=load_table("excess_risks")
    if plant:rows=[r for r in rows if r["plant"]==plant]
    if severity:rows=[r for r in rows if r["severity"]==severity]
    if risk_type:rows=[r for r in rows if r["risk_type"]==risk_type]
    rows=sorted(rows,key=lambda r:(float(r["risk_score"]),float(r["decision_excess_value"])),reverse=True)[:top_n]
    return _json(rows)

def get_excess_action_plan(material_id:str,plant:str="")->str:
    """返回指定物料的分层冗余处置瀑布：停采、取消/延期PO、调拨、共用消耗、ECN、退换及计提。"""
    risks=[r for r in load_table("excess_risks") if r["material_id"]==material_id and (not plant or r["plant"]==plant)]
    actions=[r for r in load_table("excess_action_plan") if r["material_id"]==material_id and (not plant or r["plant"]==plant)]
    return _json({"risk":risks,"actions":sorted(actions,key=lambda r:(r["plant"],r["sequence"]))})

def get_po_cancellation_alerts(plant:str="",min_excess_value:float=0,top_n:int=50)->str:
    """列出可取消或延期的PR/PO，包含取消窗口、违约成本和人工审批要求。"""
    risks={(r["material_id"],r["plant"]):r for r in load_table("excess_risks")}
    rows=[]
    for po in load_table("po_flexibility"):
        risk=risks.get((po["material_id"],po["plant"]))
        if not risk or float(risk["decision_excess_value"])<min_excess_value:continue
        if plant and po["plant"]!=plant:continue
        if int(po["cancelable_qty"])+int(po["reschedulable_qty"])<=0:continue
        rows.append({**po,"decision_excess_qty":risk["decision_excess_qty"],"decision_excess_value":risk["decision_excess_value"],"severity":risk["severity"],"primary_action":risk["primary_action"]})
    return _json(sorted(rows,key=lambda r:float(r["decision_excess_value"]),reverse=True)[:top_n])

def get_ecn_switch_candidates(source_material:str="",min_score:int=70,top_n:int=30)->str:
    """查询ECN切换消耗候选；仅作为工程验证线索，不代表可直接替换。"""
    rows=load_table("ecn_candidates")
    if source_material:rows=[r for r in rows if r["source_material"]==source_material]
    rows=[r for r in rows if int(r["compatibility_score"])>=min_score]
    return _json(sorted(rows,key=lambda r:(int(r["compatibility_score"]),int(r["potential_consume_qty"])),reverse=True)[:top_n])

def simulate_excess_scenario(material_id:str,plant:str,demand_change_rate:float=0,cancel_po_qty:int=0,ecn_consume_qty:int=0,transfer_qty:int=0)->str:
    """模拟需求变化、取消PO、ECN消耗和跨厂调拨后的冗余风险，不写回业务数据。"""
    rows=[r for r in load_table("excess_risks") if r["material_id"]==material_id and r["plant"]==plant]
    if not rows:return _json({"error":"未找到对应物料-工厂的冗余记录"})
    r=rows[0];new_demand=max(0,round(float(r["demand_12w"])*(1+demand_change_rate)))
    new_po=max(0,int(r["open_po"])-max(0,cancel_po_qty))
    start=min(date.fromisoformat(str(row["week_start"])[:10]) for row in load_table("future_mps"))
    from .models import WeeklyInventoryInput
    eta_rows=[row for row in load_table("po_flexibility") if row["material_id"]==material_id and row["plant"]==plant]
    eta_week=max(1,min(12,int(eta_rows[0]["eta_week"]))) if eta_rows else 12
    def projection_input(demand_total:float,po_total:float,ecn_qty:float=0,transfer_out:float=0)->InventoryProjectionInput:
        weeks=[]
        for index in range(12):
            weeks.append(WeeklyInventoryInput(
                week_start=start+timedelta(days=7*index),
                gross_demand=demand_total/12+(ecn_qty if index==0 else 0),
                safety_stock=float(r["protected_qty"]),
                po_receipt=po_total if index+1==eta_week else 0,
                transfer_out=transfer_out if index==0 else 0,
            ))
        return InventoryProjectionInput(material_id=material_id,plant=plant,on_hand=float(r["on_hand"]),weeks=weeks,data_version="LEGACY-DEMO-V2",source_versions={"excess_risks":"CURRENT"})
    baseline=project_inventory_by_week(projection_input(float(r["demand_12w"]),float(r["open_po"])))
    scenario=project_inventory_by_week(projection_input(new_demand,new_po,max(0,ecn_consume_qty),max(0,transfer_qty)))
    new_excess=round(scenario.ending_excess_qty)
    new_value=round(new_excess*float(r["unit_price"]),2)
    ratio=new_excess/max(new_demand+int(r["protected_qty"]),1)
    score=max(0,min(100,round(25*min(ratio,1)+20*min(new_value/500000,1)+(20 if r["eom_model_count"] and not r["active_model_count"] else 5)+(15 if r["dedication_type"]=="专用料" else 5))))
    severity="Critical" if score>=75 else ("High" if score>=55 else ("Medium" if score>=35 else "Low"))
    return _json({"material_id":material_id,"plant":plant,"base_demand_12w":r["demand_12w"],"new_demand_12w":new_demand,"base_open_po":r["open_po"],"new_open_po":new_po,"new_decision_excess_qty":new_excess,"new_excess_value":new_value,"new_risk_score":score,"new_severity":severity,"creates_new_shortage":scenario.maximum_shortage_qty>baseline.maximum_shortage_qty,"baseline_first_shortage_week":baseline.first_shortage_week,"scenario_first_shortage_week":scenario.first_shortage_week,"calculation_basis":"12周逐周库存投影（旧汇总数据等分需求）","note":"旧数据缺少周需求和周到货明细，结果为兼容演示口径；正式动作必须使用validate_action_impact_v2并经人工审批"})


def _validated_json(value:Any)->str:
    if hasattr(value,"model_dump"):
        return _json(value.model_dump(mode="json"))
    return _json(value)


def _error(code:str,message:str,details:Any=None)->str:
    return _json({"ok":False,"error":{"code":code,"message":message,"details":details}})


def run_data_quality_v2()->str:
    """运行结构化项目数据质量检查；阻断问题会明确返回can_proceed=false。"""
    return _validated_json(assess_project_data())


def classify_demand_v2(item_id:str,history:list[float],unit_cost:float=0,lifecycle:str="MATURE",source_version:str="DEMO")->str:
    """执行ABC/XYZ/ADI-CV²和生命周期分类。"""
    try:
        result=classify_demand({item_id:history},unit_costs={item_id:unit_cost},lifecycles={item_id:lifecycle},source_version=source_version)[0]
        return _validated_json(result)
    except Exception as exc:
        return _error("DEMAND_CLASSIFICATION_ERROR",str(exc))


def forecast_demand_v2(item_id:str,history:list[float],unit_cost:float=0,lifecycle:str="MATURE",last_history_week:str="2026-07-20",source_version:str="DEMO")->str:
    """执行需求分类、多模型滚动回测、模型选择并输出未来4/8/13/26周预测。"""
    try:
        classification=classify_demand({item_id:history},unit_costs={item_id:unit_cost},lifecycles={item_id:lifecycle},source_version=source_version)[0]
        result=generate_forecast(item_id,history,classification,last_history_week=date.fromisoformat(last_history_week),history_source=source_version,stockout_unit_cost=unit_cost)
        return _validated_json(result)
    except Exception as exc:
        return _error("FORECAST_ERROR",str(exc))


def explode_bom_demand_v2(product_id:str,weekly_forecast:dict[str,float],forecast_version_id:str,bom_table:str="bom")->str:
    """按有效版本递归展开任意层级BOM，保留路径、损耗和单位换算。"""
    try:
        weeks={date.fromisoformat(week):float(quantity) for week,quantity in weekly_forecast.items()}
        result=explode_bom(product_id,weeks,load_table(bom_table),forecast_version_id=forecast_version_id,source=bom_table)
        return _validated_json([row.model_dump(mode="json") for row in result])
    except Exception as exc:
        return _error("BOM_EXPLOSION_ERROR",str(exc))


def project_inventory_by_week_v2(payload:dict[str,Any])->str:
    """验证输入并逐周计算可用库存、到货、需求、缺口、冗余和覆盖周数。"""
    try:
        result=project_inventory_by_week(InventoryProjectionInput.model_validate(payload))
        return _validated_json(result)
    except Exception as exc:
        return _error("INVENTORY_PROJECTION_ERROR",str(exc))


def calculate_inventory_policy_v2(payload:dict[str,Any])->str:
    """根据服务水平、需求/交期波动及MOQ/MPQ计算安全库存与补货量。"""
    try:
        return _validated_json(calculate_inventory_policy(**payload))
    except Exception as exc:
        return _error("INVENTORY_POLICY_ERROR",str(exc))


def identify_risks_v2(projection_payload:dict[str,Any],unit_cost:float,context:dict[str,Any]|None=None)->str:
    """基于真实逐周投影识别缺料、低于安全库存和冗余风险。"""
    try:
        projection=project_inventory_by_week(InventoryProjectionInput.model_validate(projection_payload))
        return _validated_json([risk.model_dump(mode="json") for risk in identify_projection_risks(projection,unit_cost=unit_cost,context=context)])
    except Exception as exc:
        return _error("RISK_CALCULATION_ERROR",str(exc))


def route_scenario_v2(query:str,facts:dict[str,Any]|None=None,available_data:list[str]|None=None)->str:
    """使用显式业务规则进行场景路由；LLM只作为上层自然语言补充。"""
    try:
        return _validated_json(route_scenario(query,facts=facts,available_data=set(available_data or [])))
    except Exception as exc:
        return _error("SCENARIO_ROUTING_ERROR",str(exc))


def validate_action_impact_v2(action_payload:dict[str,Any],projection_payload:dict[str,Any],related_projection_payloads:list[dict[str,Any]]|None=None,unit_cost:float=0)->str:
    """在内存情景中应用动作、重算投影并拒绝制造新缺料的方案，不写回源数据。"""
    try:
        action=Action.model_validate(action_payload)
        projection=InventoryProjectionInput.model_validate(projection_payload)
        related=[InventoryProjectionInput.model_validate(payload) for payload in (related_projection_payloads or [])]
        return _validated_json(validate_action_impact(action,projection,related_inputs=related,unit_cost=unit_cost))
    except Exception as exc:
        return _error("ACTION_VALIDATION_ERROR",str(exc))


def allocate_shared_material_atp_v3(material_id:str,available_supply:float,protected_supply:float,demand_payloads:list[dict[str,Any]],source_versions:dict[str,str]|None=None)->str:
    """按冻结订单、客户优先级、停线损失、需求日期和生命周期分配共用料ATP。"""
    try:
        demands=[ATPDemand.model_validate(payload) for payload in demand_payloads]
        return _validated_json(allocate_shared_material_atp(material_id,available_supply=available_supply,protected_supply=protected_supply,demands=demands,source_versions=source_versions))
    except Exception as exc:
        return _error("ATP_ALLOCATION_ERROR",str(exc))


def optimize_cross_plant_transfer_v3(material_id:str,as_of_date:str,source_payloads:list[dict[str,Any]],target_payloads:list[dict[str,Any]],lane_payloads:list[dict[str,Any]])->str:
    """在来源保护量、到货时限和兼容性约束下执行多工厂最小成本流调拨。"""
    try:
        result=optimize_cross_plant_transfer(material_id,as_of_date=date.fromisoformat(as_of_date),sources=[TransferSource.model_validate(item) for item in source_payloads],targets=[TransferTarget.model_validate(item) for item in target_payloads],lanes=[TransferLane.model_validate(item) for item in lane_payloads])
        return _validated_json(result)
    except Exception as exc:
        return _error("TRANSFER_OPTIMIZATION_ERROR",str(exc))


def optimize_po_reduction_plan_v3(material_id:str,plant:str,excess_qty:float,po_payloads:list[dict[str,Any]],as_of_date:str,horizon_weeks:int=13)->str:
    """同时评估取消罚金、持有/过时成本、锁定量、取消窗口和MPQ。"""
    try:
        return _validated_json(optimize_po_reduction_plan(material_id,plant,excess_qty=excess_qty,po_options=[POOption.model_validate(item) for item in po_payloads],as_of_date=date.fromisoformat(as_of_date),horizon_weeks=horizon_weeks))
    except Exception as exc:
        return _error("PO_OPTIMIZATION_ERROR",str(exc))


def optimize_replenishment_v3(material_id:str,required_qty:float,price_break_payloads:list[dict[str,Any]],moq:float,mpq:float,package_multiple:float)->str:
    """联合优化MOQ、MPQ、包装倍数和价格阶梯，不满足约束的数量不会被推荐。"""
    try:
        return _validated_json(optimize_replenishment_order(material_id,required_qty=required_qty,price_breaks=[PriceBreak.model_validate(item) for item in price_break_payloads],moq=moq,mpq=mpq,package_multiple=package_multiple))
    except Exception as exc:
        return _error("REPLENISHMENT_OPTIMIZATION_ERROR",str(exc))


def transition_ecn_v3(workflow_payload:dict[str,Any],to_status:str,actor:str,role:str,evidence_updates:dict[str,str]|None=None,effective_batch:str|None=None,traceability_rule:str|None=None)->str:
    """执行受证据和角色约束的ECN状态迁移；候选不会直接变成批准替代。"""
    try:
        workflow=ECNWorkflow.model_validate(workflow_payload)
        result=transition_ecn(workflow,ECNValidationStatus(to_status),actor=actor,role=role,evidence_updates=evidence_updates,effective_batch=effective_batch,traceability_rule=traceability_rule)
        return _validated_json(result)
    except Exception as exc:
        return _error("ECN_WORKFLOW_ERROR",str(exc))


def import_excel_v3(path:str,sheet_name:str,mapping_payloads:list[dict[str,Any]],data_version:str)->str:
    """根据显式字段映射读取Excel并返回类型校验和阻断问题，不写回ERP。"""
    try:
        return _validated_json(import_excel(path,sheet_name=sheet_name,mappings=[FieldMapping.model_validate(item) for item in mapping_payloads],data_version=data_version))
    except Exception as exc:
        return _error("EXCEL_IMPORT_ERROR",str(exc))


def supplier_reliability_v3(supplier_id:str,record_payloads:list[dict[str,Any]])->str:
    """计算供应商准时率、数量满足率、确认遵从率和交期稳定性。"""
    try:
        return _validated_json(calculate_supplier_reliability(supplier_id,[SupplierDeliveryRecord.model_validate(item) for item in record_payloads]))
    except Exception as exc:
        return _error("SUPPLIER_RELIABILITY_ERROR",str(exc))


def optimize_inventory_scenarios_v3(baseline_payload:dict[str,Any],scenario_payloads:list[dict[str,Any]],decision_payloads:list[dict[str,Any]])->str:
    """按概率比较多个需求/供给情景，只从所有情景均不缺料的方案中选择最低期望成本。"""
    try:
        return _validated_json(optimize_inventory_across_scenarios(InventoryProjectionInput.model_validate(baseline_payload),scenarios=[DemandScenario.model_validate(item) for item in scenario_payloads],decisions=[InventoryDecision.model_validate(item) for item in decision_payloads]))
    except Exception as exc:
        return _error("SCENARIO_OPTIMIZATION_ERROR",str(exc))
