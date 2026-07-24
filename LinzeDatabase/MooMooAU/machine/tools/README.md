# 机器工具入口

这里只保存项目专用适配器和校验器。共享 Governance 必须按
`machine/contracts/governance_binding.json` 的 commit 与摘要从外部 checkout 消费；不得复制、分叉、重建或作为 submodule 引入。

当前 v1.0.4 控制包只读验收：

```bash
python3 machine/tools/validate_delivery_status.py
python3 machine/tools/validate_production_composition.py
python3 machine/tools/validate_workflow_matrix.py --governance-root <固定版本的外部检出目录>
python3 machine/tools/validate_evidence.py evidence/tasks
python3 machine/tools/build_governance_facts.py --check
python3 machine/tools/validate_governance.py --governance-root <固定版本的外部检出目录>
python3 machine/tools/validate_publication.py
python3 machine/tools/build_package_manifest.py --check
python3 machine/tools/validate_package.py
```

`validate_evidence.py evidence/tasks` 只证明每份 evidence 符合真实 stage schema、任务绑定与禁止项约束；
它不会把局部机制证据提升为正式任务完成、受保护 Oracle、最终 Acceptance 或生产就绪。
`machine/status/latest.json` 是唯一当前跨维度状态入口，任务图仅裁定正式任务完成度。

`validate_workflow_matrix.py` 在最终树上离线回放 S3–S6 Workflow 的显式累计入口，并用无参数模式作
历史 fail-closed 负向控制；它不执行或冒充远端 GitHub Actions、受保护 Oracle 或生产运行。

`validate_production_composition.py` 只验证 RMD-04 Workflow/源码绑定、离线 contract-only CLI 和本地
合成观察；它不读取 Secret、不调用真实 Gmail/私有仓，也不把本地组合证据提升为生产健康。

`build_* --write` 是显式生成动作；所有 `validate_*` 命令只读。测试也要求通过
`MOOMOOAU_GOVERNANCE_ROOT` 指向同一固定版本外部检出目录，缺失时按失败处理。
