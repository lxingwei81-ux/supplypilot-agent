# 案例2：需求上升与供应延期导致缺料

## 业务问题

客户需求上升，同时供应商交期延长。系统需要定位首次缺料周、最大缺口，并比较PO提前和跨厂调拨方案。

## 输入

- 物料：`MAT-B`；
- 目标工厂：`TARGET_PLANT`；
- 来源工厂：`SOURCE_PLANT`；
- 单位成本：45；
- PO提前数量：5,000；
- 跨厂调拨数量：2,000。

## 基准结果

逐周投影识别：

| 指标 | 基准 |
|---|---:|
| 首次缺料周 | 2026-08-24 |
| 最大缺口 | 8,800 |

缺口计算：

$$
Shortage_t=\max(0,-EndingInventory_t)
$$

静态缺口只能描述总量，动态缺口还必须回答“哪一周开始、持续多久、何时到货”。

## 方案比较

### PO提前

将5,000数量的既有PO从原到货周提前：

- 首次缺料周由2026-08-24延后到2026-09-07；
- 最大缺口仍为8,800，说明提前动作改善时间窗口，但单一动作不足以覆盖整个周期；
- 不制造新缺料，因此可作为组合方案的一部分。

### 跨厂调拨

从来源工厂调入2,000：

- 首次缺料周延后到2026-09-21；
- 最大缺口从8,800降至6,800；
- 来源工厂重算后最大缺口为0；
- 动作可建议执行，但仍需物流/计划审批。

## 关键门禁

$$
SourceAvailable=OnHand-Protected-FutureDemand-MinimumCoverage
$$

调拨不能只解决目标工厂问题，还必须证明来源工厂不会因此缺料。

## 运行

```powershell
python examples/run_cases.py --case 2
python examples/run_phase2_cases.py --case 2
```

对应代码：[`action_validation.py`](../../src/services/action_validation.py)、[`transfer_optimization.py`](../../src/services/transfer_optimization.py)。

[返回案例库](README.md)
