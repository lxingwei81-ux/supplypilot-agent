# SupplyPilot产品展示素材

`screenshots/`中的图片由当前仓库的Streamlit Demo生成，使用的均为合成数据。展示主线是“Supply Chain Control Tower + AI Copilot”，五大工作区为Overview、Demand Forecast、Inventory、Procurement和AI Copilot。

| 文件 | 页面 |
|---|---|
| `control-tower-overview.png` | Overview：控制塔KPI、趋势、风险热力、AI洞察和行动中心 |
| `demand-forecast-confidence.png` | Demand Forecast：Actual vs Forecast、情景上下限和模型指标 |
| `inventory-risk-heatmap.png` | Overview：物料×周风险状态及来源说明 |
| `sku-360-detail.png` | SKU 360°：预测、库存、PO、BOM、风险和建议动作 |
| `inventory-projection.png` | Inventory：周度库存、安全库存、缺料与到货时序 |
| `procurement-action-center.png` | Procurement：高影响动作、审批状态与前后结果 |
| `action-impact-validation.png` | Action Validation：动作前后缺口/冗余对比 |
| `ai-copilot-structured-response.png` | AI Copilot：证据、根因、建议和预期影响 |

以下文件用于兼容旧版README和历史发布：

| 文件 | 页面 |
|---|---|
| `management-dashboard.png` | 管理驾驶舱兼容名称 |
| `forecast.png` | 需求预测兼容名称 |
| `atp-allocation.png` | 共用料ATP与客户分配 |
| `transfer-optimization.png` | 多工厂调拨优化 |
| `procurement-optimization.png` | Procurement：PO取消/延期、批量与价格阶梯优化 |
| `scenario-optimization.png` | 多情景库存成本优化 |

README首屏使用`control-tower-overview.png`。更新UI后应先重新生成该图片，确认首屏可以直接看到MAT-B缺料主线，而不是原始JSON或开发调试信息。

重新生成：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/capture_screenshots.ps1
```

也可用Python脚本只生成指定素材或检查窄屏布局：

```powershell
python scripts/capture_screenshots.py --only inventory-risk-heatmap.png
python scripts/capture_screenshots.py --width 720 --output-dir temp/screenshots-mobile --only control-tower-overview.png
```

截图脚本使用Streamlit的`?page=`只读直达参数，不改变任何业务数据。旧页面名称仍由导航兼容层识别。

截图中的核心数值必须与确定性测试一致：

- MAT-B最大缺口8,800件；调拨1,800件后最大缺口7,000件，首次缺料由2026-08-24推迟至2026-09-21，来源工厂保留安全库存；
- MAT-A取消8,000件PO后，期末冗余由9,000件降至1,000件；
- Forecast上下限标注为规则化情景带，不称为统计置信区间；
- 动作卡片保留“需人工审批、不自动写回ERP”的状态。

截图应使用固定Demo输入，不依赖实时LLM响应或外部API，避免同一版本生成不一致的证据和数字。

`diagrams/`预留给需要导出为SVG/PNG的架构图；README与文档当前优先使用GitHub原生Mermaid，避免静态图与代码逻辑失去同步。
