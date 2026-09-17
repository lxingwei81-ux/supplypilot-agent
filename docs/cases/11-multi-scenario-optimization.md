# 案例11：多情景库存成本优化

## 业务问题

单一需求预测无法覆盖需求上升、需求下降或PO延期。系统需要比较不同决策在多个情景下的库存成本，并拒绝任何会在某个情景中制造缺料的方案。

## 情景

| 情景 | 概率 | 需求倍率 | PO延期 |
|---|---:|---:|---:|
| LOW | 20% | 0.80 | 0周 |
| BASE | 50% | 1.00 | 0周 |
| HIGH_DELAY | 30% | 1.15 | 1周 |

概率之和必须等于1。

## 候选决策

- `NO_ACTION`；
- `ORDER_4000`，动作成本200；
- `TRANSFER_5000`，动作成本500。

## 目标函数

$$
Cost_{d,s}=Holding_{d,s}+Shortage_{d,s}+EndingExcess_{d,s}+ActionCost_d
$$

$$
ExpectedCost_d=\sum_sProbability_s\times Cost_{d,s}
$$

## 安全门禁

不是直接从所有方案中选择期望成本最低者，而是先筛选：

$$
MaximumShortage_{d,s}\le AllowedShortage,\quad \forall s
$$

只有所有情景都不缺料的方案才允许被推荐。

## Demo结果

| 决策 | 期望成本 | 所有情景安全 |
|---|---:|---|
| NO_ACTION | 464,083.5 | 否 |
| ORDER_4000 | 19,495.5 | 否 |
| TRANSFER_5000 | 15,989.5 | 是 |

最终推荐`TRANSFER_5000`。如果没有任何鲁棒可行方案，系统返回`INFEASIBLE`，不会推荐不安全动作。

## 运行

```powershell
python examples/run_phase2_cases.py --case 10
```

页面：`http://localhost:8501/?page=多情景库存成本优化`

对应代码：[`scenario_optimization.py`](../../src/services/scenario_optimization.py)。

[返回案例库](README.md)
