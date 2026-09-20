# SupplyPilot 交互式案例展示

本目录用于 GitHub 展示和项目面试讲解。

- `supplypilot-showcase.html` 是自包含交互式案例页，不依赖 CDN 或后端服务。
- `index.html` 会跳转到案例页，便于 GitHub Pages 使用站点根入口。
- `open-showcase.bat` 用于 Windows 本地单机双击打开网页。

在线演示：

```text
https://lxingwei81-ux.github.io/supplypilot-agent/
```

注意：在 GitHub 仓库文件列表中直接点击 `.html` 文件会看到源码，这是 GitHub 文件浏览器的默认行为；需要使用上面的 GitHub Pages 链接，或下载仓库后在本机打开。

本地预览：

Windows 用户也可以直接双击：

```text
docs/showcase/open-showcase.bat
```

或者启动本地静态服务：

```bash
python -m http.server 8080 --bind 127.0.0.1 --directory docs/showcase
```

然后打开：

```text
http://127.0.0.1:8080/supplypilot-showcase.html
```

展示页包含 6 个案例：

| 案例 | 展示能力 |
|---|---|
| 中间周缺料 | 周度库存投影、首次缺料周、PO提前动作校验 |
| 需求下降消冗 | 冗余计算、PO取消、动作前后重算和审批边界 |
| 共用料ATP | 冻结订单、客户优先级、缺货罚金和生命周期分配规则 |
| 多工厂调拨 | 来源厂保护、通道过滤、最小成本流和审批动作 |
| 采购批量优化 | MOQ、MPQ、包装倍数、价格阶梯和总成本枚举 |
| 预测调整FVA | 统计预测、人工调整、共识版本和FVA回看 |

所有数字均来自仓库 Demo 数据或案例脚本的合成结果，仅用于解释业务逻辑，不代表真实企业数据或生产收益。
