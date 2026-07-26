# CyberBoss Full-Cloud MVP — Traceability & Release Checklist

- 版本：`v0.0.0.4-final`
- 日期：`2026-07-26`
- 目标：把需求、任务、测试、证据、制品和发布结论闭环，避免开发 Agent 漏项、重复劳动或用“已运行一段时间”代替工程验证。

---

## 1. 使用规则

1. 本文件是执行核对表，不新增与 `02_PRD_ACCEPTANCE_CONTRACT.md` 冲突的需求。
2. 验收依据是可执行 Oracle，不是主观描述、截图堆积或真实时间 Soak。
3. 每项只能处于：`passed`、`failed`、`activation_pending`、`hazard_blocked`、`not_applicable`。
4. `activation_pending` 仅允许用于真实外部适配器；模拟器、代码、测试、部署槽位和其余无关任务必须继续。
5. 不为证据专门制造大量 JSON 台账。优先保留：测试报告、命令输出、Git commit、状态快照、恢复/回滚报告和必要截图。
6. 所有敏感值必须脱敏；不得把微信 ID、token、prompt/result 原文、Codex auth、绝对私人路径写入普通证据。
7. 禁止固定等待、24 小时/7 天/30 天观察 Gate、`sleep` 型 Canary 或“等待凭据后再开发”。

---

## 2. 权威链

```text
Canonical Facts
→ Acceptance Contract
→ Task DAG
→ Implementation
→ Automated Tests
→ Continuous Evidence
→ Immutable Release
→ Request-count Canary
→ Final State
```

发生冲突时按以下顺序处理：

```text
00_README_FIRST.md
→ 02_PRD_ACCEPTANCE_CONTRACT.md
→ 04_TASK_DAG_EXECUTION_PACK.yaml
→ 03_ARCHITECTURE_DATA_SECURITY.md
→ 05_ACCELERATED_VERIFICATION_MODEL_SECURITY_RELEASE.md
→ 06_OPERATIONS_STATUS_HANDOVER.md
→ 09_PREAUTHORIZED_DECISIONS_ACTIVATION_INPUTS.md
→ 本文件
```

---

## 3. 端到端 Traceability Matrix

| 能力域 | Requirements / Oracle | DAG 节点 | 主要测试 | 最低证据 | 发布制品 |
|---|---|---|---|---|---|
| 固定来源基线与许可证 | AC-034, AC-069 | CB-000 | fixed-bundle install/test、license scan、diff map、upstream-separation scan | pinned SHA、bundle hash、license/dependency report | baseline report、source bundle |
| OVH 容量与现有 Status | AC-042, AC-046, AC-064 | CB-010, CB-310, CB-340 | live inventory、profile calculator、resource fixture | redacted `free/df/ss/systemctl`、profile output | capacity config、status adapter |
| 微信 Channel | AC-001–AC-006 | CB-020, CB-130, CB-200, CB-210 | simulator contract、real QR E2E（激活后）、oversize/unauthorized | simulator report；真实适配器为 verified 或 activation_pending | channel adapter、activation command |
| Codex Runtime | AC-010–AC-017 | CB-020, CB-110, CB-140, CB-220, CB-410 | mock runtime、loopback assertion、workspace escape、cancel/approval | process/port evidence、runtime tests | pinned Codex config、runtime adapter |
| Durable Inbox/Cursor | AC-003–AC-005, AC-023, AC-061–AC-063 | CB-200, CB-210, CB-400 | 1,000 replay、事务切点 crash、cursor commit ordering | replay/crash report、SQLite set diff | migration、durable inbox implementation |
| Job State Machine | AC-012, AC-016, AC-024 | CB-200, CB-220 | legal/illegal transition table、lease expiry、single active | state-machine test report | state machine、migration |
| Durable Outbox | AC-020–AC-025 | CB-200, CB-210, CB-230, CB-400 | send-before/after crash、100 send faults、chunk ordering | receipt/dedupe report | outbox worker、retry policy |
| Private-MetaDatabase Canonical | AC-030–AC-033, AC-063 | CB-240, CB-300, CB-400 | fake API、object/manifest 409/429 fixture、reconcile | object/manifest hash/set-diff report | no-clone canonical adapter、batch format |
| Timeline/Search | AC-034–AC-036 | CB-300, CB-320 | rebuild from canonical、date/category/job queries | build/search report、protected route check | timeline build and route |
| Health/Status/Analytics | AC-040–AC-047 | CB-310, CB-320, CB-340 | health dimension faults、redaction lint、status adapter fixture | snapshots、redaction report、analytics config | status exporter/card、Access policy |
| Backup/R2/OCI | AC-050–AC-053 | CB-330, CB-430 | online snapshot、hash verify、20 isolated restore cycles、simulator/real upload | snapshot manifest、restore-cycle report | backup/restore scripts、retention config |
| Release/Rollback | AC-054–AC-056, AC-065–AC-068 | CB-440, CB-500, CB-510, CB-520, CB-530 | immutable release、request-count canary、rollback and re-forward | deployed local commit、health snapshots、rollback report | release directory、immutable label、runbook |
| Security/Privacy/Supply Chain | AC-043, AC-066, AC-069 | CB-030, CB-410, CB-420 | secret scan、SAST、dependency/license/SBOM、abuse paths | scan outputs、risk disposition | hardened unit/config、source offer |
| Model Capability/Safety | AC-060, AC-067 | CB-410, CB-420 | golden prompts、red-team corpus、approval/non-fabrication | eval report、System Card | model config、eval corpus |
| No-wait / No-soak | AC-056, AC-070 | CB-030, CB-400, CB-520, CB-540 | static no-wait lint、fake clock、fault loops | `NO_WAIT_VALIDATION=PASS` | CI gate、final report |

---

## 4. Release Evidence Contract

每个 Stage 只保留一个可读的 Stage Summary，加上真实工具输出；不建立形式化证据仓库。

### 4.1 必须存在

```text
artifacts/release/<release-id>/
├── RELEASE_REPORT.md
├── SOURCE_BASELINE.md
├── TEST_SUMMARY.md
├── SECURITY_MODEL_SUMMARY.md
├── DEPLOYMENT_REPORT.md
├── RESTORE_ROLLBACK_REPORT.md
├── status-before.json
├── status-after.json
├── checksums.sha256
└── raw-logs/              # 仅必要、脱敏、受限大小
```

### 4.2 不得存在

```text
EVIDENCE/<每任务一个json>
SCHEMAS/<重复规格json>
真实 token/auth.json
微信原始私聊导出
完整 prompt/result 默认归档
无限增长的 raw log
“passed=true”但没有命令/测试出处的自报台账
```

### 4.3 证据命名

- `release-id`：`cyberboss-v<version>-<git-short-sha>`；
- 测试结果应包含 command、exit code、assertion totals、failed cases；
- 截图仅用于证明外部 UI/微信可见结果，不替代状态或数据一致性测试；
- 所有 hash 使用 SHA-256；
- 每个报告必须列出未验证项，不得把 simulator 结果写成真实外部适配器通过。

---

## 5. 开发完成前的立即可执行检查

### 5.1 规格和 DAG

```bash
python implementation-kit/tests/validate_task_dag.py 04_TASK_DAG_EXECUTION_PACK.yaml
python implementation-kit/tests/validate_no_wait.py .
python implementation-kit/tests/validate_traceability.py .
node implementation-kit/tests/validate_config.js \
  --allow-placeholders \
  implementation-kit/config/cyberboss.env.example \
  implementation-kit/config/workspaces.json.example
```

Pass Gate：

- 30 个 Task ID 唯一；
- 所有依赖存在；
- DAG 无循环；
- 每个 Stage 不超过 5 个 Task；
- 每个 Task 有输入、输出、动作、测试、证据、风险、回滚、Stop Condition、AC、Pass Gate；
- 无真实时间 Soak、观察期任务、固定长 sleep 或凭据等待节点。

### 5.2 工程静态检查

```bash
shellcheck implementation-kit/scripts/*.sh
for f in implementation-kit/scripts/*.sh; do bash -n "$f"; done
node --check implementation-kit/status/generate-status.js
node --check implementation-kit/status/global-status-adapter.js
python -m compileall implementation-kit/tests
```

Pass Gate：exit code 全部为 0。

### 5.3 数据层

```bash
db="$(mktemp)"
sqlite3 "$db" < implementation-kit/sql/runtime-spool.sql
sqlite3 "$db" 'PRAGMA integrity_check;'
python implementation-kit/tests/accelerated_reliability.py \
  --schema implementation-kit/sql/runtime-spool.sql \
  --replays 1000 \
  --restarts 100 \
  --send-faults 100 \
  --restore-cycles 20
```

Pass Gate：

- integrity=`ok`；
- duplicate executions=`0`；
- lost accepted messages=`0`；
- duplicate terminal replies=`0`；
- illegal transitions=`0`；
- restore hash mismatches=`0`。

### 5.4 Provider Contract

在无真实凭据时立即运行：

```text
WeChat simulator
Codex runtime simulator
Private-MetaDatabase content-addressed simulator
local immutable object-store simulator
status adapter fixture
fake clock
```

真实凭据激活后，只补跑真实 adapter E2E；不得重做已经通过的内部层测试。

### 5.5 安全

至少运行：

```text
secret scan
SAST / CodeQL
npm audit or equivalent advisory scan
SBOM generation
license inventory
loopback listener assertion
workspace traversal and symlink escape tests
unauthorized user/command tests
status/timeline/log redaction lint
```

Pass Gate：

- P0/P1 未处置项=`0`；
- secret findings=`0`；
- Codex non-loopback listeners=`0`；
- workspace escape success=`0`；
- status forbidden-pattern hits=`0`。

---

## 6. Accelerated Reliability Gate

不等待真实时间流逝。一次执行完成以下矩阵：

| 类别 | 次数/切点 | 必须证明 |
|---|---:|---|
| 入站重放 | 1,000 | 同一 source message 只对应一次 execution |
| 进程重启 | 100 | durable inbox/job/outbox 无丢失、可恢复 |
| Runtime crash | 100 | lease 回收、状态真实、无双执行 |
| 微信 send fault | 100 | 重试有界、最终回复至多一次 |
| Cursor crash cut | 每个事务边界至少 1 次 | cursor 永不越过未持久消息 |
| Canonical conflict/rate-limit | 每类至少 20 | 可补偿、稳定 ID、set diff=0 |
| Timeline rebuild | 20 | canonical → Timeline 可重复且 hash 匹配 |
| R2/OCI restore | 20 | 隔离目录可恢复、integrity=ok |
| Deployment rollback/re-forward | 每方向至少 5 | symlink、migration、health 一致 |
| Resource pressure | memory/disk/queue 阶梯 | protect/degraded/recover 状态正确 |
| Fake-clock lifecycle | retry/TTL/reminder/check-in/backup | 不等待真实时间即可覆盖边界 |

任一 P0 失败即不得声明 `MVP_LIVE`。

---

## 7. Production Activation Checklist

### 7.1 一次性输入

- [ ] OVH SSH/sudo 可用；
- [ ] `codex login --device-auth` 完成；
- [ ] 微信二维码扫码成功且 user ID 加入白名单；
- [ ] Private-Database 最小权限 client identity 就位，或
  `activation_pending:private_db`；
- [ ] PG-0–PG-5 全部通过后的最终 MetaDatabase code publish 凭据就位；
- [ ] Cloudflare DNS/Access/R2 最小权限凭据就位；
- [ ] OCI prefix-scoped 凭据就位，或状态明确为 `activation_pending:oci`；
- [ ] `cyberboss.linzezhang.com` 和 `status.linzezhang.com` 路由已核对。

缺少某项时：只标记对应 adapter `activation_pending`，继续所有其他开发、验证和可逆部署。

### 7.2 激活顺序

1. 安装 immutable candidate release；
2. 应用 additive migration；
3. 运行 offline/loopback health；
4. 启动 candidate slot；
5. 运行 simulator E2E；
6. 逐个注入外部凭据并运行真实 adapter smoke；
7. 通过请求数 Canary：先内部请求，再授权微信真实请求；
8. 切换 `current` symlink；
9. 运行完整 health/status/canonical/backup检查；
10. 保留上一版本并验证一键 rollback；
11. 输出最终状态，不等待观察期。

---

## 8. Request-count Canary

Canary 不是按分钟/小时挂机，而是按请求和错误预算推进：

| Step | 输入 | Gate |
|---|---|---|
| C0 | simulator 20 请求 | 全部通过，重复/丢失=0 |
| C1 | 内部受控 10 请求 | E2E、status、canonical 全部正确 |
| C2 | 授权微信 10 请求 | 成功率 100%，重复终态回复=0 |
| C3 | 故障注入 20 请求 | degraded/recovery/rollback符合合同 |
| C4 | 正式槽位 20 请求 | 无 P0/P1；资源在选定 profile 内 |

任一步失败立即回滚或保持 candidate，不等待“再观察一会儿”。

---

## 9. Final State Decision

只能输出一个：

| 状态 | 定义 |
|---|---|
| `MVP_LIVE` | 所有 P0、真实微信+Codex主链、部署/回滚/恢复、资源和安全 Gate 全部通过 |
| `MVP_DEGRADED` | 核心可用，但一个非核心 P1 外部 adapter 或备份层降级；状态和修复动作明确 |
| `ACTIVATION_PENDING` | 软件/模拟/部署槽位已完成，但真实微信、Codex、DNS或凭据激活尚缺至少一项 |
| `STOPPED` | 触发不可接受的安全、数据、许可证、账户风控或不可逆风险 |
| `NOT_VERIFIED` | 证据不足，禁止宣称成功 |

### 最终报告必须回答

1. 部署 local commit/immutable label 是什么；最终 tag 是否只在 PG-5 后创建；
2. 当前资源 profile 是什么；
3. 微信、Codex、Private-Database、GitHub final publication、R2、OCI 分别是 verified / activation_pending / failed；
4. AC-001–AC-070 有多少 passed/failed/pending；
5. 是否存在重复执行、丢失消息、重复回复；
6. 最近一次 restore、rollback、re-forward 是否通过；
7. 当前 status snapshot 与最终结论是否一致；
8. 一键 rollback 命令是什么；
9. 未解决风险是什么；
10. 最终唯一状态是什么。

---

## 10. Release Sign-off

```text
Release ID:
Code commit:
Data schema version:
Resource profile:
Real WeChat adapter:
Real Codex adapter:
Private-MetaDatabase canonical:
Cloudflare Access/R2:
OCI backup:
Acceptance passed / failed / activation_pending:
Security P0/P1 open:
Rollback verified:
Restore verified:
No-wait lint:
Final state:
Decision authority:
```

没有完整字段、没有对应证据或 final state 与 status 不一致时，不得签署 `MVP_LIVE`。
