# GitHub发布检查清单

## 1. 数据与隐私

- [ ] 所有CSV均为合成或已脱敏数据；
- [ ] 不包含真实客户、供应商、员工、价格协议或订单；
- [ ] 不包含ERP导出文件、邮件、会议记录或本地路径；
- [ ] `.env`、API Key、Token、证书和密码未被提交；
- [ ] 截图只展示Demo数据。

建议检查：

```powershell
rg -n -i "api[_-]?key|secret|token|password|bearer|BEGIN PRIVATE KEY" .
git status --short
git ls-files
```

## 2. 文档

- [ ] README首屏图片可以加载；
- [ ] Mermaid图在GitHub中可以渲染；
- [ ] 公式、案例、架构和数据字典链接有效；
- [ ] 运行命令从新环境可以复制执行；
- [ ] Demo结果明确标注为合成数据；
- [ ] 没有声称虚构的预测准确率、库存收益或降本比例。

## 3. 工程质量

```powershell
python -m compileall -q app.py src tests examples
python -m pytest -q
python -m src.evaluate
python examples/run_cases.py --case all
python examples/run_phase2_cases.py --case all
```

- [ ] 124项测试全部通过；
- [ ] 第一阶段5个案例通过；
- [ ] 第二阶段11个案例通过；
- [ ] 24个Streamlit页面可以加载；
- [ ] FastAPI `/health`和关键`/v3`接口返回200；
- [ ] GitHub Actions测试通过。

## 4. 开源准备

- [ ] 确认MIT License符合发布意图；
- [ ] 仓库名、简介、Topics和README标题一致；
- [ ] 替换README中的`<your-repository-url>`；
- [ ] 设置GitHub Topics：`supply-chain`、`demand-forecasting`、`inventory-optimization`、`agent`、`fastapi`、`streamlit`；
- [ ] 首个Release写明Demo边界和已知限制。

## 5. 已知限制必须保留

- 不连接或写回真实ERP；
- 不自动执行PO、调拨、替代、ECN或报废；
- 任务和审批主要为进程内Demo；
- 调拨固定成本采用Demo级处理；
- 采购优化未覆盖税费、币种、供应商产能和复杂价格协议；
- 所有阈值和成本在生产使用前必须重新校准。
