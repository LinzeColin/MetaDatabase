# MooMooAU Archive 开发任务包 v1.0.3

- Package ID：`MMAU-ARCHIVE-TP-2026-07-22-V1.0.3`
- 授权依据：v1.0.2 已冻结的 RMD-03 后续顺序与 Owner 的逐 run 推进目标
- 目标代码位置：`LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU`
- 产品契约：按固定哈希原样继承 v1.0.1；34 RQ、34 AC、58-task DAG 与十条不变量不变
- 控制前序：v1.0.2 Manifest 字节不可变
- 唯一当前状态：`machine/status/latest.json`
- 发布状态：`LOCAL_ONLY_NOT_PUBLISHED`

## 开发入口

1. 运行 `python3 machine/tools/validate_package.py`，确认 v1.0.3、v1.0.2 前序与 v1.0.1 历史基线无漂移；
2. 运行 `python3 machine/tools/validate_delivery_status.py`，读取唯一当前跨维度状态；
3. 运行 `python3 machine/tools/validate_workflow_matrix.py --governance-root <固定外部检出>`，离线回放
   S3–S6 最终树入口及历史默认负向控制；
4. 运行 `python3 machine/tools/validate_evidence.py evidence/tasks`，验证 58 份真实 stage evidence；
5. 通过 pinned external Governance checkout 运行 `validate_governance.py`；
6. 每次 run 最多处理一个 Stage 或复审修复 task group；全部完成并最终复审通过后才一次上传 GitHub。

## RMD-03 边界

- S3–S6 workflows 使用显式 `--cumulative-final`，最终树离线入口为 4/4 PASS；
- 同一批 CLI 无参数运行仍为 4/4 `BLOCKED`，且各自只失败一个 later-stage scope check；
- command matrix 只证明当前最终树上的只读本地入口，不声称远端 GitHub Actions 已运行；
- 真实 Gmail、私有仓、Secret、受保护 Oracle、生产 Workflow 和远端发布均为 0/NOT_RUN。

当前准确状态：evidence 58/58；本地机制证据 58/58；正式任务 7/58；受保护 Oracle 0/43；最终验收
0/34；生产运行 0；未发布。下一 run 只允许处理 RMD-04 生产 composition，不得顺带进入 assurance
provenance、受保护验收、生产执行或上传。

## 冻结边界

v1.0.1 `00_READ_ME_FIRST` 和 `ROADMAP` 的全部边界继续有效：只处理确定性双重验证的 Moomoo AU
入站消息；只允许 exact message Trash；远端恢复成功前禁止 M3；恰好一个私有数据仓；Raw 与敏感
Processed 持久化前 age 加密；Timeline 健康稳态恰好一个且任何时刻最多一个；真实邮件、附件、密码、
Token 与私钥永不进入模型上下文；本地电脑和自建服务器零生产持久化。
