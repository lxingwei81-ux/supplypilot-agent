from __future__ import annotations
import asyncio,json,os
from agents import Agent,Runner,function_tool
from . import tools as domain
@function_tool
def get_mps_changes(top_n:int=10,direction:str="全部")->str:"""查询MPS版本净需求变化。""";return domain.get_mps_changes(top_n,direction)
@function_tool
def get_product_bom(product_id:str)->str:"""展开产品多级BOM。""";return domain.get_product_bom(product_id)
@function_tool
def get_material_commonality(material_id:str)->str:"""判断物料共专用属性并列出共用机型。""";return domain.get_material_commonality(material_id)
@function_tool
def diagnose_product_risk(product_id:str,lt_threshold:int=30)->str:"""诊断产品需求变化后的物料供给风险。""";return domain.diagnose_product_risk(product_id,lt_threshold)
@function_tool
def list_exceptions(exception_type:str="",severity:str="",plant:str="",limit:int=50)->str:"""筛选计划和采购例外。""";return domain.list_exceptions(exception_type,severity,plant,limit)
@function_tool
def build_procurement_action_list(plant:str="")->str:"""生成采购协同动作清单。""";return domain.build_procurement_action_list(plant)
@function_tool
def get_transfer_opportunities(target_plant:str="")->str:"""查询跨工厂调拨机会。""";return domain.get_transfer_opportunities(target_plant)
@function_tool
def get_excess_portfolio(plant:str="",severity:str="",risk_type:str="",top_n:int=20)->str:"""查询库存冗余风险组合。""";return domain.get_excess_portfolio(plant,severity,risk_type,top_n)
@function_tool
def get_excess_action_plan(material_id:str,plant:str="")->str:"""生成指定物料的分层冗余处置计划。""";return domain.get_excess_action_plan(material_id,plant)
@function_tool
def get_po_cancellation_alerts(plant:str="",min_excess_value:float=0,top_n:int=50)->str:"""生成可取消或延期的PR/PO预警清单。""";return domain.get_po_cancellation_alerts(plant,min_excess_value,top_n)
@function_tool
def get_ecn_switch_candidates(source_material:str="",min_score:int=70,top_n:int=30)->str:"""查询ECN切换消耗候选和验证路径。""";return domain.get_ecn_switch_candidates(source_material,min_score,top_n)
@function_tool
def simulate_excess_scenario(material_id:str,plant:str,demand_change_rate:float=0,cancel_po_qty:int=0,ecn_consume_qty:int=0,transfer_qty:int=0)->str:"""模拟动作后的剩余冗余风险。""";return domain.simulate_excess_scenario(material_id,plant,demand_change_rate,cancel_po_qty,ecn_consume_qty,transfer_qty)
@function_tool
def run_data_quality_v2()->str:"""运行数据质量门禁并返回结构化问题。""";return domain.run_data_quality_v2()
@function_tool
def classify_demand_v2(item_id:str,history:list[float],unit_cost:float=0,lifecycle:str="MATURE",source_version:str="DEMO")->str:"""执行ABC/XYZ/间歇性及生命周期分类。""";return domain.classify_demand_v2(item_id,history,unit_cost,lifecycle,source_version)
@function_tool
def forecast_demand_v2(item_id:str,history:list[float],unit_cost:float=0,lifecycle:str="MATURE",last_history_week:str="2026-07-20",source_version:str="DEMO")->str:"""运行多模型滚动回测并输出4/8/13/26周预测。""";return domain.forecast_demand_v2(item_id,history,unit_cost,lifecycle,last_history_week,source_version)
@function_tool
def route_scenario_v2(query:str)->str:"""使用确定性规则路由业务场景。""";return domain.route_scenario_v2(query)
@function_tool
def allocate_shared_material_atp_v3(material_id:str,available_supply:float,protected_supply:float,demand_json:str)->str:"""按客户、冻结订单和业务优先级分配共用料ATP；demand_json为需求数组。""";return domain.allocate_shared_material_atp_v3(material_id,available_supply,protected_supply,json.loads(demand_json))
@function_tool
def optimize_cross_plant_transfer_v3(material_id:str,as_of_date:str,source_json:str,target_json:str,lane_json:str)->str:"""运行多工厂最小成本流调拨；三个JSON参数分别为来源、目标和运输通道数组。""";return domain.optimize_cross_plant_transfer_v3(material_id,as_of_date,json.loads(source_json),json.loads(target_json),json.loads(lane_json))
@function_tool
def optimize_po_reduction_plan_v3(material_id:str,plant:str,excess_qty:float,po_json:str,as_of_date:str)->str:"""联合取消罚金、持有成本、锁定量、窗口和MPQ优化PO；po_json为单据数组。""";return domain.optimize_po_reduction_plan_v3(material_id,plant,excess_qty,json.loads(po_json),as_of_date)
@function_tool
def optimize_replenishment_v3(material_id:str,required_qty:float,price_break_json:str,moq:float,mpq:float,package_multiple:float)->str:"""联合MOQ、MPQ、包装倍数和价格阶梯优化补货。""";return domain.optimize_replenishment_v3(material_id,required_qty,json.loads(price_break_json),moq,mpq,package_multiple)
@function_tool
def supplier_reliability_v3(supplier_id:str,delivery_json:str)->str:"""计算供应商准时、数量满足、确认遵从和交期稳定性；delivery_json为交付记录数组。""";return domain.supplier_reliability_v3(supplier_id,json.loads(delivery_json))
agent=Agent(name="SupplyPilot",model=os.getenv("OPENAI_MODEL","gpt-5-nano"),instructions=("你是制造业供应链需求预测、库存计划、异常诊断与采购协同智能体。遵循三道防线：先验证和预测需求，再量化库存缓冲，最后编排执行例外。所有数量、金额、预测指标、BOM用量、投影库存、ATP、调拨和采购优化必须来自确定性工具，禁止自行计算或编造。数据质量存在阻断问题时停止后续计算并列出缺口。预测从数据开始，以有证据且带原因码的人工判断结束；NPI无相似品或项目证据时不得输出伪精确预测。共用料分配必须显示被满足与被牺牲的需求及规则；调拨必须保护来源工厂；采购优化必须显示MOQ/MPQ/价格阶梯和不可行原因。冗余处置顺序为冻结新增采购→删除PR/取消未锁定PO→延期PO→调拨/共用消耗→ECN验证→退换→计提/报废。任何动作都必须先重算逐周投影；制造新缺料的消冗动作必须拒绝。取消PO、调拨、替代、ECN和报废只生成建议，必须显示责任部门、截止日期、审批人、执行状态和残余风险，不连接或写回ERP。"),tools=[run_data_quality_v2,classify_demand_v2,forecast_demand_v2,route_scenario_v2,allocate_shared_material_atp_v3,optimize_cross_plant_transfer_v3,optimize_po_reduction_plan_v3,optimize_replenishment_v3,supplier_reliability_v3,get_mps_changes,get_product_bom,get_material_commonality,diagnose_product_risk,list_exceptions,build_procurement_action_list,get_transfer_opportunities,get_excess_portfolio,get_excess_action_plan,get_po_cancellation_alerts,get_ecn_switch_candidates,simulate_excess_scenario])
async def ask(question:str)->str:
    result=await Runner.run(agent,question);return result.final_output
if __name__=="__main__":print(asyncio.run(ask(input("SupplyPilot > ").strip())))
