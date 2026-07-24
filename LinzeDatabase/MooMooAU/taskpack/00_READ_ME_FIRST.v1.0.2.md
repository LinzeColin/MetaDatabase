# MooMooAU Archive 开发任务包 v1.0.2

- Package ID：`MMAU-ARCHIVE-TP-2026-07-22-V1.0.2`
- 授权：Owner 选择方案 1，建立基线保真继任版本
- 目标代码位置：`LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU`
- 产品契约：按固定哈希原样继承 v1.0.1；34 RQ、34 AC、58-task DAG 与十条不变量不变
- 唯一当前状态：`machine/status/latest.json`
- 发布状态：`LOCAL_ONLY_NOT_PUBLISHED`

## 开发入口

1. 运行 `python3 machine/tools/validate_package.py`，确认 v1.0.2 快照与 v1.0.1 历史基线均无漂移；
2. 运行 `python3 machine/tools/validate_delivery_status.py`，读取唯一当前跨维度状态；
3. 运行 `python3 machine/tools/validate_evidence.py evidence/tasks`，验证 58 份真实 stage evidence；
4. 通过 pinned external Governance checkout 运行 `validate_governance.py`；
5. 每次 run 最多处理一个 Stage 或复审修复 task group，未通过对应 Gate 不进入下一组；
6. S0–S7、整体复审修复、受保护验收和最终干净快照全部完成后，才一次性上传 GitHub。

## 状态解释

- `evidence_integrity=PASS`：record 的 schema、路径、task、stage-local AC、final AC 与禁止项绑定有效；
- `LOCAL_MECHANISMS_EVIDENCED`：本地或合成机制有证据，不代表受保护 Oracle 已执行；
- `formal_task_completion`：只由冻结 task graph 与最终验收门裁定；
- `protected_oracles` 与 `final_acceptance`：只能由带受保护 provenance 的真实观察升级；
- `production_readiness`：正式任务、受保护 Oracle、最终验收与生产运行未全部通过时必须为 `BLOCKED`。

当前准确状态：evidence 58/58；本地机制证据 58/58；正式任务 7/58；受保护 Oracle 0/43；最终验收
0/34；生产运行 0；未发布。下一 run 只允许处理 RMD-03 累计 CI，不得顺带进入生产 composition、
assurance provenance、受保护验收或上传。

## 冻结边界

v1.0.1 `00_READ_ME_FIRST` 和 `ROADMAP` 中的全部安全边界继续有效，特别是：只处理确定性双重验证的
Moomoo AU 入站消息；只允许 exact message Trash；远端恢复成功前禁止 M3；恰好一个私有数据仓；
Raw 与敏感 Processed 持久化前 age 加密；Timeline 健康稳态恰好一个且任何时刻最多一个；真实邮件、
附件、密码、Token 与私钥永不进入模型上下文；本地电脑和自建服务器零生产持久化。
