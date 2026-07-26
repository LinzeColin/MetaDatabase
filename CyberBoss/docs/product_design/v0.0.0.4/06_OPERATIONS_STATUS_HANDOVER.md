# 06 — 安装、运维、Status、自愈、恢复与交接

## 1. 运维目标

运营者只需要理解四个结论：

```text
MVP_LIVE           真实主链路和必要可靠性均已验证
MVP_DEGRADED       可继续有限使用，但有明确降级原因
ACTIVATION_PENDING 可控开发和模拟验收完成，仍缺一个或多个真实外部激活
STOPPED            为保护数据/安全/资源而停止相应执行路径
NOT_VERIFIED       尚无足够证据，不能宣称可用
```

运维不依赖 LLM。Codex/Claude 只执行产品任务与受控开发；health、status、self-heal、backup、restore 和 rollback 由确定性命令完成。

---

## 2. 一次性激活输入与无阻塞规则

开发 Agent 不得在开发过程中零散索取输入。所有不可代替的人类动作集中到最终激活窗口；缺失时使用 simulator/mock 完成全部非激活工作。

### 2.1 最小激活表

| Activation | 人类动作 | Agent 现在必须完成 | 缺失时的准确状态 |
|---|---|---|---|
| OVH | 提供 sudo/SSH 或执行一次入口命令 | repo-local代码、安装脚本、systemd、preflight、release slot、mock部署 | `activation_pending:ovh`；其余开发继续 |
| Codex | OVH 上执行 `codex login --device-auth` 并浏览器确认 | CLI安装、受保护home、app-server simulator、protocol contract、启动/诊断命令 | `activation_pending:codex_auth` |
| WeChat | 扫一次 CyberBoss 二维码 | iLink simulator、durable inbox/outbox、cursor/idempotency、真实登录命令 | `activation_pending:wechat`；风控只阻止真实channel |
| Private-Database | 注入仅限 `Private-MetaDatabase` 的 client identity | fake API、object/manifest、409/429/reconcile 测试 | `activation_pending:private_db` |
| GitHub code | 全部 PG 通过后注入 MetaDatabase repo-scoped 凭据 | 本地 branch/commit/CI 和最终一次性 publish script | `activation_pending:github_publish` |
| Cloudflare | 注入DNS/Access/R2最小权限凭据 | route/Access/R2模板、origin/adapter测试、匿名拒绝fixture | `activation_pending:cloudflare` |
| OCI | 注入bucket/prefix凭据 | adapter、mock、manifest/replica验证 | `activation_pending:oci`；不阻塞MVP核心 |

### 2.2 默认名称

```text
Application repo: LinzeColin/MetaDatabase
Application subpath: CyberBoss/
Canonical hot-data repo: LinzeColin/Private-Database
Canonical data root: Private-MetaDatabase (domain=CyberBoss)
Canonical access: private_db_client.py ingest/get/list/verify; clone forbidden
Domain: cyberboss.linzezhang.com
Linux user: cyberboss
Application root: /opt/cyberboss-cloud
State root: /var/lib/cyberboss
Workspace root: /srv/cyberboss-workspaces
Config root: /etc/cyberboss
HTTP loopback: 127.0.0.1:8780
Codex App Server: 127.0.0.1:8765
Storage timezone: UTC
Display timezone: Australia/Sydney
```

实际仓库/路径只在 `activation.env`、systemd environment和CI变量各自引用一次；禁止保留多套互相冲突的别名。

### 2.3 激活执行顺序

```text
准备阶段：全部simulator/CI/deploy slot通过
→ 注入OVH/Private-Database/Cloudflare/R2凭据
→ Codex device auth
→ WeChat扫码
→ 一次性DNS/Access切换
→ 真实请求计数Canary
→ verified或activation_pending/failed
```

任何一步未完成都不得让 Agent等待；它只影响相应真实adapter的最终状态。

---

## 3. Clean Installation Golden Path

> Starter files are in `implementation-kit/`. They are scaffolds and must be
> reconciled with the fixed local source bundle before production. Commands
> containing placeholders must fail closed until values are replaced.

### 3.1 Preflight（测量与选档，不是等待 Gate）

```bash
bash implementation-kit/scripts/preflight.sh
```

脚本不需要 `sudo`，不产生持久写入（自动清理自己的临时目录）；它连续采集三次
即时 snapshot（不等待真实时间），并仅输出脱敏聚合：

- Linux/architecture；
- effective memory/swap（有限 cgroup v2 ceiling 优先于更大的 host `/proc`
  数值）、load/disk/inode；
- listener port 与 bind scope（不输出 IP）；
- Node/Codex/Git/systemd/SQLite能力；
- 现有 process/service/container、反向代理和 Status ingestion 摘要；
- canonical path 是否存在（不读取 secret 或业务文件内容）；
- `constrained`、`tiny` 或 `standard` resource profile；
- MemoryHigh/MemoryMax、disk cap、protect/recover 阈值与安全清理建议。

输出：

```text
PREFLIGHT=PASS | PASS_WITH_ACTIVATION_PENDING | HAZARD_BLOCKED
CB_RESOURCE_PROFILE=constrained | tiny | standard
CB_RESOURCE_GUARD_STATE=recover | warn | protect
CB_RESOURCE_ACTIVATION_SAFE=true | false
CB_RESOURCE_BLOCK_REASONS=none | <comma-separated reasons>
WARNING=<zero or more redacted warnings>
REMEDIATION=<zero or more redacted remediations>
```

RAM/磁盘低不会自动终止整个开发：先降档、使用 partial/sparse clone、清理可重建
cache、关闭非必要 build；只有“单一 Codex Runtime 仍会 OOM、越过磁盘保留量或破坏
既有关键服务”时，才阻止真实 Runtime 启动，其他代码与验证继续。

clean-shell、profile 和有界 pressure 合同可在无真实凭据时立即验证：

```bash
bash implementation-kit/scripts/preflight.sh --check
python3 implementation-kit/tests/test_resource_profile.py
python3 implementation-kit/scripts/resource-pressure-fixture.py
node --test implementation-kit/tests/status-adapter-contract.test.js
```

本机或受限容器 pressure fixture 只能证明脚本合同；不得冒充 OVH 实机
memory/cgroup/port/service 基线。真实启用前仍须在同一获授权 OVH 主机上完成脱敏
preflight 与有界 induced-load snapshot。后者会分配少量内存并写入自动清理的临时
文件，不属于纯只读命令；只有在 Owner 明确授权有界实机压力后才能运行。

CB-010 已于 2026-07-26 完成该首次实机证据：三次 snapshot 选择
`constrained`，8765/8780 与四个拟用路径无冲突；有界 fixture 在无网络、
只读 rootfs、128 MiB memory/swap、32 PID、0.25 CPU 的 ephemeral container
中以 `--evidence-scope=authorized_live_host_container` 运行，16 MiB RAM、
8 MiB temporary disk、100 queue items，OOM-kill delta=0。容器与临时目录已
清理。该历史证据不替代实际激活前的重新 preflight。

### 3.2 Create Service Account and Directories

```bash
sudo useradd --system --create-home --home-dir /var/lib/cyberboss \
  --shell /usr/sbin/nologin cyberboss 2>/dev/null || true

sudo install -d -o root -g root -m 0755 /opt/cyberboss-cloud/releases
sudo install -d -o cyberboss -g cyberboss -m 0750 /var/lib/cyberboss
sudo install -d -o cyberboss -g cyberboss -m 0750 /srv/cyberboss-workspaces
sudo install -d -o root -g cyberboss -m 0750 /etc/cyberboss
sudo install -d -o root -g cyberboss -m 0750 /etc/cyberboss/credentials
```

Secrets use mode `0640` or stricter; Codex/WeChat auth state uses `0600` owned by the service account.

### 3.3 Install Runtime

- Node.js 22+ from an approved/pinned source；
- Git, SQLite CLI, curl, jq, rsync, zstd, ca-certificates；
- Codex CLI exact version verified in Stage 0；
- Claude Code optional and default disabled；
- no global package install without version pin/record。

Verify:

```bash
node --version
codex --version
git --version
sqlite3 --version
```

### 3.4 Codex 认证与Simulator路径

准备受保护目录和命令：

```bash
sudo -u cyberboss -H bash -lc 'codex login --device-auth'
```

认证完成后只检查可读性/权限，不输出内容：

```bash
sudo -u cyberboss -H test -r /var/lib/cyberboss/.codex/auth.json
sudo stat -c '%U %G %a %n' /var/lib/cyberboss/.codex/auth.json
```

若尚未认证：

```text
CB_RUNTIME_PROVIDER=simulator
CB_CODEX_ACTIVATION_STATE=activation_pending
```

Agent继续完成Runtime supervisor、JSON-RPC contract、crash/overload/approval测试、systemd和release；只有真实Codex E2E保持activation_pending。

### 3.5 Install Local Immutable Artifact and Build

```bash
sha256sum -c /var/lib/cyberboss/incoming/cyberboss-<COMMIT>.tar.zst.sha256
sudo install -d -o cyberboss -g cyberboss -m 0750 \
  /opt/cyberboss-cloud/releases/<COMMIT>
sudo -u cyberboss -H tar --extract --zstd \
  --file /var/lib/cyberboss/incoming/cyberboss-<COMMIT>.tar.zst \
  --directory /opt/cyberboss-cloud/releases/<COMMIT>

cd /opt/cyberboss-cloud/releases/<COMMIT>
sudo -u cyberboss -H npm ci
sudo -u cyberboss -H npm test
```

PG-0–PG-5 全部通过前，artifact 必须从本地 commit 确定性构建并传入 OVH，
不得依赖中间 GitHub push。The immutable release directory must not be edited
after deployment. New code means a new local commit and release directory.

### 3.6 Canonical Client and B1 Workspace

```bash
# 安装 Stage 0 已核验 hash 的 no-clone client；不得 clone Private-Database。
sudo install -o root -g cyberboss -m 0750 \
  /var/lib/cyberboss/incoming/private_db_client.py \
  /opt/cyberboss-cloud/shared/private_db_client.py

# 真实激活前只检查 dedicated service-user 的 gh 登录态；缺失时标记
# activation_pending:private_db，不 clone Private-Database，也不阻塞 simulator。
sudo -u cyberboss -H gh auth status

sudo -u cyberboss -H git clone --filter=blob:none \
  https://github.com/LinzeColin/MetaDatabase.git \
  /srv/cyberboss-workspaces/cyberboss
sudo -u cyberboss -H git -C /srv/cyberboss-workspaces/cyberboss \
  sparse-checkout set CyberBoss .github

# 本地开发 commit 通过经校验 git bundle 传入；不是 GitHub 上传。
LOCAL_BRANCH="${CB_LOCAL_BRANCH:?set the validated codex/cyberboss-* branch}"
sudo -u cyberboss -H git -C /srv/cyberboss-workspaces/cyberboss fetch \
  /var/lib/cyberboss/incoming/cyberboss.bundle \
  "$LOCAL_BRANCH:$LOCAL_BRANCH"
sudo -u cyberboss -H git -C /srv/cyberboss-workspaces/cyberboss \
  switch "$LOCAL_BRANCH"
```

Workspace config 必须强制 alias=`cyberboss`、repo=`LinzeColin/MetaDatabase`、
project_subpath=`CyberBoss`、write_globs=`CyberBoss/**`。Run `du -sh`; when
the profile budget is exceeded, reduce the checkout/worktree/cache first. Only
the affected workspace activation is blocked if no safe bounded form fits.

### 3.7 Environment and Workspace Config

Copy examples:

```bash
sudo install -o root -g cyberboss -m 0640 \
  implementation-kit/config/cyberboss.env.example /etc/cyberboss/cyberboss.env
sudo install -o root -g cyberboss -m 0640 \
  implementation-kit/config/workspaces.json.example /etc/cyberboss/workspaces.json
```

Inject the authorised WeChat ID and account-issued secrets only into the referenced root-protected credential files. All non-secret repository, path, domain and storage-prefix values are already fixed; do not rename them during MVP development.

Validate:

```bash
sudo -u cyberboss -H node implementation-kit/tests/validate_config.js \
  /etc/cyberboss/cyberboss.env /etc/cyberboss/workspaces.json
```

### 3.8 Install systemd

```bash
sudo install -o root -g root -m 0644 \
  implementation-kit/systemd/cyberboss-cloud.service \
  /etc/systemd/system/cyberboss-cloud.service

sudo install -o root -g root -m 0644 \
  implementation-kit/systemd/cyberboss-selfheal.service \
  /etc/systemd/system/cyberboss-selfheal.service
sudo install -o root -g root -m 0644 \
  implementation-kit/systemd/cyberboss-selfheal.timer \
  /etc/systemd/system/cyberboss-selfheal.timer

sudo install -o root -g root -m 0644 \
  implementation-kit/systemd/cyberboss-backup.service \
  /etc/systemd/system/cyberboss-backup.service
sudo install -o root -g root -m 0644 \
  implementation-kit/systemd/cyberboss-backup.timer \
  /etc/systemd/system/cyberboss-backup.timer

sudo systemd-analyze verify /etc/systemd/system/cyberboss-*.service \
  /etc/systemd/system/cyberboss-*.timer
sudo systemctl daemon-reload
```

Install units immediately. Start with simulator adapters when QR/auth is pending; switch each real adapter only after its own activation check.

### 3.9 Initialize Database

```bash
sudo -u cyberboss -H bash -c '
  umask 077
  sqlite3 /var/lib/cyberboss/runtime.db \
    < /opt/cyberboss-cloud/current/implementation-kit/sql/runtime-spool.sql
  sqlite3 /var/lib/cyberboss/runtime.db "PRAGMA integrity_check;"
'
```

Expected: `ok`.

### 3.10 WeChat 登录与Simulator路径

真实激活：

```bash
sudo -u cyberboss -H bash -lc 'cd /opt/cyberboss-cloud/current && npm run login'
```

用户只需扫码一次。成功后保护会话目录并运行一条adapter-level文本测试。

未扫码时：

```text
CB_CHANNEL_PROVIDER=simulator
CB_WECHAT_ACTIVATION_STATE=activation_pending
```

所有cursor、durable inbox/outbox、重复消息、send failure和状态测试继续。若账号明确不支持/风控，停止真实微信重试并记录`failed_external`；不得尝试非官方绕过，也不得阻塞其他层。

### 3.11 Offline Self-check

```bash
sudo -u cyberboss -H /opt/cyberboss-cloud/current/implementation-kit/scripts/health-check.sh --offline
sudo -u cyberboss -H npm --prefix /opt/cyberboss-cloud/current test
```

Checks:

- DB schema/integrity；
- config；
- Codex ready on loopback；
- no public Runtime listener；
- Access route not yet required；
- feature flags safe；
- workspace alias；
- secret scan of generated status/template。

### 3.12 Start Staging

```bash
sudo ln -sfn /opt/cyberboss-cloud/releases/<COMMIT> /opt/cyberboss-cloud/current
sudo systemctl start cyberboss-cloud.service
sudo systemctl status cyberboss-cloud.service --no-pager
sudo journalctl -u cyberboss-cloud.service -n 200 --no-pager
```

Do not enable timers until Walking Skeleton and reliability patches pass.

---

## 4. Domain and Cloudflare

### 4.1 DNS

Create proxied record:

```text
cyberboss.linzezhang.com → existing OVH origin/reverse proxy
```

Do not create any record for Codex App Server.

### 4.2 Routes

```text
https://cyberboss.linzezhang.com/                 minimal landing/status summary, Access
https://cyberboss.linzezhang.com/timeline/        Timeline, Access
https://cyberboss.linzezhang.com/status/          detailed status, Access
https://cyberboss.linzezhang.com/healthz           minimal probe according to collector design
https://cyberboss.linzezhang.com/readyz            private/Access
https://cyberboss.linzezhang.com/status/snapshot.json Access service-token only
```

### 4.3 Cloudflare Access

- application type: self-hosted；
- allowed identities: explicitly approved user email/account；
- Google and/or GitHub IdP；
- deny by default；
- detailed status collector uses service token or origin-local fetch；
- Access cookies/session duration chosen according to current status conventions；
- no bypass rule for broad country/IP unless narrowly justified。

### 4.4 Analytics

Enable Cloudflare Web Analytics for page views and unique visitors. Do not send prompt, job ID, Timeline content or user identity as analytics event parameters.

### 4.5 Governed activation adapter

P0.3 的命令入口：

```bash
python3 implementation-kit/scripts/scope_policy.py validate
python3 implementation-kit/scripts/cloudflare_adapter.py plan
python3 implementation-kit/scripts/oci_object_adapter.py plan
```

`cloudflare_adapter.py apply --transport real` 必须读取
`provider-activation.json` 引用的 root-owned slots，并分别验证 Access、
DNS、R2 scope attestation。Access application/policy 成功 reconcile 前不
执行 DNS；重复运行只 reconcile 同一 domain/record/bucket，不创建重复资源。

Cloudflare Web Analytics 当前对 proxied hostname 使用 dashboard automatic
setup，因此 adapter 只输出一项可复核的 `activation_pending` control-plane
动作，不伪造不存在的 API。Analytics 不阻塞 Access/DNS/R2 adapter 测试，也
不得加入 prompt/result/job/thread/微信或用户身份字段。

OCI 使用另一个 adapter。真实 `oci-sdk` backend 需要显式
`--execute-real`、精确 bucket slot 和 bucket/prefix IAM attestation；MVP
不允许 bucket create/delete、object delete/overwrite。没有这些证据时只运行
mock 并报告 `activation_pending`。

当前 P0.3 只读审计确认本机存在可用 Access/DNS/R2/OCI 读取能力，但没有证明
写权限精确范围，故没有执行真实 mutation。此局部 pending 不建立
`waiting_for_credentials` 或全局 block。

---

## 5. `status.linzezhang.com` Integration

### 5.1 Do Not Replace Existing Status System

The existing global page already reports project inventory plus operational
metrics and summaries. CyberBoss adds one adapter/snapshot; it must not deploy
a second monitoring platform or change unrelated projects.

### 5.2 Project Row

The CB-010 read-only observation found this exact `projects[]` contract:

| Field | Value |
|---|---|
| `name` | CyberBoss Cloud |
| `url` | `https://cyberboss.linzezhang.com` |
| `parts` | `["前台", "后台"]` |
| `host` | OVH Singapore VPS-1 |
| `db` | Private-MetaDatabase + SQLite spool |
| `store` | R2 + OCI |
| `deploy` | systemd immutable release |
| `backup` | R2 snapshots → OCI selected copy |
| `agent` | `中` |
| `notify` | `无` until a real notifier is configured |
| `status` | `access` only for fresh healthy/degraded service; otherwise `down` |

All fields are strings except `parts`. The page also accepts `run`, but the
CyberBoss route is Access-protected. The adapter may add private diagnostic
fields, while the required public fields and values above remain stable.

### 5.3 Status Inputs

The global page should consume only `status/snapshot.json` or an equivalent local snapshot with these groups:

- service/version/commit/deployment；
- WeChat poll/send freshness；
- Runtime ready/auth/active job age；
- queue counts/oldest age；
- Private-MetaDatabase object/manifest hash、lag、pending；
- Timeline last write/build/entries；
- R2/OCI age/state；
- CPU/RAM/disk/inode/swap；
- self-heal last result；
- degraded reasons。

### 5.4 Freshness and Severity

- snapshot generated every 60 seconds or faster；
- global page must not show a snapshot older than 2 minutes as healthy；
- `unknown` and `not_verified` are not green；
- required component severity rolls up to project severity；
- warning thresholds match architecture values；
- status must explicitly identify `private_db_sync_pending`, `wechat_poll_stale`, `runtime_auth_invalid`, `disk_pressure`, `backup_stale`, etc。

### 5.5 Status Privacy

Forbidden:

- prompt/result；
- WeChat ID/nickname/context token；
- Codex auth/token；
- private GitHub URL if not needed；
- absolute server path；
- job/thread ID；
- private filenames；
- raw error stack with secrets。

Use counts, age, state, public commit prefix and redacted error class.

---

## 6. Service Commands

### 6.1 Normal Status

```bash
sudo systemctl status cyberboss-cloud.service --no-pager
sudo /opt/cyberboss-cloud/current/implementation-kit/scripts/health-check.sh
curl -fsS http://127.0.0.1:8780/healthz
curl -fsS http://127.0.0.1:8780/readyz
```

### 6.2 Logs

```bash
sudo journalctl -u cyberboss-cloud.service --since '30 minutes ago' --no-pager
sudo journalctl -u cyberboss-selfheal.service -n 100 --no-pager
sudo journalctl -u cyberboss-backup.service -n 100 --no-pager
```

Never run `set -x` in a shell that loads secrets. Redact before sharing logs.

### 6.3 Start / Stop / Restart

```bash
sudo systemctl start cyberboss-cloud.service
sudo systemctl stop cyberboss-cloud.service
sudo systemctl restart cyberboss-cloud.service
```

A stop must leave SQLite/outbox/sync spool intact. `KillMode=control-group` must terminate bridge and App Server together.

### 6.4 Enable 7×24 After Deterministic Gates

```bash
sudo systemctl enable --now cyberboss-cloud.service
sudo systemctl enable --now cyberboss-selfheal.timer
sudo systemctl enable --now cyberboss-backup.timer
```

Do not enable before PG-2/PG-3.

---

## 7. User Commands and UX

### 7.1 First Response Contract

Every accepted ordinary task should receive:

```text
已接收 · job_<short-id>
项目：<workspace-alias>
状态：排队中 / 正在执行
查看：/status
停止：/stop
```

The exact Chinese copy can be refined, but it must not claim execution before dispatch.

### 7.2 Core Commands

| Command | Behavior |
|---|---|
| `/status` | compact conclusion first: healthy/degraded, current job, queue, Runtime, sync, backup/resource warnings |
| `/bind <alias>` | switch allowlisted logical workspace only |
| `/new` | new Runtime thread within current workspace |
| `/stop` | request current turn cancellation and return truthful result |
| `/timeline` | return protected Timeline URL and freshness |
| `/model` | show selected Runtime/model; no arbitrary unverified model switching |
| `/help` | only current supported commands, no future placeholders |

### 7.3 Error Replies

Errors are short, truthful and actionable:

```text
未执行 · job_xxx
原因：服务器磁盘进入保护阈值（91%）
系统行为：已停止接收新的修改任务，现有事实未删除
下一步：查看 /status；空间恢复到 82% 以下后自动重新评估
```

Do not expose stack traces or secrets.

---

## 8. Self-heal Runbook

### 8.1 Allowed Automatic Actions

- restart the one systemd process group after crash；
- reconnect WeChat adapter；
- restart Codex child when no ambiguous mutation is active；
- retry outbox/canonical/R2 operations within budget；
- pause Timeline build；
- rotate logs；
- remove expired verified temporary files；
- clean completed worktrees and old immutable releases after retention；
- transition readiness/degraded state。

### 8.2 Forbidden Automatic Actions

- modify source code/config policy；
- rotate or print credentials；
- rescan WeChat QR；
- run Codex/Claude to diagnose itself；
- delete unsynced inbox/outbox/canonical spool；
- force push/rewrite Git history；
- expose ports/disable Access；
- upgrade paid infrastructure；
- automatically replay an ambiguous mutation；
- disable security controls。

### 8.3 Loop Prevention

- cooldown between equivalent actions；
- max 3 restarts/10min；
- max 5 send retries/15min default；
- max one cleanup pass/15min；
- action counter and last result in status；
- repeated failure transitions to `STOPPED` or `DEGRADED` and alerts operator。

---

## 9. Backup Operations

### 9.1 Manual Backup

```bash
sudo systemctl start cyberboss-backup.service
sudo journalctl -u cyberboss-backup.service -n 200 --no-pager
```

Or:

```bash
sudo -u cyberboss -H /opt/cyberboss-cloud/current/implementation-kit/scripts/backup-runtime.sh
```

Expected result:

```text
BACKUP=PASS
SNAPSHOT_ID=<id>
LOCAL_SHA256=<sha>
R2_SHA256=<sha>
CANONICAL_OBJECT_SHA256=<sha>
LOCAL_CLEANUP=performed|retained
OCI_STATE=healthy|activation_pending|failed
```

No secret values.

### 9.2 Runtime Backup Policy（不是发布等待条件）

MVP starting policy:

- SQLite snapshot: daily and before release；
- Private-MetaDatabase canonical: terminal event batch within 60s target；
- R2 uses lifecycle tags/retention classes; exact periods are runtime policy and are tested with virtual dates；
- OCI copies selected immutable recovery points when configured；
- logs use a size-bounded local ring; selected incident/release bundles go to R2；
- adjust only after actual size/usage measurements。

### 9.3 R2 Lifecycle

Use lifecycle rules for ordinary snapshots, but protect selected release/restore points with an explicit retention/lock policy where appropriate. Verify interaction between lifecycle and bucket lock before relying on it. R2 Standard is preferred initially for small/frequently verified snapshots; do not move immediately to an infrequent-access class if retrieval/minimum-duration costs would exceed savings.

### 9.4 OCI

OCI is not on the hot path. A failed OCI copy degrades backup resilience but must not
block message execution when Private-MetaDatabase and R2 are healthy. Status must show
age/failure, and the future roadmap includes periodic restore proof.

---

## 10. Restore Operations

### 10.1 Safe Restore Command

```bash
sudo -u cyberboss -H \
  /opt/cyberboss-cloud/current/implementation-kit/scripts/restore-drill.sh \
  --snapshot <R2_OBJECT_KEY> \
  --target /var/lib/cyberboss/restore-tests/<ID> \
  --network-disabled
```

The default is an isolated drill, never in-place overwrite.

### 10.2 Promote Restored State

Promotion requires human/design-authority approval because it can replace live state:

1. Stop new jobs；
2. wait/resolve active job；
3. take current emergency snapshot；
4. verify restored DB integrity；
5. compare canonical event/job/timeline set；
6. verify code/schema compatibility；
7. rename/swap state atomically；
8. start with outbound send disabled；
9. health/read-only checks；
10. enable send only after duplicate/outbox review。

### 10.3 Restore Failures

- Hash mismatch: reject object；
- SQLite integrity failure: reject；
- missing canonical events: do not promote；
- outbox ambiguity: keep outbound disabled, review；
- incompatible schema: deploy matching release or migrate in isolation；
- missing auth: reauthenticate rather than restoring plaintext credential from an unsafe source。

---

## 11. Release and Rollback Operations

### 11.1 Deploy

```bash
sudo -u cyberboss -H /opt/cyberboss-cloud/current/implementation-kit/scripts/deploy-release.sh \
  --commit <GIT_SHA>
```

The script must:

- verify and unpack the exact local artifact/commit；
- install/test in new release directory；
- snapshot；
- offline check；
- set `previous`；
- atomically switch；
- restart；
- run health/ready/port tests；
- automatically revert only for clear startup/readiness failures。

### 11.2 Rollback

```bash
sudo /opt/cyberboss-cloud/current/implementation-kit/scripts/rollback-release.sh
```

Expected under five minutes. Never delete the failed release or DB before evidence is captured.

### 11.3 Code vs Canonical Data

- application code: local branch → local CI → PG-0–PG-5；then one final
  push → PR/review/CI → merge；
- canonical data: deterministic content-addressed batch through
  `private_db_client.py ingest`；
- no intermediate phase push/PR/tag；final merge 后不得遗留本任务 branch/PR/worktree；
- never auto-push arbitrary Runtime code changes to application `main`；
- generated canonical objects must be bounded, hashed and identifiable。

---

## 12. Incident Runbooks

### IR-01 — WeChat Poll Stale

Symptoms:

- service process healthy；
- `last_poll_success` older than threshold；
- no new inbound messages。

Actions:

1. inspect adapter error class；
2. verify network/DNS；
3. controlled adapter/service restart；
4. do not run multiple bridges；
5. if auth invalid, stop and request one QR login；
6. if account risk/unsupported, stop permanently and record external gate。

### IR-02 — Results Not Reaching WeChat

1. inspect outbox pending/attempt/error；
2. distinguish transient provider/network from terminal context/auth；
3. do not rerun Codex task just because send failed；
4. retry same durable outbox；
5. if delivery ambiguous, inform user/status and avoid generating a second result；
6. retain result hash/canonical state。

### IR-03 — Duplicate Replies

1. stop service if duplicate active；
2. list process/cgroup owners；
3. verify singleton lock/boot ID；
4. inspect same source/outbox IDs；
5. preserve evidence；
6. kill entire cgroup and restart one owner；
7. do not delete dedupe rows。

### IR-04 — Runtime Auth Invalid

1. set readiness false；
2. hold queued jobs；
3. do not attempt repeated login；
4. user runs one device-auth；
5. test read-only local Runtime；
6. resume queue only after ready。

### IR-05 — Disk Pressure

At 80% warning:

- identify releases/worktrees/cache/logs/tmp；
- upload/verify snapshots；
- safe cleanup only。

At 85% degraded:

- stop Timeline build/backup temp growth；
- reject new heavy jobs。

At 90%+:

- stop mutation dispatch；
- preserve inbox/outbox/sync；
- never delete unsynced data；
- upgrade/cleanup decision if no safe space。

### IR-06 — Private-MetaDatabase Canonical Lag

1. jobs remain durable locally；
2. status `sync_pending`；
3. inspect client auth/network/manifest conflict；
4. retry stable content-addressed event batch；
5. same ID/different hash = integrity incident, stop mutation；
6. backlog beyond threshold stops new mutation jobs；
7. never clone Private-Database or overwrite/rewrite events。

### IR-07 — Suspected Secret Exposure

1. stop affected egress/service；
2. revoke/rotate secret；
3. preserve incident evidence without repeating secret；
4. scan code history, candidate Private-MetaDatabase objects, logs, Timeline, status, R2；
5. purge according to provider/Git incident procedure；
6. re-auth and retest；
7. release blocked until root cause fixed。

### IR-08 — OVH Host Loss

1. do not assume local spool is available；
2. provision clean host；
3. unpack exact code artifact and fetch canonical objects with client get/list/verify；
4. restore R2 snapshot in isolation；
5. verify integrity and event set；
6. reauthenticate Codex/WeChat if needed；
7. update origin/DNS；
8. canary before enabling mutation；
9. record RPO/RTO and missing un-synced window honestly。

---

## 13. 24 小时实施切线（并行泳道，不是等待计划）

24 小时只定义最终截止，不要求任何任务运行到某个真实时刻。开发Agent按依赖并行推进：

| Lane | 负责内容 | 可立即完成的退出证据 |
|---|---|---|
| A — Fixed Source/Core | pin SHA、固定本地 source bundle、变更地图、cloud path、Codex loopback、simulators | baseline + simulator Walking Skeleton |
| B — Reliability | SQLite、cursor ordering、idempotency、outbox、singleton | crash-cut/replay/restart/fault报告 |
| C — Data/Recovery | Private-MetaDatabase no-clone canonical、R2/OCI adapter、backup/restore/reconcile | set diff=0 + 20 restore循环 |
| D — Experience/Ops | Timeline/search、cyberboss域名、Access、status adapter、systemd | contract/Access/status/deploy证据 |
| E — Assurance/Release | 软件/模型双流水线、安全、资源、Blue-Green、Canary | request-count Canary + rollback |

规则：

- 任一外部adapter未激活，使用simulator完成该Lane其余工作并继续；
- 任一Lane提前完成，转入故障注入、代码修复和Traceability，不增加out-of-scope功能；
- 发布Gate只看Oracle，不看经过了多少小时；
- 最终激活窗口一次性执行扫码、device auth、凭据和DNS切换；
- 不存在24小时burn-in、7天/30天Soak或观察后才能交付。

---

## 14. Handover Checklist

### Deployed Facts

- [ ] application repo/subpath and local commit；
- [ ] historical source SHAs and fixed bundle hashes；
- [ ] active/previous release paths；
- [ ] Private-MetaDatabase area/domain and last object/manifest hash；
- [ ] workspace aliases；
- [ ] feature flags；
- [ ] Node/Codex/runtime versions；
- [ ] domain/Access routes；
- [ ] R2 prefix/last snapshot；
- [ ] OCI state；
- [ ] status integration freshness。

### Verified

- [ ] true E2E with Mac offline；
- [ ] durable-before-cursor kill points；
- [ ] duplicate replay；
- [ ] outbox retry；
- [ ] singleton；
- [ ] restart/reboot；
- [ ] canonical outage/catch-up；
- [ ] Timeline rebuild/search/Access；
- [ ] status DLP/fault matrix；
- [ ] R2 restore；
- [ ] model golden/red-team；
- [ ] security/license；
- [ ] resource guard；
- [ ] rollback。

### Activation Pending / Out of Scope

- [ ] WeChat real adapter if QR/account not activated；
- [ ] Codex real adapter if device auth not activated；
- [ ] Private-Database/Cloudflare/R2/OCI real adapter if scoped credentials not injected；
- [ ] final GitHub publication if PG-0–PG-5 passed but scoped code credential unavailable；
- [ ] attachments/multimedia；
- [ ] Claude Runtime unless parity eval passed；
- [ ] multi-user/multi-node；
- [ ] commercial SLA。

不得添加任何“等待7天/30天后再判断”的交接项。

### Final Report Format

```text
Final state: MVP_LIVE | MVP_DEGRADED | ACTIVATION_PENDING | STOPPED | NOT_VERIFIED
Deployed commit:
Canonical object SHA-256:
Previous rollback commit:
Adapter states (verified/activation_pending/failed):
Real E2E:
Pass gates:
Failed/not verified:
Current risks:
Current resource headroom:
Latest R2 snapshot:
OCI state:
Start command:
Stop command:
Diagnose command:
Rollback command:
Next phase source: separate Phase 2/3 roadmap
```

---

## 15. Definition of Operational Readiness

CyberBoss Cloud is operationally ready for MVP only when:

- user can understand status without reading source code；
- a failed send is distinct from failed execution；
- process alive is distinct from channel/runtime healthy；
- no ordinary incident requires manually editing SQLite；
- every cleanup action is bounded and recoverable；
- no self-heal action invokes Agent/LLM；
- start/stop/restart do not create duplicate bridges；
- restore and rollback have been exercised, not merely documented；
- existing `status.linzezhang.com` remains the primary global entry；
- all limitations are visible and no feature is marked green without evidence；
- no real-time Soak, fixed-sleep readiness or credential-wait task remains；
- request-count Canary and accelerated fault matrix have been executed。
