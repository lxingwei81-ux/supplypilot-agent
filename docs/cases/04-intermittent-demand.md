# 案例4：间歇性需求预测

## 业务问题

售后或长尾物料存在大量零需求周期。普通移动平均会把偶发需求平滑成每期持续需求，容易形成冗余库存。

## 分类逻辑

$$
ADI=\frac{TotalPeriods}{NonZeroPeriods}
$$

$$
CV^2=\left(\frac{Std(NonZeroDemand)}{Mean(NonZeroDemand)}\right)^2
$$

系统结合ADI与CV²，将需求分为Smooth、Erratic、Intermittent和Lumpy。Demo物料`INTERMITTENT_M`被识别为`INTERMITTENT`。

## 模型选择

间歇性需求只比较：

- Croston：分别估计非零需求量和需求间隔；
- SBA：对Croston偏差进行修正；
- TSB：分别平滑需求发生概率和非零需求量。

滚动回测只使用预测起点之前的数据，并比较WAPE、Bias、MAE、缺货损失和冗余损失。

## Demo结果

| 指标 | 结果 |
|---|---|
| 需求分类 | INTERMITTENT |
| 选中模型 | CROSTON |
| 预测置信度 | LOW |
| 未来4周合计 | 169.64 |
| 未来13周合计 | 551.34 |
| 未来26周合计 | 1,102.67 |

低置信度不会被LLM改写成高置信度；库存策略应采用分层服务水平、小批量承诺和人工复核。

## 运行

```powershell
python examples/run_cases.py --case 4
```

对应代码：[`demand_classification.py`](../../src/services/demand_classification.py)、[`forecasting.py`](../../src/services/forecasting.py)、[`backtesting.py`](../../src/services/backtesting.py)。

[返回案例库](README.md)
