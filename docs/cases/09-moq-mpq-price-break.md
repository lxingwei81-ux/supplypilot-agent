# 案例9：MOQ、MPQ、包装倍数与价格阶梯

## 业务问题

净需求并不等于最终采购数量。供应商可能要求最低订货量、固定增量和整包装，同时较大采购量可能获得更低单价。

## 可行数量

$$
Q=0\quad or\quad Q\ge MOQ
$$

$$
Q=k\times LCM(MPQ,PackageMultiple)
$$

## 成本函数

$$
TotalCost(Q)=PurchaseCost(Q)+HoldingCost(Q)+ShortageCost(Q)+FixedOrderCost(Q)
$$

其中价格由适用于$Q$的最高价格阶梯确定。

## Demo输入

- 物料：`MAT-B`；
- 净需求：4,700；
- MOQ：500；
- MPQ：100；
- 包装倍数：50；
- 价格阶梯：0/2,000/5,000/10,000。

## Demo结果

| 指标 | 结果 |
|---|---:|
| 推荐订货量 | 4,700 |
| 适用单价 | 44.5 |
| 采购总成本 | 209,250 |
| 期末盈余 | 0 |
| 期末短缺 | 0 |
| 状态 | OPTIMAL |

价格阶梯不意味着应该为了低价大量超买；持有成本、过时成本和短缺成本必须共同进入目标函数。

## 运行

```powershell
python examples/run_phase2_cases.py --case 4
```

对应代码：[`procurement_optimization.py`](../../src/services/procurement_optimization.py)。

[返回案例库](README.md)
