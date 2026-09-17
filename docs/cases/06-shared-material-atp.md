# 案例6：共用料ATP与客户优先级

## 业务问题

多个客户和成品争抢同一共用物料。平均分配可能损害冻结订单、战略客户或高缺货损失订单，因此需要一套可解释且不超分配的规则。

## 可分配供给

$$
AllocatableSupply=\max(0,AvailableSupply-ProtectedSupply)
$$

保护量用于覆盖已经冻结、不可挪用或必须保留的供给。

## 优先级

$$
Score_i=FrozenBonus_i+CustomerPriority_i\times w_c
+ShortagePenalty_i\times w_s+\frac{w_u}{1+UrgencyWeeks_i}+LifecycleWeight_i
$$

规则原因会与结果一起输出，例如`FROZEN_ORDER`、`CUSTOMER_PRIORITY_5`和`DUE_DATE_URGENCY`。

## 分配流程

```mermaid
flowchart LR
    A["可用供给"] --> B["扣除保护量"]
    B --> C["可选公平份额"]
    C --> D["计算需求优先级"]
    D --> E["按分数和需求日排序"]
    E --> F["逐笔分配剩余供给"]
    F --> G["输出未满足量和原因"]
```

## Demo结果

脚本使用总供给13,000、保护量1,000，需求合计10,500。可分配量12,000，因此全部需求均被满足。

Streamlit页面默认使用更紧张的供给参数，可以直接观察冻结订单和高优先级需求如何优先获得物料，以及其他需求的未满足量。

系统保证：

$$
\sum_i Allocation_i\le AllocatableSupply
$$

## 运行

```powershell
python examples/run_phase2_cases.py --case 1
```

页面：`http://localhost:8501/?page=共用料ATP与客户分配`

对应代码：[`allocation.py`](../../src/services/allocation.py)。

[返回案例库](README.md)
