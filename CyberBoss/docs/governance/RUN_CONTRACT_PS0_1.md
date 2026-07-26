# Run Contract — PS0.1

## 1. Goal

把 Owner 提供的 CyberBoss v0.0.0.3 TaskPack 归一化为可在
`LinzeColin/MetaDatabase/CyberBoss` 严格执行的 v0.0.0.4 基线。

## 2. Minimum scope

- 建立独立本地 worktree 与 `codex/cyberboss` 分支；
- 固化 A1、上游分离、B1、Private-MetaDatabase 和最终一次性发布决策；
- 导入完整 TaskPack，保持 6 Stage、30 Task、53 Acceptance Oracle 的产品范围；
- 修复仓库身份、数据协议、workspace、许可证和无效追踪引用；
- 增加能发现上述漂移的 Prestage validator；
- 建立机器任务状态与跨 Run HANDOFF。

## 3. Non-goals

- 不执行 `P0.1 / CB-000`；
- 不导入上游应用源码；
- 不安装依赖、不修改 OVH/Cloudflare/Private-Database；
- 不部署、不 push、不建 PR、不创建 tag；
- 不把任何 Task 或 Pass Gate 标记为完成。

## 4. Inspected inputs

- Owner TaskPack ZIP 与独立 Roadmap；
- MetaDatabase 根 `AGENTS.md`、`README.md`、`LICENSE`、
  `WHERE_IS_PROJECT_DATA.md`、`dual-plane.yml`；
- `LinzeColin/Governance` 双平面标准；
- `KMOS/KMDatabase/machine/tools/private_db_client.py`；
- 固定上游 package/lock/license 和 cursor 行为证据。

## 5. Allowed modifications

- `CyberBoss/**`
- 根 `README.md`
- 根 `LICENSE`
- 根 `WHERE_IS_PROJECT_DATA.md`

本 Run 不允许修改其他根级文件或任何既有项目。

## 6. Validation

```bash
python3 CyberBoss/scripts/validate_prestage0.py
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_taskpack.py
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_task_dag.py \
  CyberBoss/docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_traceability.py
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_no_wait.py
node CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_config.js \
  --allow-placeholders \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/workspaces.json.example
git diff --check
git status --short
```

## 7. Risks and rollback

- 机械归一化可能改变产品语义：用 DAG cardinality、Acceptance ID 集合和
  traceability validator 比对。
- 嵌套 AGPL 与根专有许可可能漂移：根/子 LICENSE 和 owner decision 双向检查。
- 回滚只需删除本地分支/worktree；不得触碰主树的现有 EEI 改动。

## 8. Stop conditions

- 需要改变 Stage 1 + Stage 2A 产品范围；
- 需要删除或新增 Task/Acceptance；
- 需要猜测上游许可证或来源；
- 需要创建独立代码仓或 clone Private-Database；
- 修改范围将触及既有项目。

## 9. Acceptance

PS0.1 仅在以下全部为真时通过：

1. v0.0.0.4 TaskPack 的 30 Task、6 Stage、53 Oracle 完整；
2. 所有 Task/Pass-Gate 引用存在；
3. 禁止的独立仓、旧数据根、Private-Database clone、旧 workspace 为零；
4. A1、上游分离、B1、单 Phase Run、最终一次性发布均为机器可读事实；
5. Git diff 只包含本合同允许范围；
6. 全部命令退出码为 0；
7. Stage 0 所有任务仍为 `not_started`。
