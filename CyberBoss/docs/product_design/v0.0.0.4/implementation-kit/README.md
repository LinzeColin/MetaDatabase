# CyberBoss Full-Cloud MVP Implementation Kit

该目录是可直接复制进目标仓库的工程起点，不是“七文件限制”的补充说明。根目录控制文件负责产品/工程合同；本目录负责减少实现、部署、验证和恢复工作量。

## Contents

- `config/`：fail-closed 环境、workspace 和资源 profile 示例；
- `sql/`：SQLite WAL durable inbox/job/outbox/sync spool；
- `systemd/`：单进程族服务、状态、备份和确定性自愈；
- `scripts/`：host bootstrap、preflight、profile selection、启动、健康、部署、回滚、备份和恢复；
- `status/`：脱敏 snapshot generator 与全局 Status adapter；
- `tests/`：DAG/config/no-wait/SQLite 加速可靠性验证；
- `simulators/`：无真实凭据时使用的 WeChat、Private-MetaDatabase 和 object-store 合约模拟起点；
- `github-actions/`：CI 模板；
- `references/`：调研链接和复用决策。

P0.3 增加机器可读 identity/scope policy、无真实值的 credential slots、
Private-MetaDatabase 安全 wrapper、Cloudflare/OCI plan/apply adapters 与
provider simulator。真实 provider write 必须有外置精确 scope attestation；
缺失时返回 `activation_pending`，simulator 结果不会冒充真实激活。

P0.4 将 supplied WeChat/Codex simulator 补齐到 TaskPack contract：确定性
cursor/replay/fault/unknown-outcome、initialize/progress/approval/overload/
crash/false-success/late-event 与 artifact Oracle。两者只绑定 loopback；
`auth_activation_check.py` 只读取 CLI status 和文件 metadata，不读取 auth/
account 内容。真实 Codex/WeChat 未在目标 OVH 激活时继续
`activation_pending`。`secret_scan.py` 的七类模式均有独立 hostile fixture；
词边界使用真实 regex boundary，避免 token/JWT/Bearer/WeChat ID 漏报。

P1.2 增加项目级 runtime toolchain：`runtime-versions.json` 固定 Node.js
`24.18.0` 与 Codex CLI `0.146.0-alpha.3.1` 的官方 HTTPS archive 和
SHA-256；`install-runtime-toolchain.sh` 不写 `/usr/local`、不执行 package
lifecycle script，并把精确版本及 `node:sqlite`/App Server 命令绑定到
`releases/<commit>/version-manifest.json`。`probe-codex-app-server.mjs`
只允许 `ws://127.0.0.1:8765`，执行 `/readyz` 与
`initialize`/`initialized`，不启动 authenticated turn。Claude Code 不安装，
受控入口默认要求 `CB_CLAUDE_RUNTIME=true` 与
`CB_CLAUDE_EVAL_PASSED=true` 双门；部署默认均为 `false`。

P1.3 增加单一 root-controlled workspace registry 和运行前 realpath
复验；`/bind` 只接受 `cyberboss` alias，绝对路径、未知 alias、config/root
symlink 与未登记 Runtime root 均 fail closed。`workspace-budget.json` 固定
4 GiB workspace budget、8 GiB absolute stop、4 GiB host reserve 和
guard/protect/recover 阶梯，维护命令明确禁止 `--prune=now`。

`build-controlled-workspace-artifacts.py` 从 clean 本地 MetaDatabase commit
产生完整 CyberBoss Corresponding Source、`blob:none` sparse bare seed、
精确 canonical `private_db_client.py` 与 GitHub CLI archive；不 push，也不
clone Private-Database。`install-controlled-workspace.sh` 安装 candidate
release、唯一 sparse workspace 和 `cyberboss`/`cyberboss-data` 独立身份，
两次 apply 幂等，保持 `current`、service 和真实 data activation 不变。
root-owned immutable seed 通过 `--local --no-hardlinks` 离线复制，checkout
强制 `GIT_NO_LAZY_FETCH=1`；唯一 workspace 的 `safe.directory` 仅由
root-controlled `/etc/cyberboss/cyberboss.gitconfig` 授权。

P1.4 增加 commit-bound cloud supervisor。它把 loopback Codex Runtime、
Weixin simulator（真实 auth 未激活时）和 bridge 作为非 detached child
放在 `cyberboss-cloud.service` 的同一 cgroup；任一 critical child 异常退出
都会先清 readiness，再由 systemd 恢复整个 process family。固定入口不接受
environment shell command。

`/healthz` 与 `/readyz` 分离，`/status/snapshot.json` 只接受 `/run` 中的
ephemeral bearer token，并且只暴露 release、fixture claim 与布尔组件状态。
snapshot 和 allowlisted journal lifecycle marker 不包含 PID、账号/用户 ID、
thread、token、消息、prompt/result 或绝对路径。Runtime 固定
`127.0.0.1:8765`，status 固定 `127.0.0.1:8780`；simulator/real provider
只通过 root-controlled config 切换，simulator evidence 不代表真实激活。

`build-cloud-process-artifacts.py` 从 clean exact commit 生成完整
Corresponding Source。`install-cloud-process-family.sh` 只安装 immutable
candidate 和 value-free staging config，不移动 `current`、不启动或 enable
service。`accept-cloud-process-family.sh` 使用 transient `/run/systemd`
drop-in 完成 healthy/unready/snapshot、external scan、100 concurrent start、
100 singleton denial、100 kill/restart 和四类 fault recovery，最后恢复
disabled/inactive 且零 process/listener。

P1.5 在同一 process family 上增加 opt-in Walking Skeleton acceptance
trace。App 先执行精确 sender allowlist 和 `32768` UTF-8 byte gate，再允许
Runtime dispatch；acceptance trace 只保存派生 `trace_id`、input/output hash、
Runtime identity hash、阶段和 latency，不保存消息/结果正文、账号、sender、
token、workspace 或 target address。它只是 CB-140 evidence，不是 CB-200
SQLite spool。

`build-cloud-walking-skeleton-artifacts.py` 继续复用 exact-commit
Corresponding Source builder；`install-cloud-walking-skeleton.sh` 只安装
immutable CB-140 candidate。`accept-cloud-walking-skeleton.sh` 使用 transient
CB-140 drop-in 完成 simulator E2E `10/10`、unauthorized/32 KiB boundary、
idle latency `20/20`、trace correlation、Mac-offline 和 loopback/external
scan，再恢复 disabled/inactive 与零 process/listener。真实 WeChat/Codex
保持 `activation_pending`；该 Run 不执行 PG-1。

P2.1 增加版本化 SQLite WAL runtime spool。`001_runtime_spool.sql` 与
TaskPack starter schema 逐字一致；`002` 只增加 payload TTL/redaction
metadata、机器可读状态转换关系和数据库级 guard，不删除、重命名或收窄 v1
字段。启动入口验证 WAL、FULL synchronous、foreign keys、5000 ms busy
timeout、migration checksum 和 integrity check；v1 reader 在 v2 schema 上
继续可读。

`database-adapter.js` 是本阶段唯一 SQL repository 入口。它用 HMAC 派生稳定
opaque source/correlation/job ID，用 source replay uniqueness 与 payload
hash 拒绝 identity conflict，并以 optimistic `state_version` 和 immutable
redacted event 执行 PRD 状态图。inbox/context/target/outbox active payload
使用 caller-injected AES-256-GCM key，AAD 绑定 record identity，默认 24 小时
TTL 后替换为不可解密 sentinel；key、plaintext 和真实 identity 不写日志或
evidence。

专项测试真实执行 10,000 fixture、完整状态矩阵与 10,000 property attempt、
32 路并发 duplicate insert、五个进程崩溃切点、v1→v2/legacy reader、TTL
redaction、DB/WAL/SHM plaintext scan 和 mock canonical outage/recovery
set-diff。`build-runtime-spool-artifacts.py` 与 `install-runtime-spool.sh`
继续复用 exact-commit candidate pipeline；`accept-runtime-spool.sh` 只在
CB-200 staging 使用 synthetic ephemeral key，不启动 service、不切
`current`、不调用真实 provider/Private-MetaDatabase，也不执行 CB-210 或
PG-2。

P2.2 把微信 `fetch updates` 与 cursor commit 拆开。fetch 只返回 raw batch
与 candidate cursor；`DurableInboxCoordinator` 先用 CB-200 AES-256-GCM
spool 持久化 accepted/rejected inbox 和唯一 job，再显式 compare-and-set
cursor。numeric fixture 必须是从 committed 到 candidate 的最高连续序列；
gap、duplicate sequence、regression 或缺少稳定 provider message identity
全部 fail closed。opaque cursor 只有在 response 中全部 actionable message
durable 后才推进。

专项验证真实执行 fetch/durable/cursor 三个进程 `SIGKILL` 切点、同一 source
1,000 次 replay、reversed batch、gap/duplicate/regression property、policy
rejection、DB/query、mock canonical reconcile 和 DB/WAL/SHM plaintext/key
scan。每个 crash case 最终只有一个 inbox、一个 job、一次 synthetic
execution；synthetic execution 不代表真实 Runtime activation。

`build-durable-inbox-artifacts.py` 生成 complete Corresponding Source、
artifact manifest、checksums 和 `durable-inbox-matrix.json`；
`install-durable-inbox.sh` 只安装 immutable inactive candidate；
`accept-durable-inbox.sh` 只在 CB-210 staging 与独立 synthetic runtime root
使用 ephemeral keys/state。它们不切 `current`、不启动 service、不调用真实
WeChat/Runtime/Private-MetaDatabase。scheduler/global lease/claim recovery
仍属于 CB-220，outbox worker/retry/receipt 仍属于 CB-230，PG-2 不在本 Run
执行。

P2.3 增加 durable Runtime scheduler。Runtime job 按 `created_at,id` FIFO，
由 SQLite transaction claim 全局唯一 lease；partial unique index、owner
token、heartbeat、expiry 和 late-event fencing 共同保证 active Runtime
lease 最大值为 1。slash command 使用独立 control lease，因此 active turn
中的 `/stop` 不会排在 Runtime lease 后死锁；cancel acknowledgement 只记录
request，最终状态仍以 Runtime `completed`、`failed` 或 `interrupted` event
为真源。

每次 dispatch 都重新解析 root-controlled workspace alias；绝对路径、未知
alias、symlink escape 在 Runtime 调用前拒绝，且拒绝不得产生文件系统变化。
resource/readiness gate 同时检查 channel poll freshness、Runtime readiness、
memory、disk、inode、load、queue depth 与 stuck lease。measurement unavailable
默认阻断；protect 阶段只允许既有 read-only drain，不允许 bounded mutation
启动。只有明确 terminal retryable 的 read-only job 可在预算内自动重排；
dispatch 后 ambiguous mutation 永不自动 replay。

`build-job-scheduler-artifacts.py` 继续生成 clean exact-commit complete
Corresponding Source、manifest、checksums 与可执行
`job-scheduler-acceptance.json`。`install-job-scheduler.sh` 只安装 immutable
inactive candidate；`accept-job-scheduler.sh` 在 CB-220 staging 运行
deterministic scheduler/workspace/stop/recovery matrix，并在 128 MiB transient
cgroup 内运行有 64 MiB/64 MiB/1000 项硬上限的 immediate pressure fixture。
它不切 `current`、不 enable/start 业务 service，不读取真实凭据或调用真实
provider/Private-MetaDatabase。outbox worker 属于 CB-230，PG-2 不在本 Run
执行。

P2.4 增加 durable outbox 与 delivery truth。accepted ack 在 inbound cursor
commit 前进入 encrypted SQLite；final result、terminal error/cancelled
reply 在任何 provider dispatch 前按 Unicode code point 生成 deterministic
chunk、stable dedupe key 与 stable provider client ID。provider 只有返回可
归一化的明确 receipt 才能写 `confirmed`；全部 final chunks 确认前 job
保持 `reply_pending`，启动恢复会重新推导 `replied`/`reply_failed`。

retry 只接受 outcome 已知的 408/425/429/5xx 或明确 transient code，默认最多
5 次 bounded jittered exponential delay，clock、random 与 timer 均可注入。
401/invalid context 直接 terminal；只有发现不同的新 context 时才另行发送
固定脱敏 re-login 建议。provider 无端到端幂等/查询合同时，dispatch 已开始
但 confirmation 未提交的恢复一律标记 `ambiguous_send_outcome` 和
`manual_reconcile_required`，自动重发次数为 0，不能声称 exactly-once
provider delivery。

`build-durable-outbox-artifacts.py` 生成 clean exact-commit complete
Corresponding Source、manifest、checksums 与
`outbox-recovery-matrix.json`；`install-durable-outbox.sh` 只安装 immutable
inactive candidate；`accept-durable-outbox.sh` 仅在 CB-230 staging 和独立
synthetic runtime root 使用 ephemeral keys、fixture provider 与 virtual
clock。它不切 `current`、不 enable/start service、不读取真实凭据，不调用
真实 WeChat/Runtime/Private-MetaDatabase。canonical sync 属于 CB-240，
PG-2 仍须在五个 Stage 2 tasks 全部通过后独立执行。

P2.5 增加 identity-separated canonical sync。code plane 只把 terminal
job/material event 映射为严格 allowlist 的脱敏记录，按最多 50 条、
262144 bytes 或 60 秒生成 deterministic gzip content-addressed object；
`cyberboss-data` data plane 才能经 fail-closed wrapper 调用
`private_db_client.py ingest|get|list|verify`。wrapper 绑定实际 OS identity，
禁止 code identity 执行 data client，且全流程不 clone
Private-Database。

sync worker 在 ingest 前后均重取 manifest/object/event set；409、429、
403、transient 与 partial-success 保持 pending 或安全确认，不做
last-write-wins。同 event ID/different record hash 进入 P0 quarantine 并
阻断新的 bounded mutation，read-only 仍可 drain。专项验收执行 1,000
terminal events、50 concurrent sync groups、10 分钟虚拟 outage/catch-up，
删除隔离 SQLite 后仅从 canonical objects 与 deterministic R2 pointer
fixture 重建 terminal index 和供 CB-300 消费的 Timeline source。真实
Private-MetaDatabase、R2、Timeline Web/build/search 均保持
`activation_pending`/后续 phase 边界；本 Run 不执行 PG-2。

## Immediate validation

```bash
python implementation-kit/tests/validate_task_dag.py 04_TASK_DAG_EXECUTION_PACK.yaml
python implementation-kit/tests/validate_no_wait.py .
python implementation-kit/tests/validate_traceability.py .
python implementation-kit/tests/validate_taskpack.py .
node implementation-kit/tests/validate_config.js \
  --allow-placeholders \
  implementation-kit/config/cyberboss.env.example \
  implementation-kit/config/workspaces.json.example
python3 implementation-kit/scripts/scope_policy.py validate
python3 implementation-kit/tests/test_identity_scope.py
python3 implementation-kit/tests/test_workspace_budget.py
python3 implementation-kit/tests/test_external_adapters.py
node --test implementation-kit/tests/access-policy-contract.test.js
node --test implementation-kit/tests/simulator-contract.test.mjs
python3 implementation-kit/scripts/cloudflare_adapter.py plan
python3 implementation-kit/scripts/oci_object_adapter.py plan
python3 implementation-kit/scripts/auth_activation_check.py \
  --mode local --output /tmp/cyberboss-auth-probe.json

for f in implementation-kit/scripts/*.sh implementation-kit/simulators/*.sh; do
  bash -n "$f"
done
node --check implementation-kit/status/generate-status.js
node --check implementation-kit/status/global-status-adapter.js
node --test implementation-kit/tests/status-adapter-contract.test.js
node --check implementation-kit/simulators/weixin-ilink-simulator.mjs
node --check implementation-kit/simulators/codex-app-server-simulator.mjs
bash implementation-kit/scripts/preflight.sh --check
python3 implementation-kit/tests/test_resource_profile.py
python3 implementation-kit/scripts/resource-pressure-fixture.py
bash implementation-kit/scripts/install-runtime-toolchain.sh \
  --check --release-id 0000000000000000000000000000000000000000
bash implementation-kit/scripts/install-controlled-workspace.sh \
  --check --release-id 0000000000000000000000000000000000000000
python3 -m py_compile \
  implementation-kit/scripts/build-cloud-process-artifacts.py
bash implementation-kit/scripts/install-cloud-process-family.sh \
  --check --release-id 0000000000000000000000000000000000000000
python3 -m py_compile \
  implementation-kit/scripts/build-job-scheduler-artifacts.py
bash implementation-kit/scripts/install-job-scheduler.sh \
  --check --release-id 0000000000000000000000000000000000000000
bash implementation-kit/scripts/accept-job-scheduler.sh \
  --check --release-id 0000000000000000000000000000000000000000
python3 -m py_compile \
  implementation-kit/scripts/build-durable-outbox-artifacts.py
bash implementation-kit/scripts/install-durable-outbox.sh \
  --check --release-id 0000000000000000000000000000000000000000
bash implementation-kit/scripts/accept-durable-outbox.sh \
  --check --release-id 0000000000000000000000000000000000000000
python3 -m py_compile \
  implementation-kit/scripts/build-canonical-sync-artifacts.py
bash implementation-kit/scripts/install-canonical-sync.sh \
  --check --release-id 0000000000000000000000000000000000000000
bash implementation-kit/scripts/accept-canonical-sync.sh \
  --check --release-id 0000000000000000000000000000000000000000
python3 -m py_compile \
  implementation-kit/scripts/build-cloud-walking-skeleton-artifacts.py
bash implementation-kit/scripts/install-cloud-walking-skeleton.sh \
  --check --release-id 0000000000000000000000000000000000000000
bash implementation-kit/scripts/accept-cloud-walking-skeleton.sh \
  --check --release-id 0000000000000000000000000000000000000000
python3 -m py_compile \
  implementation-kit/scripts/build-runtime-spool-artifacts.py
bash implementation-kit/scripts/install-runtime-spool.sh \
  --check --release-id 0000000000000000000000000000000000000000
bash implementation-kit/scripts/accept-runtime-spool.sh \
  --check --release-id 0000000000000000000000000000000000000000
node --check implementation-kit/scripts/run-walking-skeleton-acceptance.mjs
node --check implementation-kit/scripts/probe-codex-app-server.mjs

db="$(mktemp)"
sqlite3 "$db" < implementation-kit/sql/runtime-spool.sql
sqlite3 "$db" 'PRAGMA integrity_check;'
python implementation-kit/tests/accelerated_reliability.py \
  --schema implementation-kit/sql/runtime-spool.sql \
  --replays 1000 --restarts 100 --send-faults 100 --restore-cycles 20
```

## Target-host sequence

```bash
sudo implementation-kit/scripts/bootstrap-host.sh --apply
implementation-kit/scripts/preflight.sh
sudo implementation-kit/scripts/select-resource-profile.sh \
  --write /etc/cyberboss/resource-profile.env \
  --systemd-dropin /etc/systemd/system/cyberboss-cloud.service.d/20-resource-profile.conf
sudo implementation-kit/scripts/install-runtime-toolchain.sh \
  --apply --release-id <full-local-implementation-commit>
sudo implementation-kit/scripts/install-runtime-toolchain.sh \
  --verify --release-id <full-local-implementation-commit>
sudo implementation-kit/scripts/install-controlled-workspace.sh \
  --apply \
  --release-id <full-local-implementation-commit> \
  --artifacts /var/lib/cyberboss/incoming/cb120-<full-local-implementation-commit>
sudo implementation-kit/scripts/install-controlled-workspace.sh \
  --verify \
  --release-id <full-local-implementation-commit> \
  --artifacts /var/lib/cyberboss/incoming/cb120-<full-local-implementation-commit>
sudo implementation-kit/scripts/install-cloud-process-family.sh \
  --apply \
  --release-id <full-local-implementation-commit> \
  --artifacts /var/lib/cyberboss/incoming/cb130-<full-local-implementation-commit>
sudo implementation-kit/scripts/install-cloud-process-family.sh \
  --verify \
  --release-id <full-local-implementation-commit> \
  --artifacts /var/lib/cyberboss/incoming/cb130-<full-local-implementation-commit>
sudo implementation-kit/scripts/install-cloud-walking-skeleton.sh \
  --apply \
  --release-id <full-local-implementation-commit> \
  --artifacts /var/lib/cyberboss/incoming/cb140-<full-local-implementation-commit>
sudo implementation-kit/scripts/install-cloud-walking-skeleton.sh \
  --verify \
  --release-id <full-local-implementation-commit> \
  --artifacts /var/lib/cyberboss/incoming/cb140-<full-local-implementation-commit>
sudo implementation-kit/scripts/install-runtime-spool.sh \
  --apply \
  --release-id <full-local-implementation-commit> \
  --artifacts /var/lib/cyberboss/incoming/cb200-<full-local-implementation-commit>
sudo implementation-kit/scripts/install-runtime-spool.sh \
  --verify \
  --release-id <full-local-implementation-commit> \
  --artifacts /var/lib/cyberboss/incoming/cb200-<full-local-implementation-commit>
sudo implementation-kit/scripts/accept-runtime-spool.sh \
  --run \
  --release-id <full-local-implementation-commit> \
  --output-dir \
  /var/lib/cyberboss/cb200-staging/evidence/acceptance-<full-local-implementation-commit>
```

`preflight.sh` 只读并输出三次即时脱敏 snapshot；有限 cgroup v2 memory/swap
ceiling 会覆盖更大的 host `/proc` 数值，profile writer 在安全预算不足时拒绝写入。
任何本地或容器 pressure 结果都不能替代同一获授权 OVH 主机的基线与有界
induced-load/cgroup 证据。

Runtime installer 的 `--apply` 与 `--verify` 都必须使用同一个完整 40 位
implementation commit。Codex device auth 只准备命令，不在该安装序列执行；
真实认证留到最终一次性激活。App Server 验收结束后必须确认进程和 8765
listener 都为零，`cyberboss-cloud.service` 继续 disabled/inactive。

CB-120 artifact builder 只能从 branch
`codex/cyberboss-prestage0` 的 clean exact HEAD 构建。bare seed 的
artifact remote 不是 GitHub/upstream remote；目标 workspace origin 只指向
该本地 immutable seed。candidate release 不切换 `current`，data credential
缺失时准确保持 `activation_pending`，不得为了通过验收执行真实 `gh api`。

CB-130 acceptance 的 `--prepare` 只建立 transient drop-in 和 ephemeral
status token，供 operator-host 立即执行外部 8765/8780 scan；随后
`--exercise` 运行完整机制型 matrix 并自动 cleanup。任何失败都必须执行
`--cleanup`，不得留下 active service、cgroup child、listener、drop-in 或
token。candidate 与 staging env 可保留审计，`current` 和 CB-120 workspace
不得变化。

CB-140 acceptance 使用 operator ready/release marker 让外部端口扫描发生在
service active 窗口内；marker、status token、trace working file 和 systemd
drop-in 都只存在于 transient scope。导出的 JSON/NDJSON/HTML 仅含 synthetic
或 redacted evidence；真实 adapter 缺失时继续 `activation_pending`，不等待、
不伪造，也不执行 PG-1。

CB-200 acceptance 不运行 process family。它在 pinned Node.js 下重跑
migration/state/concurrency/crash/privacy tests，再在 staging DB 生成
10,000 fixture、schema dump 和 machine-readable report；退出时删除
synthetic key 与 DB/WAL/SHM。operator 保存脱敏 report 后必须删除 CB-200
staging env/state/incoming，确认 canonical `runtime.db` 仍不存在且 service
保持 disabled/inactive。真实 channel poll、scheduler、outbox worker 和
canonical client 分别留给 CB-210–CB-240。

CB-210 acceptance 同样不运行 process family。它在
`/var/lib/cyberboss/cb210-runtime-<commit>` 的独立 synthetic scope 重跑
candidate-cursor、三 crash cuts、1,000 replay、ordering/query/privacy
matrix，保存脱敏 report 后删除 synthetic root。operator 随后删除 CB-210
staging env/state/incoming，确认 canonical `runtime.db` 不存在、service
disabled/inactive、零 process/listener 且 `current`/workspace 未改变。

`resource-pressure-fixture.py` 默认 `--evidence-scope=local_container`，不得
改称实机证据。只有目标授权链和只读 baseline 已在外层证据中验证、且 fixture
确实运行于该 host 的有限 ephemeral container 时，才可使用
`--evidence-scope=authorized_live_host_container`；该标志本身不授予权限。

之后按 `06_OPERATIONS_STATUS_HANDOVER.md` 从 `CB_INCOMING_ROOT` 内的已校验本地制品安装
candidate release。真实凭据缺失时不等待：运行 simulator、完成其余代码和部署槽位，
把对应 adapter 标记 `activation_pending`。

## Non-negotiable

- Codex App Server 只允许 loopback；
- 不依赖 Mac；
- 不把 secret、微信原始私聊或完整 prompt/result 写入代码仓、
  Private-MetaDatabase、Status 或 Timeline；
- Private-Database 只允许通过 `private_db_client.py` 的
  `ingest/get/list/verify` 免 clone 存取；
- PG-0–PG-5 全部通过前，不 push、不创建 PR/tag；
- 不使用真实时间 Soak、观察期、固定 `sleep` readiness 或凭据等待节点；
- simulator 通过不得冒充真实 adapter 通过；
- Acceptance Contract 是最终 Pass Gate。
