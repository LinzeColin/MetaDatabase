# CyberBoss Agent Contract

继承母仓库根目录 `AGENTS.md`，冲突时 Fail Closed。

## 唯一身份

- 母仓库：`LinzeColin/MetaDatabase`
- 子项目：`CyberBoss/`
- 项目代号：`CyberBoss`
- 当前产品设计：`v0.0.0.4`
- 治理框架：只消费 `LinzeColin/Governance`，不得复制、分叉或通过
  submodule 引入。

禁止为 CyberBoss 创建、恢复或引用任何独立代码仓；本项目只能作为
`LinzeColin/MetaDatabase` 的 `CyberBoss/` 子树存在。

## 许可证与来源边界

- `CyberBoss/` 整个子树使用 GNU AGPL-3.0-only；根仓专有许可证不得覆盖本子树。
- 依法保留固定上游 SHA、版权、许可证、修改说明与 Corresponding Source
  获取入口。
- 上游只在 Stage 0 作为一次性固定输入核验和导入源。导入后不得保留 upstream
  remote、submodule、Git URL package dependency、自动同步、运行时下载或定期
  rebase。
- `timeline-for-agent`、`whereabouts-mcp` 等必要源码必须按锁定 SHA 纳入可恢复
  source bundle，或以独立许可证审计证明的本地包消费；禁止跟随 `main`。
- 任何未来上游更新都需要新的 Owner Change Event，不得隐式拉取。

## B1 工作范围

- 默认 workspace alias 为 `cyberboss`。
- 仓库身份固定为 `LinzeColin/MetaDatabase`。
- 普通实现写入仅限 `CyberBoss/**`。
- 根级 `README.md`、`LICENSE`、`.github/workflows/dual-plane.yml` 等集成文件
  只有在当前 Run Contract 明确列出时才可修改。
- 不修改、恢复、stash、暂存或提交其他子项目及主工作树的改动。
- mutation 使用 `codex/cyberboss-*` 分支和有界 worktree；禁止直接写 `main`。

## 数据边界

- 本代码仓只保存代码、治理、合成 fixture 和脱敏紧凑证据。
- 长期/业务/运行时快照写入 `Private-MetaDatabase`，`domain=CyberBoss`。
- 使用 `KMOS/KMDatabase/machine/tools/private_db_client.py` 的免 clone 协议；
  禁止 clone `Private-Database`。
- OVH SQLite WAL 是仓外运行 spool，不是唯一长期事实源；可恢复压缩快照和
  脱敏事件批次通过客户端进入私有库。
- secret、Codex auth、微信 bearer、原始私聊、真实 PII 不得进入本代码仓、
  普通日志、TaskPack 或公开证据。

## Run 纪律

- 权威执行图：
  `docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml`。
- Prestage Run 使用 `PS*`；TaskPack Stage 0–5 使用其原有 `P0.1`–`P5.5`。
- 每个 Run 最多执行一个 `phase`，不得顺带完成下一个 phase。
- 每个 phase 开始前必须写 compact Run Contract；结束时必须运行该 phase
  Acceptance、全局 TaskPack validator、作用域检查，并更新 `HANDOFF.md` 和
  `machine/facts/task_state.json`。
- 前置依赖未 `passed` 时不得开始下游 phase。
- 外部凭据缺失只能使对应 adapter 为 `activation_pending`，不得伪称 verified。
- 任一 P0 安全、数据、许可证、恢复或验收项为 UNKNOWN/NOT_RUN 时不得过 Gate。
- 不使用真实时间 Soak、固定等待或观察期替代确定性测试。

## 发布纪律

- Stage 0–5 全部完成、PG-0–PG-5 全部有充分证据前，只允许本地 commit；
  禁止 push、PR、tag 或 GitHub 发布。
- 最终完成审计通过后才执行一次性 push、PR、CI、merge。
- 收尾必须完成：代码合并、PR 关闭、远程分支删除、worktree 删除、本地分支
  安全删除、`git worktree prune`、普通 `git gc`；禁止 `git gc --prune=now`。
