# SupplyPilot：供应链计划与采购协同智能体

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-24_pages-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Tests](https://img.shields.io/badge/tests-124_passed-brightgreen)](tests/)
[![Data](https://img.shields.io/badge/data-synthetic_demo-blue)](data/)
[![License](https://img.shields.io/badge/license-MIT-black)](LICENSE)

面向制造业供应链计划场景，将**需求预测、多级BOM、周度库存投影、缺料与冗余诊断、ATP分配、多工厂调拨、采购优化和审批跟踪**封装为可追溯的智能体工具链。

> 设计边界：LLM负责理解问题、场景路由辅助、原因解释和报告组织；所有预测、库存、BOM、数量、金额与优化结果均由确定性Python服务计算。

![SupplyPilot管理驾驶舱](assets/screenshots/management-dashboard.png)

## 30秒看懂项目

SupplyPilot按照供应链“三道防线”组织能力：第一道防线提高需求基线质量，第二道防线用库存吸收剩余不确定性，第三道防线只处理真正的执行例外。

```mermaid
flowchart LR
    A["第一道防线<br/>需求预测"] --> B["第二道防线<br/>库存计划"]
    B --> C["第三道防线<br/>供应链执行"]
    A --> A1["数据治理与需求分类"]
    A --> A2["多模型预测与滚动回测"]
    A --> A3["统计/人工/共识版本"]
    B --> B1["多级BOM需求拆解"]
    B --> B2["安全库存与补货策略"]
    B --> B3["逐周库存投影"]
    C --> C1["缺料与冗余诊断"]
    C --> C2["ATP/PO/调拨/ECN"]
    C --> C3["动作重算、审批与任务"]
```

系统完成的闭环：

```mermaid
flowchart LR
    DQ["数据质量门禁"] --> DC["需求分类"]
    DC --> FC["预测与回测"]
    FC --> FV["预测版本"]
    FV --> BOM["BOM拆解"]
    BOM --> IP["周度库存投影"]
    IP --> RK["缺料/冗余风险"]
    RK --> AC["采购/调拨/替代建议"]
    AC --> VA["动作前后重算"]
    VA --> AP["审批与任务闭环"]
```

## 项目能力

| 业务问题 | 确定性能力 | 关键输出 |
|---|---|---|
| 历史数据是否可信 | 必填、日期、数值、重复记录、BOM循环、版本断档检查 | 阻断项、警告、数据限制 |
| 应该使用哪类预测方法 | ABC/XYZ、ADI-CV²、生命周期分类 | 需求标签、候选模型、库存策略 |
| 未来需求是多少 | 11类模型、4/8/13/26周预测、滚动起点回测 | WAPE、Bias、MAE、模型得分、置信度 |
| 人工调整是否有效 | 统计/调整/共识版本和FVA | 审批记录、调整证据、FVA状态 |
| 成品需求如何转换为物料需求 | 任意层级BOM递归、版本有效期、损耗和单位换算 | 物料、周次、BOM路径、毛需求 |
| 哪一周会缺料 | 可用库存与逐周库存状态递推 | 首次缺料周、最大缺口、覆盖周数 |
| 哪些库存是真正冗余 | 预测需求、安全库存、保留需求和在途供给联合计算 | 冗余数量、金额、形成原因 |
| 共用料不足时如何分配 | 冻结订单、客户优先级、停线损失、紧迫度规则 | 请求量、分配量、未满足量、分配原因 |
| 能否从其他工厂调拨 | 来源保护量、通道兼容、到货时限、最小成本流 | 来源/目标、调拨量、到货日、成本、残余缺口 |
| 哪些PO可以取消或延期 | 取消窗口、锁定量、MPQ、罚金、持有和过时成本 | 单据级调整量、罚金、避免成本、剩余冗余 |
| 如何选择补货批量 | MOQ、MPQ、包装倍数、价格阶梯联合枚举 | 建议数量、适用单价、总成本、期末缺口/盈余 |
| 动作是否会制造新问题 | 内存应用动作并重跑周度投影 | 动作前后对比、拒绝原因、残余风险、审批要求 |

完整公式、变量、边界条件和代码位置见[《公式与规则手册》](docs/FORMULA_CATALOG.md)。

## 关键公式

### 周度库存投影

$$
EndingInventory_t = BeginningInventory_t + POReceipt_t + ProductionReceipt_t
+ TransferIn_t - GrossDemand_t - ReservedDemand_t - TransferOut_t
$$

逐周递推而不是只计算“库存＋PO－总需求”，因此能够识别总量充足但中间周缺料的时序风险。

### 冗余库存

$$
Excess_t = \max(0, EndingInventory_t - SafetyStock_t)
$$

业务上将其解释为：满足预测/保留需求并保留必要安全缓冲后，仍超出需求的库存。冗余金额为：

$$
ExcessValue_t = Excess_t \times UnitCost
$$

### 安全库存

$$
SS = z \times \sqrt{\overline{LT}\sigma_D^2 + \overline{D}^{2}\sigma_{LT}^2}
$$

安全库存吸收需求与交期的不确定性，不用于掩盖虚高预测或不稳定的执行流程。

### 多级BOM毛需求

$$
GrossRequirement_{m,t} = \sum_i Forecast_{i,t}\times CumulativeUsage_{i,m}
$$

其中累计用量逐层叠加单位用量、单位换算和损耗。

## 三个重点案例

### 1. 总量不缺，但中间周缺料

静态算法显示未来总供应比总需求多2,000，但PO到货时间过晚。逐周投影发现：

| 指标 | 结果 |
|---|---:|
| 静态总量盈余 | 2,000 |
| 首次缺料周 | 2026-08-31 |
| 最大缺口 | 2,000 |
| 提前4,000 PO后的最大缺口 | 0 |

![周度库存投影](assets/screenshots/inventory-projection.png)

结论：静态总量不能替代时间维度投影。运行案例：

```powershell
python examples/run_cases.py --case 3
```

[查看完整案例](docs/cases/03-middle-week-shortage.md)

### 2. 需求下降导致库存冗余

产品周需求从1,000下降到600，经BOM拆解和周度投影，识别MAT-A期末决策冗余9,000。模拟取消8,000在途PO后：

| 指标 | 动作前 | 动作后 |
|---|---:|---:|
| 期末冗余 | 9,000 | 1,000 |
| 新增缺料 | — | 否 |
| 建议执行 | — | 是，需审批 |

![采购成本与批量优化](assets/screenshots/procurement-optimization.png)

系统继续检查共用消耗、跨厂调拨和ECN消耗机会；PO取消、调拨和ECN均只生成建议，不自动写回业务系统。

```powershell
python examples/run_cases.py --case 1
python examples/run_phase2_cases.py --case 3
```

[查看完整案例](docs/cases/01-demand-decline-excess.md)

### 3. 共用料竞争与多工厂调拨

ATP先扣除保护量，再按冻结订单、客户优先级、缺货损失、需求紧迫度和生命周期进行可追溯分配。

![共用料ATP](assets/screenshots/atp-allocation.png)

调拨优化只使用不影响来源工厂未来需求和最低覆盖的库存，并排除不兼容或无法按时到达的通道。Demo中调拨前缺口8,500，优化后缺口为0，总调拨成本9,860。

![多工厂调拨](assets/screenshots/transfer-optimization.png)

```powershell
python examples/run_phase2_cases.py --case 1
python examples/run_phase2_cases.py --case 2
```

[查看ATP案例](docs/cases/06-shared-material-atp.md) · [查看调拨案例](docs/cases/07-cross-plant-transfer.md)

## 页面预览

| 需求预测 | 多情景库存优化 |
|---|---|
| ![需求预测](assets/screenshots/forecast.png) | ![多情景库存优化](assets/screenshots/scenario-optimization.png) |

Streamlit共24个页面，覆盖数据质量、需求分类、预测/回测、预测版本、BOM、库存投影、风险、采购动作、ATP、调拨、ECN、任务和管理驾驶舱。

## 智能体架构

```mermaid
flowchart TB
    U["用户业务问题"] --> AG["SupplyPilot Agent"]
    AG --> RT["规则优先场景路由"]
    AG --> LLM["LLM：意图、解释、报告"]
    AG --> TOOLS["21个Agent Tools"]
    TOOLS --> DQ["数据质量/分类"]
    TOOLS --> FC["预测/回测/版本"]
    TOOLS --> BI["BOM/库存/风险"]
    TOOLS --> OP["ATP/调拨/采购优化"]
    TOOLS --> WF["审批/任务/ECN"]
    DQ --> PY["确定性Python领域服务"]
    FC --> PY
    BI --> PY
    OP --> PY
    WF --> PY
    PY --> MD["Pydantic领域模型"]
    MD --> API["FastAPI"]
    MD --> UI["Streamlit"]
    MD --> JSON["可验证JSON/CSV"]
    DATA["CSV / Excel Demo"] --> PY
    RULES["rules.yaml"] --> PY
```

架构原则：

- 规则优先、LLM辅助，不让大模型编造业务数量；
- 预测、风险和动作保留数据版本、规则版本、证据和计算时间；
- 数据存在阻断问题时停止依赖该数据的计算；
- 高影响动作必须重新投影并保留人工审批；
- 相同输入产生相同结果，便于测试、审计和复现。

详细说明见[《智能体与技术架构》](docs/AGENT_ARCHITECTURE.md)。

## 快速运行

要求Python 3.11+。

```powershell
git clone https://github.com/lxingwei81-ux/supplypilot-agent.git
cd supplypilot_agent_v2
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

浏览器打开 `http://localhost:8501`。除“智能问答”外，确定性页面不需要OpenAI API Key。

如需启用Agent问答：

```powershell
Copy-Item .env.example .env
# 在本地.env中配置OPENAI_API_KEY，不要提交.env
```

### 运行API

```powershell
python -m uvicorn src.api:app --reload
```

接口文档：`http://127.0.0.1:8000/docs`

### 运行案例

```powershell
python examples/run_cases.py --case all
python examples/run_phase2_cases.py --case all
```

案例导航见[《业务案例库》](docs/cases/README.md)。

### 一键同步到GitHub

首次发布完成后，可使用仓库内脚本执行“测试 → 敏感文件检查 → 提交 → 拉取 → 推送”：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/sync_github.ps1 `
    -Message "docs: update cases and screenshots"
```

脚本只为当前进程继承Windows系统代理，不修改全局网络设置；测试失败、存在冲突或检测到敏感文件时会停止推送。

## 测试与复现

```powershell
python -m pytest -q
python -m src.evaluate
```

当前验收结果：

- `124 passed`；
- 原有20条冗余记录的公式/动作一致性回归为100%；
- 第一阶段5个案例与第二阶段11个案例均可独立运行；
- 24个Streamlit页面通过加载检查；
- 新旧工具及`/query`兼容接口保留。

这里的100%是规则一致性回归结果，不是生产预测准确率或库存收益。

## 工程结构

```text
supplypilot_agent_v2/
├─ app.py                         # 24个Streamlit页面
├─ config/rules.yaml              # 阈值、成本、权重、服务水平、审批矩阵
├─ data/                          # 脱敏合成Demo CSV
├─ assets/screenshots/            # GitHub展示截图
├─ docs/
│  ├─ FORMULA_CATALOG.md          # 公式、变量、边界和代码追溯
│  ├─ AGENT_ARCHITECTURE.md       # 智能体、工具与领域服务架构
│  ├─ BUSINESS_SCENARIO_SPEC.md   # 业务口径和安全边界
│  ├─ DATA_DICTIONARY.md          # 数据表与字段
│  └─ cases/                      # 可复制业务案例
├─ examples/                      # 第一/二阶段案例脚本
├─ scripts/capture_screenshots.ps1
├─ src/
│  ├─ agent.py                    # OpenAI Agents SDK编排
│  ├─ api.py                      # FastAPI结构化接口
│  ├─ models.py                   # Pydantic领域模型
│  ├─ router.py                   # 场景路由
│  ├─ tools.py                    # 兼容工具与V2/V3工具
│  └─ services/                   # 确定性领域服务
├─ tests/                         # 124项领域测试
└─ requirements.txt
```

## 文档导航

- [公式与规则手册](docs/FORMULA_CATALOG.md)
- [智能体与技术架构](docs/AGENT_ARCHITECTURE.md)
- [业务案例库](docs/cases/README.md)
- [业务场景规格](docs/BUSINESS_SCENARIO_SPEC.md)
- [数据字典](docs/DATA_DICTIONARY.md)
- [GitHub发布检查清单](docs/GITHUB_RELEASE_CHECKLIST.md)

## 数据与安全边界

- 仓库数据均为合成Demo，不代表任何真实企业、客户或供应商；
- 系统不连接真实ERP，不自动写回生产数据；
- 不自动执行PO取消、调拨、替代料、ECN或报废；
- 任务模块只生成结构化提醒，不发送真实邮件或企业消息；
- 原V2采购数据仍保留18组重复单号，用于演示数据质量阻断；
- 工作流和任务默认使用进程内存储，生产部署需接入数据库、权限、审计和并发控制；
- Demo成本、服务水平和阈值来自`config/rules.yaml`，真实使用前必须根据企业策略校准。

## License

[MIT](LICENSE)。知识框架用于解释项目设计，业务公式和参数应以企业实际数据、政策和审计要求为准。
