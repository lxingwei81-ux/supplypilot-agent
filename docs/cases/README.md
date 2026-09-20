# SupplyPilot业务案例库

本案例库使用仓库中的合成Demo数据。每个案例按照“业务问题 → 输入 → 公式/规则 → 确定性结果 → 动作和审批”组织，可以独立复现。

第一次查看项目建议从[案例12：Control Tower Hero Demo](12-control-tower-hero.md)开始。它把需求、库存、供应商、跨厂调拨、PO消冗和AI Copilot证据串成一条完整决策链。

## 案例导航

| # | 场景 | 主要能力 | 运行命令 |
|---:|---|---|---|
| 1 | [需求下降导致库存冗余](01-demand-decline-excess.md) | Forecast变化、BOM、冗余、PO/ECN | `python examples/run_cases.py --case 1` |
| 2 | [需求上升与供应延期导致缺料](02-demand-rise-shortage.md) | 首次缺料、PO提前、跨厂调拨 | `python examples/run_cases.py --case 2` |
| 3 | [总量不缺但中间周缺料](03-middle-week-shortage.md) | 周度投影、供需时序 | `python examples/run_cases.py --case 3` |
| 4 | [间歇性需求预测](04-intermittent-demand.md) | ADI/CV²、Croston/SBA/TSB | `python examples/run_cases.py --case 4` |
| 5 | [人工预测调整与FVA](05-forecast-adjustment-fva.md) | 版本、审批、实际后评价 | `python examples/run_cases.py --case 5` |
| 6 | [共用料ATP和客户优先级](06-shared-material-atp.md) | 保护量、冻结订单、分配解释 | `python examples/run_phase2_cases.py --case 1` |
| 7 | [多工厂调拨优化](07-cross-plant-transfer.md) | 来源保护、通道约束、最小成本流 | `python examples/run_phase2_cases.py --case 2` |
| 8 | [PO取消与延期成本优化](08-po-cancellation-optimization.md) | 取消窗口、锁定量、MPQ、罚金 | `python examples/run_phase2_cases.py --case 3` |
| 9 | [MOQ/MPQ与价格阶梯](09-moq-mpq-price-break.md) | 批量约束、价格阶梯、总成本 | `python examples/run_phase2_cases.py --case 4` |
| 10 | [ECN验证状态机](10-ecn-workflow.md) | 规格、试制、质量、客户与追溯 | `python examples/run_phase2_cases.py --case 5` |
| 11 | [多情景库存成本优化](11-multi-scenario-optimization.md) | 概率成本、鲁棒可行门禁 | `python examples/run_phase2_cases.py --case 10` |
| 12 | [Control Tower Hero Demo](12-control-tower-hero.md) | MAT-B缺料、跨厂调拨、MAT-A消冗、结构化Copilot | `python -m streamlit run app.py` |

## 运行全部案例

```powershell
python examples/run_cases.py --case all
python examples/run_phase2_cases.py --case all
```

第二阶段脚本还包含快照趋势、Excel映射、任务升级、供应商可靠性和管理驾驶舱演示，可使用`--case 6`至`--case 11`分别运行。

## 结果解释原则

- 所有数量和金额由Python服务计算；
- 结果包含适用的数据版本、规则版本或证据；
- Demo成本、服务水平和阈值不代表生产参数；
- Forecast上下限是规则化情景带，不是概率校准的统计置信区间；
- “建议执行”不等于自动执行，高影响动作仍需审批；
- 原V2兼容数据中的质量阻断项仍保留，控制塔使用隔离的`DEMO-*`数据版本，不代表旧数据已经修复；
- 案例结果只证明逻辑和软件可以复现，不代表真实库存收益或预测准确率。

[返回项目首页](../../README.md) · [查看公式手册](../FORMULA_CATALOG.md)
