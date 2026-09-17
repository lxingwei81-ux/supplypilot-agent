# 案例8：PO取消与延期成本优化

## 业务问题

识别出库存冗余后，不能按PO金额从大到小直接取消。每张单据存在取消期限、锁定量、可延期量、MPQ和供应商罚金，需要在不超过安全冗余量的前提下选择组合。

## 目标和约束

取消罚金：

$$
Penalty_i=CancelQty_i\times UnitPrice_i\times PenaltyRate_i
$$

净收益：

$$
NetBenefit=AvoidedHolding+AvoidedObsolescence-Penalty
$$

约束：

$$
\sum_i(CancelQty_i+DelayQty_i)\le DecisionExcess
$$

- 锁定量不可取消；
- 超过取消期限的单据不参与；
- 取消数量遵循MPQ；
- 取消或延期后仍要重新检查逐周缺料。

## 求解方式

系统使用确定性动态规划，以累计取消量为状态，比较各候选组合的净收益；取消后剩余冗余再匹配可延期数量。

## Demo结果

输入决策冗余9,000：

| 单据 | 取消 | 延期 |
|---|---:|---:|
| PO-OPT-001 | 4,000 | 1,000 |
| PO-OPT-002 | 2,000 | 2,000 |

汇总：

| 指标 | 结果 |
|---|---:|
| 动作后冗余 | 0 |
| 取消罚金 | 5,040 |
| Demo净收益 | 5,760 |
| 状态 | OPTIMAL |

净收益来自Demo成本参数，不能作为生产节省承诺。

## 运行

```powershell
python examples/run_phase2_cases.py --case 3
```

页面：`http://localhost:8501/?page=采购成本与批量优化`

对应代码：[`procurement_optimization.py`](../../src/services/procurement_optimization.py)。

[返回案例库](README.md)
