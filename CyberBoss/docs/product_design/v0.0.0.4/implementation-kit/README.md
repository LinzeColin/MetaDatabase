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
python3 implementation-kit/tests/test_external_adapters.py
node --test implementation-kit/tests/access-policy-contract.test.js
python3 implementation-kit/scripts/cloudflare_adapter.py plan
python3 implementation-kit/scripts/oci_object_adapter.py plan

for f in implementation-kit/scripts/*.sh implementation-kit/simulators/*.sh; do
  bash -n "$f"
done
node --check implementation-kit/status/generate-status.js
node --check implementation-kit/status/global-status-adapter.js
node --test implementation-kit/tests/status-adapter-contract.test.js
node --check implementation-kit/simulators/weixin-ilink-simulator.mjs
bash implementation-kit/scripts/preflight.sh --check
python3 implementation-kit/tests/test_resource_profile.py
python3 implementation-kit/scripts/resource-pressure-fixture.py

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
```

`preflight.sh` 只读并输出三次即时脱敏 snapshot；有限 cgroup v2 memory/swap
ceiling 会覆盖更大的 host `/proc` 数值，profile writer 在安全预算不足时拒绝写入。
任何本地或容器 pressure 结果都不能替代同一获授权 OVH 主机的基线与有界
induced-load/cgroup 证据。

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
