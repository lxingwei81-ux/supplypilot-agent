# SupplyPilot Demo 数据字典

## 原V2表（保留）

| 表 | 主用途 | 主要键/字段 | 当前限制 |
|---|---|---|---|
| products | 产品/客户/月需求 | product_id, plant, customer, lifecycle | 月粒度，不是历史周需求 |
| materials | 物料、LT、MOQ、价格 | material_id | 缺MPQ、包装倍数、交期方差 |
| bom | 两层BOM | product_id, parent_id, child_id | 缺失效日、损耗和单位换算 |
| future_mps | 未来成品周需求 | version, product_id, week_start | 无历史实际值 |
| material_demand | 已拆解物料周需求 | product_id, material_id, week_no | 由静态Demo预生成 |
| inventory_positions | 8周库存汇总 | material_id, plant | 缺冻结/质检/分配明细 |
| procurement | PR/PO汇总 | document_id, material_id, plant | 存在18组重复单号 |
| po_flexibility | 单据灵活性 | document_id, cancelable_qty | 周号口径，无完整日历时间 |
| exceptions | 已生成例外 | exception_id | 静态演示结果 |
| excess_risks | 冗余快照 | material_id, plant | 12周汇总而非逐周流水 |
| excess_action_plan | 消冗动作 | action_id | 静态演示任务 |
| ecn_candidates | ECN候选 | source_material, target_material | 候选不等于批准替代 |

## 新增Demo表

所有行的 `source_type` 均为 `DEMO`。

| 表 | 关键字段 | 用途 |
|---|---|---|
| demo_historical_demand | item_id, week_start, demand_qty, unit_cost, lifecycle, data_version | 分类、预测和回测 |
| demo_bom_extended | product_id, parent_id, child_id, loss_rate, conversion_factor, effective_from/to | 多级BOM、损耗、版本 |
| demo_item_planning | item_id, lead_time_variance, service_level, moq, mpq, package_multiple | 安全库存和补货 |
| demo_weekly_inventory | case_id, material_id, plant, week_start, demand/receipt/status fields | 逐周库存与动作模拟 |
| demo_forecast_versions | version_id, item_id, version_type, status, forecast_qty | 版本演示 |
| demo_forecast_adjustments | adjustment_id, before/after, reason, approvers | 人工调整审计 |
| demo_atp_demand | demand_id, material_id, customer_id, requested_qty, frozen_order, customer_priority | 共用料ATP和多客户优先级 |
| demo_transfer_sources | plant, material_id, on_hand, protected_qty, future_demand, minimum_coverage_qty | 调拨来源保护量 |
| demo_transfer_targets | plant, material_id, shortage_qty, need_date, priority | 多工厂缺口目标 |
| demo_transfer_lanes | source_plant, target_plant, lead_time_days, unit_cost, fixed_cost, compatible | 调拨通道和兼容性 |
| demo_po_optimization | document_id, open/cancelable/reschedulable/locked_qty, penalty, deadline, mpq | PO取消/延期成本优化 |
| demo_price_breaks | material_id, minimum_qty, unit_price, moq, mpq, package_multiple | 采购批量和价格阶梯 |
| demo_supplier_deliveries | supplier_id, promised/confirmed/actual_date, ordered/received_qty | 供应商交期和齐套可靠性 |
| demo_supplier_assignments | material_id, supplier_id, valid_from/to, mapping_version | 带有效期的物料—供应商映射及Copilot证据追溯 |

## 第二阶段运行时对象

下列对象由 Pydantic 模型校验，不作为静态 CSV 保存：

| 对象 | 关键字段 | 用途 |
|---|---|---|
| ATPAllocationResult | allocatable_supply, total_allocated, allocations, trace | 分配结果和规则追溯 |
| TransferOptimizationResult | recommendations, shortage_before/after, cost, infeasible_reasons | 多工厂调拨方案 |
| POOptimizationResult | cancel/delay_qty, penalty, avoided_cost, excess_after | PO动作成本比较 |
| ProcurementOptimizationResult | recommended_order_qty, selected_unit_price, total_cost | MOQ/MPQ/价格阶梯联合选择 |
| ECNWorkflow | current_status, evidence, approvals, effective_batch, history | ECN验证状态机 |
| ForecastAdjustmentWorkflow | reviewers, approver, adjusted_version_id, fva_status | 人工预测调整审计 |
| WeeklySnapshot / SnapshotTrend | as_of_week, metrics, source_versions, direction | 周快照和趋势 |
| ExcelImportResult | mapped_fields, rows, issues, status | Excel导入门禁 |
| RiskTask / TaskNotification | priority, status, due_date, escalation_level | 风险任务和升级 |
| SupplierReliabilityResult | OTD, fill, adherence, stability, grade | 供应商履约评价 |
| MultiScenarioOptimizationResult | expected_cost, robust_feasible_decisions, selected_decision | 多情景库存优化 |
| ManagementDashboard | blocker/risk/task/supplier aggregates | 管理驾驶舱 |
| ControlTowerSnapshot | KPI、需求趋势、风险热力、投影、动作校验、数据质量、版本 | 五大工作区共用的单一口径快照 |
| StructuredCopilotResponse | summary、evidence、root_causes、recommendations、impact、rules、limitations | 可验证的Copilot决策说明，不包含自由生成数量 |

## 版本和追溯

核心输出包含 `data_version`、`source_version`、`forecast_version_id`、`rules_version`、计算时间或证据来源。Demo版本以 `DEMO-*` 命名，不得与生产版本混用。运行时任务、工作流和快照若用于生产，必须迁移到带权限、并发控制和审计的持久化存储。
