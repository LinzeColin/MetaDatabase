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

## Immediate validation

```bash
python implementation-kit/tests/validate_task_dag.py 04_TASK_DAG_EXECUTION_PACK.yaml
python implementation-kit/tests/validate_no_wait.py .
python implementation-kit/tests/validate_traceability.py .
python implementation-kit/tests/validate_taskpack.py .
node implementation-kit/tests/validate_config.js \
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
