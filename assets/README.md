# 展示素材

`screenshots/`中的图片由当前仓库的Streamlit Demo生成，使用的均为合成数据。

| 文件 | 页面 |
|---|---|
| `management-dashboard.png` | 管理驾驶舱 |
| `forecast.png` | 需求预测 |
| `inventory-projection.png` | 周度库存投影 |
| `atp-allocation.png` | 共用料ATP与客户分配 |
| `transfer-optimization.png` | 多工厂调拨优化 |
| `procurement-optimization.png` | 采购成本与批量优化 |
| `scenario-optimization.png` | 多情景库存成本优化 |

重新生成：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/capture_screenshots.ps1
```

截图脚本使用Streamlit的`?page=`只读直达参数，不改变任何业务数据。

`diagrams/`预留给需要导出为SVG/PNG的架构图；README与文档当前优先使用GitHub原生Mermaid，避免静态图与代码逻辑失去同步。

