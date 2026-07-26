# Run Contract — P1.5 / CB-140 All-cloud Walking Skeleton

## 1. Goal

本 Run 只执行 Task DAG 节点 `P1.5 / CB-140`：

> Prove all-cloud Walking Skeleton with deterministic simulators and optional
> real adapters.

在 CB-130 已通过的同一授权 OVH 主机上，以 exact implementation commit
candidate 瞬态启动 channel simulator、CyberBoss bridge 与 loopback Runtime
simulator，完成十条确定性只读消息的端到端闭环，并为每条消息生成同一
`trace_id` 下的 inbound、Runtime turn、delivery outbox、channel confirmation
和 canonical acceptance event。另验证 allowlist、32 KiB 边界、20 条 idle
latency 基线与 Mac 零依赖。

本 Run 不执行 `PG-1`，不进入 Stage 2 durable spool，不切换 `current`，不
enable 业务 service，不读取或激活真实 credential，不发布 GitHub。

## 2. Frozen input and minimum scope

- 输入基线：
  `20405812e4ebfc51d59093b5916dd624317309a7`；
- 直接依赖：
  `CB-130=passed`；
- 唯一权威：
  `04_TASK_DAG_EXECUTION_PACK.yaml` 的 `CB-140` 与
  `02_PRD_ACCEPTANCE_CONTRACT.md` 的
  `AC-001`、`AC-002`、`AC-006`、`AC-010`、`AC-061`；
- 不创建新 repo；canonical code identity 仍为
  `LinzeColin/MetaDatabase/CyberBoss`；
- 完整 Corresponding Source、原许可证、provenance、修改记录和未解决冲突
  随 exact commit artifact 保留；合规表达固定为
  `AGPL-3.0-only AND GPL-3.0-only`，
  `upstream_clarification_received=false`；
- candidate 固定为
  `/opt/cyberboss-cloud/releases/<implementation-commit>`；
  `current` 必须始终解析到
  `b2a603e415a2045b441f31e07cf74ac451ba6240`；
- workspace 必须始终保持
  `10d988e908d72ea1a43bbed04a2130a338663363` 且 clean；
- CB-130 process-family、安全监听、status 与 simulator contract 全部复用，
  只通过 `/run/systemd` transient drop-in 指向 CB-140 candidate；
- acceptance trace 只保存 hash、byte count、单调阶段、redacted Runtime
  identity hash 和 latency，不保存 sender、account、token、消息正文、结果
  正文、workspace path、target address 或 credential；
- acceptance trace 是 CB-140 验收证据，不得声称已经实现 CB-200 的 SQLite
  inbox/outbox/job state machine；
- 真实 WeChat 与真实 Codex 均为可选 adapter。缺少激活时必须明确记录
  `activation_pending`，不得把 simulator 截图或结果称为真实激活；
- 目标地址只从受保护本地部署记录解析并匹配
  `target_id_sha256=7865f743d174`；只用 strict-known-host、key-only
  BatchMode，地址不得落库或输出。

## 3. Required implementation and oracles

- inbound policy 在任何 Runtime call 前执行：
  - 非空 allowlist 只接受精确 sender；
  - UTF-8 正文最大 `32768` bytes；
  - unauthorized 和 `32769` bytes 输入的 Runtime call delta 均为 `0`；
  - `32768` bytes 输入可进入 Runtime；
- acceptance tracing 仅在显式 file path 开启时工作，并以 append-only NDJSON
  记录：
  `inbound_received → runtime_dispatched → runtime_completed →
  outbox_staged → delivery_confirmed → canonical_event`；
- `trace_id` 必须由 provider/account/sender/message identity 的 SHA-256
  派生，证据中只保存派生值；每个阶段保存 text/result hash，不保存正文；
- simulator E2E：
  十条顺序只读输入均收到
  `SIMULATED_CODEX_RESULT` 预期回复，十条 trace 均完整、无跨 trace 混淆；
- latency：
  二十条 idle simulator 消息均完成，并以 inbound 到 delivery confirmation
  计算 `P50 < 5s`、`P95 < 10s`；
- Mac-offline：
  exact release source、systemd/config、process args、listeners 和 trace 中
  的 Mac IP、Mac path、Mac connector/process 命中总数为 `0`；
- Runtime 与 channel 继续只监听 loopback；8765 非 loopback listener
  count=`0`，operator-host external scan 不可达；
- required screenshot 必须清楚标为 simulator fixture；真实 QR/send/receive
  screenshot 在未激活时记录为 `activation_pending`，不得伪造；
- `AC-001-real`、`AC-010-real` 允许为 `activation_pending`；
  `AC-002`、`AC-006`、`AC-061` 和 CB-140 dependency-independent simulator
  criteria 必须有 executable evidence。

## 4. Allowed repository modifications

- `CyberBoss/app/package.json`
- `CyberBoss/app/src/core/app.js`
- `CyberBoss/app/src/core/config.js`
- `CyberBoss/app/src/core/inbound-turn.js`
- `CyberBoss/app/src/core/stream-delivery.js`
- `CyberBoss/app/src/core/walking-skeleton-trace.js`
- `CyberBoss/app/src/adapters/channel/weixin/index.js`
- `CyberBoss/app/src/adapters/channel/weixin/message-utils.js`
- `CyberBoss/app/test/cloud-walking-skeleton.test.js`
- `CyberBoss/app/test/cloud-walking-skeleton-live.test.js`
- `CyberBoss/docs/governance/RUN_CONTRACT_P1_5_CB_140.md`
- `CyberBoss/docs/product_design/v0.0.0.4/{MANIFEST.sha256,implementation-kit/**}`
  中 CB-140 直接相关 config、scripts、simulator、tests、README、report 与
  manifests；
- `CyberBoss/machine/facts/post-baseline-change-ledger.json`
- `CyberBoss/scripts/validate_cb140.py`
- `CyberBoss/tests/cloud-walking-skeleton.test.js`
- `CyberBoss/docs/evidence/CB-140/**`
- closure 时的
  `CyberBoss/machine/facts/task_state.json`、`CyberBoss/README.md`、
  `CyberBoss/HANDOFF.md`、`CyberBoss/CHANGELOG.md`。

其他路径不得修改，尤其是 `CyberBoss/vendor/**`、CB-000–CB-130/PG-0
历史 evidence、Task DAG、PRD、Roadmap、Acceptance、母仓其他项目。

## 5. Local validation

```bash
bash -n \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-walking-skeleton.sh \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-cloud-walking-skeleton.sh
python3 -m py_compile \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-walking-skeleton-artifacts.py
node --test CyberBoss/app/test/cloud-walking-skeleton.test.js
node --test CyberBoss/tests/cloud-walking-skeleton.test.js
cd CyberBoss/app && npm run check && npm test
python3 CyberBoss/scripts/validate_cb140.py --prepare
```

实现 commit 后，builder 只能从 clean exact worktree 产生 complete source
archive、artifact manifest 与 checksums，且证明 `remote_publication=none`。

## 6. Authorized target sequence

1. fresh read-only preflight 重验 target hash、key-only sudo、CB-130 candidate、
   service disabled/inactive、current/workspace、process/listener、incoming 和
   disk reserve；
2. installer `--check` 证明 persistent write/live command 均为 false；
3. 只将 exact three-file artifact set 放入
   `/var/lib/cyberboss/incoming/cb140-<commit>`；
4. 两次 `--apply` 与一次 `--verify` 绑定同一 commit；第二次必须幂等，均不
   启动 service、不移动 `current` 或 workspace；
5. 生成仅位于 `/run/cyberboss-cb140/` 的 transient drop-in，并使用 CB-140
   专用 synthetic trace/output state 瞬态启动 candidate；
6. 依次执行 10 条 E2E、allowlist、32 KiB/32 KiB+1、20 条 latency、trace
   correlation、Mac dependency 与 loopback/external scan；
7. 导出 redacted evidence 与 simulator fixture screenshot；
8. 无论成功失败都 stop/kill cgroup，删除 transient drop-in、token、trace
   working copy 和 incoming/transfer artifacts，daemon-reload；
9. 最终确认 service disabled/inactive、current/workspace 不变、process 与
   8765/8780/19080 listener 为 `0`；真实 credential/provider/data operation
   为 `0`。

## 7. Risks, rollback and stop conditions

- **False trace / cross-run mix：** 每条 trace 必须具有唯一 message identity、
  唯一 Runtime turn hash、唯一 delivery hash和单调阶段；缺阶段或跨 trace
  复用立即失败。
- **Policy after Runtime：** unauthorized 或 oversized 输入只要观察到
  Runtime call delta 非零即失败并停止。
- **Stage 2 scope creep：** acceptance NDJSON 不得用于业务 job recovery、
  retry 或 canonical Private-MetaDatabase sync；这些仍属于 CB-200+。
- **Indirect Mac dependency：** source/config/process/network 任一命中 Mac
  path、IP 或 connector 即停止。
- **Adapter-only defect：** 若真实账号不可用，真实项保持
  `activation_pending`，核心 simulator 继续；不得等待或伪造真实证据。
- **Rollback：** `systemctl stop` + control-group kill，删除 exact transient
  drop-in/token/working trace，恢复 daemon state；`current`、workspace 和
  历史 candidate 从不参与切换或删除。
- **硬停止：** non-loopback Runtime、无法阻止 Runtime 越权调用、trace 包含
  私密正文/identity、孤儿进程无法清理，或目标无法恢复到
  disabled/inactive 且零 listener/process。

## 8. Completion rule

只有十条 simulator E2E、20 条 latency、policy boundary、trace correlation、
Mac-offline、loopback/external scan、exact-commit install/verify 与 final
cleanup 全部通过，才能把 `CB-140` 标为 `passed`。真实
`AC-001`、`AC-010` 保持 `activation_pending`，不得声称真实验证。

`PG-1` 与所有后续任务保持 `not_started`；本 Run 不 push，不创建
PR/tag/release。
