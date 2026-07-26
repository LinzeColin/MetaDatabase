# CyberBoss

CyberBoss 是 `LinzeColin/MetaDatabase` 内的全云微信驱动 Codex MVP 子项目。

## 当前状态

- 生命周期：Stage 0 已完成，等待独立 `PG-0`
- 当前产品设计：`v0.0.0.4`
- 已完成 Run：`PS0.1`；`P0.1 / CB-000`；`P0.2 / CB-010`；
  `P0.3 / CB-020`；`P0.4 / CB-030`；`P0.5 / CB-040`
- 当前基线：三个精确 commit 的本地 source bundle、完整许可证/依赖清单及
  Codex CLI `0.146.0-alpha.3.1` 协议证据
- 最新 Run：`P0.5 / CB-040` 已通过；唯一非秘密 environment substitutions、
  25 个后续任务的实现/测试/证据/发布映射、确定性 10 项追溯审计、immutable
  release/rollback plan 与本地 baseline commit SHA 均已冻结
- Stage 0–5 任务状态：`CB-000`–`CB-040` 五项 Stage 0 任务已通过；其余 25 项与
  PG-0–PG-5 均为 `not_started`
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

CB-010 使用受保护本地部署记录解析同一授权 OVH 资产，严格 known-host、
key-only SSH 完成三次即时脱敏 preflight；选择 `constrained`，确认
8765/8780 和四个拟用路径无冲突，并在 128 MiB 有限容器中完成
16 MiB/8 MiB/100 有界 pressure，OOM-kill delta 为 0。地址、凭据、私钥、
原始进程/容器/Status 数据均未进入仓库。

P0.3 从受保护部署记录完成 Cloudflare/OCI 只读能力核验，没有输出真实值。
Access 专用 token 的跨服务读取被拒绝；现有 R2/D1 token 表现出跨
Access/R2/DNS 的读取能力且无法证明精确写 scope，因此所有真实 provider
mutation 保持 `activation_pending`/`hazard_blocked`。本地 adapters/mocks、
Access deny/allow、repo/data/bucket/prefix negative matrix 与 7 个受保护已知
秘密 equality scan 全部通过，P0/P1 findings=0。

P0.4 先原样运行 supplied simulator。WeChat baseline 收发成功；Codex
simulator 因无法从 implementation-kit 解析已锁定的 `ws` dependency 而实际
启动失败。最小扩展后，两份 simulator 覆盖 QR/login、cursor/replay、
duplicate/unknown outcome、401/403/429/500/503/timeout/reset，以及 Codex
initialize/thread/turn/progress/approval/error/overload/interrupt/crash/
false-success/late-event，4/4 contract tests 和 App 155/155 tests 均通过。
本机虽有锁定版本的 authenticated Codex，目标 OVH 仍无 CLI/auth/WeChat
state，真实 Codex/WeChat 与 AC-001/AC-010 均准确保持
`activation_pending`。安全复核同时修正既有 secret scanner 的字面
word-boundary 漏报，并用 7 类 hostile fixture 逐项验证；不阻塞下一 Run
`P0.5 / CB-040`。

P0.5 交叉核验 owner decisions、source lock、identity/credential policy、
OVH 实机边界和完整 TaskPack，消解旧 Feature Flag 别名后，将运行时名称唯一
对齐到 implementation-kit 已校验配置；没有改变功能默认值、Acceptance 或
Task DAG。`implementation-plan.json` 将 `CB-100`–`CB-540` 全部 25 个后续
任务映射到具体模块、测试、Acceptance、证据和 immutable release artifact。
确定性 SHA-256 抽取的 10 个 requirement 均能定位完整链，no-wait hits=0。
本地 baseline commit
`8a75b55e92071bb33f1cae5872feca55ade1c858` 未推送，远端 branch/PR/tag
核验均为空。真实 Codex、WeChat、Private-MetaDatabase 与 provider 写入继续
保持 `activation_pending`/`hazard_blocked`，下一 Run 只能执行 `PG-0`。

## 许可证

`CyberBoss/` 子树适用 [`LICENSE`](LICENSE) 中的 GNU AGPL-3.0-only。
历史上游仅作为固定来源快照和依法必须的归属证明；项目不保留上游 remote、
submodule、Git URL 运行时依赖、自动同步或定期 rebase 关系。

`whereabouts-mcp` 的 package 声明与许可证文件冲突按
`GPL-3.0-only AND AGPL-3.0-only` 的严格双重义务处理；原许可证、源码和冲突
记录完整保留，且不得声称已获得上游澄清。
