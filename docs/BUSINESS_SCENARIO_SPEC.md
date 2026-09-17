# SupplyPilot V3 工程内业务场景规格

本文件把工作区上级《SupplyPilot V2 业务场景与智能体编排规格》映射到当前工程实现。上级文档仍是完整业务依据；本文件记录已经落地的第一、二阶段口径、工具和边界。

## 1. 责任边界

- 大模型：意图识别补充、解释、建议组织和自然语言报告。
- Python 服务：数据质量、分类、预测、指标、版本、BOM、库存、安全库存、风险、动作前后数量与金额。
- Agent 不连接或写回 ERP。所有高影响动作仅为 `PROPOSED/PENDING_APPROVAL`。

## 2. 三道防线

1. 需求预测：形成可回测的数据基线，人工只调整有未来证据的例外。
2. 库存计划：按需求/交期波动和服务水平计算安全库存，不以夸大预测代替缓冲。
3. 供应链执行：只有前两道防线未吸收的例外，才进入催交、PO、调拨、替代和 ECN。

动作前后必须重算周度投影；任何消冗动作若新增缺料，结论必须为不建议执行。

## 3. 场景路由

`src/router.py` 使用规则优先级和关键词覆盖：数据质量、需求增减、预测版本/人工调整、供应延期、静态/动态缺料、低于安全库存、冗余、呆滞、无需求有PO、EOL、PO提前/延期/减量/取消、调拨、替代、ECN和What-if。

路由结果固定包含：场景类型、置信度、触发规则、所需工具、缺失数据和人工确认标志。

## 4. 计算口径

```text
AnnualValue = AnnualDemand × UnitCost
CV = DemandStd / MeanDemand
ADI = TotalPeriods / NonZeroPeriods

ModelScore = w1×WAPE + w2×|Bias|
             + w3×StockoutLoss + w4×ExcessLoss

GrossRequirement[m,t] = Σ Forecast[i,t] × CumulativeBOMUsage[i,m]

Available = OnHand - Frozen - QualityHold - Allocated + ReusableReturn
Ending[t] = Beginning[t] + Receipts[t] + TransferIn[t]
            - Demand[t] - Reserved[t] - TransferOut[t]

SS = z × sqrt(MeanLT×DemandVariance + MeanDemand²×LeadTimeVariance)
```

所有参数来自 `config/rules.yaml`。缺少交期方差或服务水平时只允许使用配置中的显式默认值，并返回警告。

## 5. 数据质量门禁

阻断项：必填字段、日期、数值、重复记录、BOM循环/无效、单位换算。警告项：负库存、PO日期逻辑、生命周期、Forecast版本断档、实际偏离、冲销还原和历史周期不足。

预测可只对通过门禁的历史需求数据集运行；不能因为其他不相关表缺失而伪造输入。BOM/库存计算分别检查其所需的数据范围。

## 6. 审批矩阵

审批角色由 `rules.yaml` 加载：PO取消/减量/提前/延期/拆单、跨厂调拨、替代、ECN、需求调整、安全库存调整和报废均保留明确审批对象、责任部门、截止日期和状态。

## 7. 第二阶段分配与优化口径

### 7.1 共用料 ATP 与客户优先级

```text
AllocatableSupply = AvailableSupply - ProtectedSupply
PriorityScore = FrozenBonus + CustomerPriority
                + ShortagePenalty + DueUrgency + LifecyclePriority
```

冻结订单优先于预测，分配不得突破可分配供给。每笔结果保留排序、命中规则、请求量、分配量和未满足量。配置可启用最低公平份额，但公平份额同样受可用量上限约束。

### 7.2 多工厂调拨

```text
SourceAvailable = OnHand - Protected - FutureDemand - MinimumCoverage
```

只有物料/版本/质量兼容、交期不超过规则上限且预计到货不晚于需求日的通道可进入求解。确定性最小成本流优先消除高优先级缺口，任何来源工厂不得因为调拨跌破保护量。

### 7.3 PO 消冗与批量优化

PO取消/延期总量不得超过已经由逐周投影确认的决策冗余；锁定量、取消期限和 MPQ 是硬约束。目标比较持有成本、过时成本、取消罚金及延期收益。

联合补货优化枚举 MOQ、MPQ、包装倍数共同可行的数量，并按适用价格阶梯计算采购、持有、缺货和固定下单成本。价格和成本均来自数据或规则配置。

### 7.4 多情景成本

```text
ExpectedCost = Σ Probability[s] × (
  HoldingCost[s] + ShortageCost[s] + EndingExcessCost[s] + ActionCost
)
```

方案选择采用鲁棒可行门禁：必须在所有配置情景下都不制造缺料。不存在安全方案时返回 `INFEASIBLE`，不得退而推荐不安全动作。

## 8. 工作流、任务与治理

- ECN：候选、规格审查、试制、质量批准、客户批准（适用时）、最终批准或拒绝。每个节点检查角色和证据；批准必须包含生效批次和追溯规则。
- 预测调整：草稿、提交、商业评审、供应评审、待批准、批准、生效、FVA评价。实际结果出现前保持 `PENDING_ACTUALS`。
- 风险任务：风险等级映射 P0-P3；到期前提醒，逾期 1/3/7 天按配置升级。服务只生成记录，不发送外部通知。
- 周度快照：保留实体、工厂、指标、数据版本和快照周；提供 4/13/26 周趋势。
- Excel：别名建议、显式字段映射、日期/数字转换和阻断报告；不写回 ERP。
- 供应商可靠性：按准时率、数量齐套率、承诺遵从率和交期稳定性加权，样本不足时必须警告。
- 管理驾驶舱：只聚合底层确定性结果，不重新发明风险数量或收益。

## 9. 数据与实现限制

当前全部数据为合成 Demo。原 V2 表缺少完整历史需求、库存状态、逐周供给和交期方差，因此新增独立 Demo 表用于闭环演示。任务、工作流和版本默认使用进程内存储，快照可选本地 JSON；生产环境需接入数据库、权限和审计。当前调拨为确定性最小成本流，未包含税费、币种、复杂供应商产能和跨期价格阶梯。不声称生产准确率、降本比例或库存收益。
