# CyberBoss

CyberBoss 是 `LinzeColin/MetaDatabase` 内的全云微信驱动 Codex MVP 子项目。

## 当前状态

- 生命周期：Stage 0（Prestage 0 已通过）
- 当前产品设计：`v0.0.0.4`
- 已完成 Run：`PS0.1`；`P0.1 / CB-000`
- 当前基线：三个精确 commit 的本地 source bundle、完整许可证/依赖清单及
  Codex CLI `0.146.0-alpha.3.1` 协议证据
- 下一 Run：`P0.2 / CB-010`，只读测量 OVH 与现有 Status 基线
- Stage 0–5 任务状态：`CB-000` 已通过；其余 29 项与 PG-0–PG-5
  均为 `not_started`
- GitHub 发布：全部 TaskPack 与 PG-0–PG-5 完成前禁止 push/PR

## 唯一身份

- 代码仓：`LinzeColin/MetaDatabase`
- 项目路径：`CyberBoss/`
- MVP workspace alias：`cyberboss`
- MVP 写入范围：`CyberBoss/**`，以及 Run Contract 明确列出的根级治理集成文件
- 长期数据：`LinzeColin/Private-Database` 的 `Private-MetaDatabase` 区，
  `domain=CyberBoss`，通过 `private_db_client.py` 免 clone 存取

## 权威入口

1. [`AGENTS.md`](AGENTS.md)
2. [`HANDOFF.md`](HANDOFF.md)
3. [`machine/facts/owner_decisions.json`](machine/facts/owner_decisions.json)
4. [`machine/facts/task_state.json`](machine/facts/task_state.json)
5. [`docs/product_design/v0.0.0.4/00_README_FIRST.md`](docs/product_design/v0.0.0.4/00_README_FIRST.md)
6. [`docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml`](docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml)

每个 Run 最多执行一个 TaskPack `phase`。Run 结束必须运行对应 Acceptance，
更新 `task_state.json` 与 `HANDOFF.md`；不得用意图、文档声明或窄测试代替真实证据。

## 许可证

`CyberBoss/` 子树适用 [`LICENSE`](LICENSE) 中的 GNU AGPL-3.0-only。
历史上游仅作为固定来源快照和依法必须的归属证明；项目不保留上游 remote、
submodule、Git URL 运行时依赖、自动同步或定期 rebase 关系。

`whereabouts-mcp` 的 package 声明与许可证文件冲突按
`GPL-3.0-only AND AGPL-3.0-only` 的严格双重义务处理；原许可证、源码和冲突
记录完整保留，且不得声称已获得上游澄清。
