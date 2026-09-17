# 案例3：总量不缺但中间周缺料

## 业务问题

未来13周的总供应量高于总需求量，静态汇总看起来没有缺料，但主要PO在需求发生后才到货。

这是供应链计划中典型的供需时间错配：总量正确不等于每周齐套。

## 静态算法

$$
StaticSurplus=OnHand+\sum POReceipt-\sum Demand
$$

Demo结果：

$$
StaticSurplus=2{,}000
$$

按静态算法会得出“库存有盈余”的错误结论。

## 周度算法

$$
Ending_t=Beginning_t+POReceipt_t+ProductionReceipt_t+TransferIn_t
-GrossDemand_t-ReservedDemand_t-TransferOut_t
$$

每周期末成为下周期期初，因此PO晚到之前产生的负库存不会被未来到货掩盖。

## Demo结果

| 指标 | 结果 |
|---|---:|
| 静态总量盈余 | 2,000 |
| 首次缺料周 | 2026-08-31 |
| 最大缺口 | 2,000 |
| 原PO到货周 | 第8周 |
| 提前数量 | 4,000 |
| 动作后最大缺口 | 0 |

```mermaid
flowchart LR
    A["总供应 > 总需求"] --> B{"按周展开?"}
    B -- "否" --> C["误判：没有缺料"]
    B -- "是" --> D["第6周库存跌破0"]
    D --> E["定位晚到PO"]
    E --> F["提前/拆单模拟"]
    F --> G["重算后缺口为0"]
```

## 决策结论

建议将4,000 PO提前或拆分首批到货。该动作不增加采购总量，只调整到货时序，解决中间周缺口。

## 运行

```powershell
python examples/run_cases.py --case 3
```

页面：`http://localhost:8501/?page=周度库存投影`

对应代码：[`inventory_projection.py`](../../src/services/inventory_projection.py)、[`action_validation.py`](../../src/services/action_validation.py)。

[返回案例库](README.md)
