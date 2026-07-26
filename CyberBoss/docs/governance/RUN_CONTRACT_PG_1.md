# Run Contract — PG-1 Stage 1 Exit Gate

## 1. Goal

独立判定 Stage 1 exit gate `PG-1`：

> All-cloud Walking Skeleton passes with channel/runtime simulators and
> loopback transport; real adapters are additionally verified when activated.

只有 Stage 1 五项 Task 的冻结证据、当前可执行回归、无凭据 Walking
Skeleton 和 loopback/Mac-offline 边界全部成立时，才把 `PG-1` 标为
`passed`。本 Run 不得顺带开始 `P2.1 / CB-200`。

## 2. Frozen input and minimum scope

- 以精确 P1.5 closure commit
  `4020f07bc086ab9827ab97ddf295927075189a9f` 为不可变输入；
- 验证 `CB-100`–`CB-140` 五项 Stage 1 Task 及 Stage 0 五项 Task 均为
  `passed`，`CB-200`–`CB-540` 均为 `not_started`；
- 验证 simulator WeChat → bridge boundary → simulator Codex → outbox →
  simulator WeChat 的 10/10 完整链路；
- 验证 unauthorized sender 与 32769-byte 输入在 Runtime 前拒绝，
  32768-byte 边界通过；
- 验证关联 trace 不含消息、结果、身份或 credential 原文；
- 验证 Runtime/status/channel fixture 只监听 loopback，Mac 路径、进程、
  connector 与 non-loopback Runtime dependency 均为 0；
- 验证真实 Codex/WeChat 未激活时准确保留为 `activation_pending`；
- 复核 CB-100–CB-140 evidence tree、closure/implementation commit、
  Acceptance 映射、许可证冲突和目标机只读终态；
- 在 scrubbed credential environment、临时 HOME、空 CODEX_HOME 和空
  WeChat state 下重跑 Walking Skeleton 专项、完整 App、simulator、
  DAG、traceability、no-wait、TaskPack、Prestage、auth fixture 和
  secret scan。

本 Gate 中“bridge boundary”只指 Stage 1 已验收的 Walking Skeleton
进出站边界；不得据此声称 Stage 2 `CB-200` SQLite WAL durable
inbox/outbox spool 已实现。

## 3. Non-goals

- 不执行 `P2.1 / CB-200` 或任何 Stage 2 implementation；
- 不修改 `CyberBoss/app/**`、`CyberBoss/vendor/**`、固定 source bundle、
  product design、TaskPack 或 CB-000–CB-140/PG-0 历史 evidence；
- 不切换目标机 `current`，不启动/启用业务 service，不创建 Runtime route；
- 不执行真实 Codex device auth、WeChat QR/account、Private-MetaDatabase、
  Cloudflare、OCI 或其他 provider mutation；
- 不读取、打印、复制或提交 credential/secret value；
- 不创建新 repo、remote、submodule、Git URL dependency 或持续 upstream
  relation；
- 不 push，不创建 PR/tag/release，不触发远端发布；
- 不把 deterministic fixture、静态 fixture screenshot 或 read-only
  probe 称为真实 WeChat/Codex E2E；
- 不声称上游已经澄清许可证冲突。

## 4. Inputs to inspect

- `machine/facts/task_state.json`
- `machine/facts/owner_decisions.json`
- `machine/source-lock.json`
- `docs/evidence/PG-0/**`
- `docs/evidence/CB-100/**` 至 `docs/evidence/CB-140/**`
- `docs/product_design/v0.0.0.4/02_PRD_ACCEPTANCE_CONTRACT.md`
- `docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml`
- `docs/product_design/v0.0.0.4/10_TRACEABILITY_RELEASE_CHECKLIST.md`
- `docs/product_design/v0.0.0.4/12_CURRENT_ROADMAP.md`
- `docs/product_design/v0.0.0.4/implementation-kit/**`
- `app/package.json`、`app/package-lock.json`、完整 App tests
- Git branch/worktree/origin、remote publication read-only state
- 受保护本地部署记录解析出的目标标识与只读终态；不得持久化目标地址

## 5. Allowed modifications

- `CyberBoss/docs/governance/RUN_CONTRACT_PG_1.md`
- `CyberBoss/scripts/validate_pg1.py`
- `CyberBoss/docs/evidence/PG-1/**`
- `CyberBoss/machine/facts/task_state.json`
- `CyberBoss/README.md`
- `CyberBoss/HANDOFF.md`
- `CyberBoss/CHANGELOG.md`

除以上路径外不得修改。尤其禁止修改 App、vendor、product design、
CB-000–CB-140 evidence、PG-0 evidence、母仓根文件与其他项目。

## 6. Validation

```bash
python3 CyberBoss/scripts/validate_pg1.py --prepare
python3 CyberBoss/scripts/validate_pg1.py --final
python3 CyberBoss/scripts/validate_prestage0.py
python3 \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_task_dag.py \
  CyberBoss/docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml
python3 \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_traceability.py \
  CyberBoss/docs/product_design/v0.0.0.4
python3 \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_no_wait.py \
  CyberBoss/docs/product_design/v0.0.0.4
python3 \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_taskpack.py \
  CyberBoss/docs/product_design/v0.0.0.4
git diff --check
```

`validate_pg1.py` 必须真实执行而不是只查报告字符串：

- App Walking Skeleton static 4/4；
- App live simulator process chain 1/1；
- root CB-140 contract 5/5；
- root CB-130 process-family contract 5/5；
- implementation-kit simulator contract 5/5；
- App check 与完整 175/175 regression；
- clean auth fixture、secret scan、shell syntax；
- DAG/traceability/no-wait/TaskPack/Prestage。

目标机复核只能通过 strict known-host、key-only SSH 做只读元数据检查；
任何 SSH stderr、地址或 credential 内容不得进入 evidence。

## 7. Risks and rollback

- 历史漂移：以冻结 commit 的五个 Stage 1 evidence tree hash 为准，任何
  App/vendor/product design/历史 evidence 变化均 fail closed；
- simulator 冒充真实 adapter：真实 Codex/WeChat 必须继续为
  `activation_pending`，real turn/message count=0；
- “durable”术语越界：本 Gate 不声称 `CB-200` SQLite WAL spool；
- 隐式 credential：隔离环境移除 auth/provider/secret 变量，使用临时
  HOME 与空 adapter state；
- 目标探针误报：未计入通过的失败尝试必须保留，最终只读结果必须单独通过；
- GitHub 查询误用：任何未成功的查询尝试保留，最终 branch/PR/tag/release
  必须均为 0，外部对象变更必须为 0；
- 回滚仅 `git revert` 本地 PG-1 closure commit；Gate 不产生目标机、
  provider、数据或 GitHub 对象。

## 8. Stop conditions

- CB-000–CB-140 任一不是 `passed`，或 `CB-200` 以后任一 Task 已启动；
- Stage 1 historical evidence、implementation/closure topology 或
  Acceptance 映射不完整；
- 10/10 simulator chain、policy boundary、trace、latency、Mac-offline、
  loopback 或完整 App regression 任一失败；
- 真实 adapter 缺失被误报为 verified，或通过 Gate 需要真实 credential；
- strict `AGPL-3.0-only AND GPL-3.0-only` 处理、原许可证/源码/冲突记录
  或 `upstream_clarification_received=false` 任一丢失；
- 需要修改 App/vendor/product design/历史 evidence 或开始 CB-200；
- 需要目标机写入、公开 Runtime、真实 provider/data mutation、新 repo、
  push、PR、tag 或 release 才能通过。

## 9. Acceptance

`PG-1` 仅在以下全部成立时为 `passed`：

1. Stage 0 与 Stage 1 共 10 项 Task 均 `passed`；Stage 2–5 共 20 项 Task
   均 `not_started`；
2. CB-100–CB-140 五个 evidence tree 与冻结 commit 一致，五个
   implementation/closure commit 和 15 个 Acceptance ID 可验证；
3. CB-100 systemd/permission/singleton/restart、CB-110 pinned
   Node/Codex/Claude-off、CB-120 bounded workspace/no-clone identity、
   CB-130 supervised process family 均保持已验收状态；
4. fresh simulator Walking Skeleton 通过，冻结目标证据为 10/10 完整链、
   policy Runtime deltas `0/1/0`、20/20 latency；
5. trace correlation 完整且没有 raw message/result/identity；
6. Mac runtime dependency=0，non-loopback Runtime connection/listener=0，
   外部 8765/8780/19080 均不可达；
7. scrubbed credential matrix 全部通过，secret hits/P0/P1=0，外部写入=0；
8. 真实 WeChat/Codex 准确为 `activation_pending`，不声称 AC-001/AC-010
   real 已验证；
9. strict dual-license conflict posture、原源码/许可证/冲突记录完整，
   `upstream_clarification_received=false`；
10. 目标机 fresh read-only 终态为 service disabled/inactive、
    process/listener/staging/incoming/token=0，candidate retained inactive，
    `current`/workspace 未变化；
11. DAG、traceability、no-wait、TaskPack、Prestage 与 PG-1 validator
    全部通过；
12. `PG-1=passed` 后 `P2.1 / CB-200` 仍为 `not_started`，GitHub
    branch/PR/tag/release=0，闭环后工作树干净。
