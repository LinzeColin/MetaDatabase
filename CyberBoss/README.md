# CyberBoss

CyberBoss 是 `LinzeColin/MetaDatabase` 内的全云微信驱动 Codex MVP 子项目。

## 当前状态

- 生命周期：Stage 0 与独立退出门 `PG-0` 已通过；Stage 1 的
  `P1.1 / CB-100`、`P1.2 / CB-110`、`P1.3 / CB-120` 已通过
- 当前产品设计：`v0.0.0.4`
- 已完成 Run：`PS0.1`；`P0.1 / CB-000`；`P0.2 / CB-010`；
  `P0.3 / CB-020`；`P0.4 / CB-030`；`P0.5 / CB-040`；
  `P1.1 / CB-100`；`P1.2 / CB-110`；`P1.3 / CB-120`
- 当前基线：三个精确 commit 的本地 source bundle、完整许可证/依赖清单及
  Codex CLI `0.146.0-alpha.3.1` 协议证据
- 最新 Run：`P1.3 / CB-120` 已在同一目标安装 exact-commit candidate、
  唯一 `cyberboss` sparse workspace、root 控制的 registry、code/data
  身份隔离及 exact no-clone client；两次 apply 与 verify 通过，数据和
  Runtime 仍为 `activation_pending`，`current`/service/公网 route 未变
- Stage 0–5 任务状态：`CB-000`–`CB-120` 共八项任务已通过；其余 22 项与
  PG-1–PG-5 均为 `not_started`；`PG-0=passed`
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
保持 `activation_pending`/`hazard_blocked`；该 Run 当时的唯一下一节点为
`PG-0`。

PG-0 在不读取或依赖真实 credential 的隔离环境中执行 22 项准备检查；
4/4 simulator tests、155/155 App tests、DAG/traceability/no-wait/TaskPack、
preflight/resource、activation clean fixture 与 secret scan 全部通过。
unresolved architecture conflicts、credential values、external writes 均为
0。原源码、许可证、Corresponding Source、129 项依赖清单和严格
`GPL-3.0-only AND AGPL-3.0-only` 冲突记录保持不变，且
`upstream_clarification_received=false`。远端 CyberBoss branch/PR/tag
仍为空；该 gate 当时未启动 `P1.1 / CB-100`。

P1.1 以本地 implementation commit
`b2a603e415a2045b441f31e07cf74ac451ba6240` 作为目标主机 immutable
release ID。fresh preflight 再次证明 target hash、strict known-host、
key-only SSH、constrained/recover profile、四个路径和 8765/8780 无冲突。
两次 apply（第二次不重测资源、不覆盖 rollback prestate）通过；主
`cyberboss-cloud.service` 固定非 root、`KillMode=control-group`、
strict filesystem allowlist、资源上限和独立 journal cap。最终验收完成
100/100 systemd kill/restart、100/100 singleton denial、5 个权限拒绝与
2 个 allowlisted write，规范化 route topology 不变，unit 回到
disabled/inactive 且端口为 0。首次验收 harness 的原始 route JSON
复合哈希冲突及后续纠正记录完整保留。未安装真实 Runtime、Node/Codex，
未执行 provider/Private-MetaDatabase 写入，也未 push/PR/tag。

P1.2 以本地 implementation commit
`3cd8eee4f6b7c0a78f7b6fde90dae0f4ff1392fc` 固定 Node.js `24.18.0`、
Codex CLI `0.146.0-alpha.3.1` 与三个官方 archive SHA-256，只安装到
`/opt/cyberboss-cloud/shared/toolchains`，不修改全局 Node/Codex。两次
apply 与独立 verify 通过，`node:sqlite` self-test 通过，受保护
`CODEX_HOME` 为 `cyberboss:cyberboss:0700`。瞬时 App Server 仅监听
`127.0.0.1:8765`，`/readyz=200`、initialize/initialized 通过，外部端口
不可达；清理后 listener/process/staging 均为 0，主 unit 仍
disabled/inactive，`current` 仍指向 CB-100 release。

目标没有 `auth.json`，因此真实 Codex adapter 准确保持
`activation_pending`，device auth 命令只准备未执行。Claude Code
binary/credential 均未安装；默认 feature/eval 双门为 false，三个负向组合
全部拒绝，true/true 只进入无副作用 fixture，没有启动 adapter。首次 hold
marker 编排超时和第二次 0700 staging 导出失败均保留在 CB-110 evidence，
最终完整重跑通过。没有真实 WeChat/Runtime、provider/
Private-MetaDatabase 写入或 GitHub publication。

P1.3 以本地 implementation commit
`10d988e908d72ea1a43bbed04a2130a338663363` 生成完整 Corresponding
Source、`blob:none` partial seed、exact canonical no-clone client 与官方
GitHub CLI `2.96.0` artifact。目标机 check、两次 apply、独立 verify 和
App 166/166 tests 通过；第二次 apply 幂等。唯一 workspace
`/srv/cyberboss-workspaces/cyberboss` 固定 exact head、`.github` /
`CyberBoss` sparse paths、本地 immutable seed remote 和 root-controlled
alias/realpath gate。

目标 9/9 workspace 专项测试证明 `/bind cyberboss` 通过，绝对路径、未知
alias、symlink escape 与未登记 Runtime root 全部 fail-closed。code identity
不能读/执行 data client，data identity 不能写 code workspace；wrapper
只执行 plan-only，credential 文件缺失，Private-Database clone 和真实数据
操作为 0。Live workspace 约 29.1 MB、预算状态 `recover`；有界 target
cgroup pressure 零 OOM。验收过程中 root Python 产生的两个 cache entry 已
作为精确 transient artifact 删除并保留纠正记录。最终 candidate 只读，
process/listener 为 0，`current` 仍指向 CB-100，service 仍
disabled/inactive；没有 push/PR/tag/release。

P1.4 / CB-130 以本地 implementation commit
`81dc1ee211e554dd8b84001bfca4b8aa73bb89dd` 固定一个非 shell、
无 detached child 的 cloud supervisor，在既有
`KillMode=control-group` unit 下管理 loopback Runtime、channel fixture
与 bridge。目标机 check、两次 apply、独立 verify 和 App 170/170 tests
通过；第二次 apply 幂等，candidate 只读且完整保留 Corresponding Source、
原许可证与冲突记录。

`/healthz`、`/readyz` 与 token-protected bounded snapshot 分离验证；
forced-unready 为 healthy 200 / ready 503，不能假绿。8765/8780/19080
仅监听 loopback，操作者主机扫描确认 8765/8780 外部不可达。100/100
concurrent start、100/100 singleton denial、100/100 SIGKILL/restart 与
runtime/channel/bridge/service 4/4 fault recovery 全部通过，每次恢复均证明
旧 cgroup 成员已全部替换。Node 24 TAP 前缀与 systemd 255
`kill-whom=all` 两个真实 harness 缺陷及所有失败/清理结果完整保留。

最终 service 为 disabled/inactive，MainPID、process、listener、transient
drop-in、token、incoming 均为 0；`current` 仍指向 CB-100，workspace 仍在
CB-120。真实 Codex/WeChat 仍准确保持 `activation_pending`，没有
Private-MetaDatabase/provider 写入或 GitHub publication。下一任务
`P1.5 / CB-140` 仍为 `not_started`。

## 许可证

`CyberBoss/` 子树适用 [`LICENSE`](LICENSE) 中的 GNU AGPL-3.0-only。
历史上游仅作为固定来源快照和依法必须的归属证明；项目不保留上游 remote、
submodule、Git URL 运行时依赖、自动同步或定期 rebase 关系。

`whereabouts-mcp` 的 package 声明与许可证文件冲突按
`GPL-3.0-only AND AGPL-3.0-only` 的严格双重义务处理；原许可证、源码和冲突
记录完整保留，且不得声称已获得上游澄清。
