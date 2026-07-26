# Run Contract — P1.1 / CB-100 Host Layout and systemd Walking Skeleton

## 1. Goal

执行 Task DAG 的唯一节点 `P1.1 / CB-100`：

> Apply supplied lightweight host layout and systemd walking skeleton.

在 CB-010 已验证的同一授权 OVH 主机上创建专用非 root `cyberboss` 身份、
受限目录、immutable `releases/<sha>` 与原子 `current` symlink，安装并验证
主 `cyberboss-cloud.service`，但保持 unit disabled/inactive，不启动真实
Runtime、不暴露网络。以可执行证据满足 `AC-044` 与本节点可归属的
`AC-067` host-layout/runbook 边界。

本 Run 不得顺带执行 `P1.2 / CB-110`。

## 2. Frozen input and minimum scope

- 输入基线：
  `cc00d057ae096e0eccb88c52f7b5f85a10e18a3a`；
- `PG-0=passed`、`CB-040=passed`，所有 `CB-100` 之后节点仍
  `not_started`；
- 以 DAG 中 `CB-100` 的 title/inputs/outputs/actions/verification/
  risks/rollback/stop conditions 和 `AC-044`、`AC-067` 为唯一任务权威；
- 修正 HANDOFF 中把 CB-100 错写为 PostgreSQL migration 的历史描述；
  TaskPack 明确排除 PostgreSQL，本 Run 不创建数据库 schema/migration；
- 复用并加强 supplied `install-layout.sh`、`verify-installation.sh` 与
  `cyberboss-cloud.service`，不另建部署框架；
- 先形成已验证的本地 implementation commit，以该精确 commit SHA 作为
  immutable release ID，再执行目标主机 apply；避免部署不可追溯的
  uncommitted source；
- 目标解析只使用受保护本地部署记录，必须匹配 CB-010 的
  `target_id_sha256=7865f743d174`，并使用 strict-known-host、
  key-only BatchMode；
- 真实目标写入仅限：
  `/opt/cyberboss-cloud`、`/var/lib/cyberboss`、
  `/srv/cyberboss-workspaces`、`/etc/cyberboss`、
  `/etc/systemd/system/cyberboss-cloud.service`、该 unit 的资源 drop-in
  和 CyberBoss 独立 journald namespace 配置；验收期间另允许创建
  `/run/systemd/system/cyberboss-cloud.service.d/90-cb100-acceptance.conf`
  这一份 ephemeral restart override，验收结束必须删除并
  `daemon-reload`；
- 为传输精确 implementation commit，另允许一个
  `/tmp/cyberboss-cb100.XXXXXXXX` 模式的 `0700` caller-owned ephemeral staging
  directory；只接收该 commit 的 `implementation-kit` archive，退出时
  必须清除；
- 只安装主 cloud unit。backup/status/self-heal services/timers 属于后续
  Task，不在 CB-100 安装或启用；
- 运行 deterministic 100× crash/restart、100× concurrent singleton
  contention、permission negative tests、idempotent second apply、unit
  verify 与 no-listener checks；
- 输出紧凑脱敏证据，不保存目标地址、credential、private key、原始
  journal、完整 `/etc`、进程 argv 或其他项目配置。

## 3. Non-goals

- 不执行 `CB-110` 或安装/升级 Node、Codex CLI、Claude Code；
- 不安装固定 App/source bundle、dependencies、SQLite Runtime 或
  `private_db_client.py`；这些由后续节点完成；
- 不启动或 enable `cyberboss-cloud.service`，不运行真实 WeChat/Codex
  adapter，不形成 Runtime/HTTP listener；
- 不安装或启用 backup/status/self-heal unit/timer；
- 不创建 Cloudflare Access/DNS/R2、OCI object、Status row 或
  Private-MetaDatabase 对象；
- 不读取、打印、复制、提交 credential/session/private-key value；
- 不创建 repository、remote、submodule、Git URL dependency 或 upstream
  relationship；
- 不修改 Task DAG、PRD、Roadmap、Acceptance、fixed source bundle 或
  CB-000–PG-0 历史 evidence；本节点明确实现
  `implementation-kit`，其内容 manifest 必须随实际改动重建；
- 不 push，不创建 PR/tag/release，不运行 GitHub CI；
- 不把 staging mechanics、simulator 或 disabled unit 称为已上线 Runtime。

## 4. Inputs to inspect

- `04_TASK_DAG_EXECUTION_PACK.yaml` 的 `CB-100`
- `02_PRD_ACCEPTANCE_CONTRACT.md` 的 `AC-044`、`AC-067`
- `12_CURRENT_ROADMAP.md` 的 S1/PG-1
- `docs/evidence/CB-010/**`
- `docs/evidence/CB-040/implementation-plan.json`
- `docs/evidence/PG-0/**`
- `implementation-kit/scripts/install-layout.sh`
- `implementation-kit/scripts/verify-installation.sh`
- `implementation-kit/scripts/preflight.sh`
- `implementation-kit/scripts/select-resource-profile.sh`
- `implementation-kit/systemd/cyberboss-cloud.service`
- `implementation-kit/config/cyberboss.env.example`
- `machine/facts/task_state.json`
- 受保护本地 OVH deployment identity/baseline/known-host records（值不落库）

## 5. Allowed repository modifications

- `CyberBoss/docs/governance/RUN_CONTRACT_P1_1_CB_100.md`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-layout.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/verify-installation.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/systemd/cyberboss-cloud.service`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss-journald.conf`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256`
- `CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256`
- `CyberBoss/tests/cloud-install-layout.test.js`
- `CyberBoss/scripts/validate_cb100.py`
- `CyberBoss/docs/evidence/CB-100/**`
- `CyberBoss/machine/facts/task_state.json`
- `CyberBoss/README.md`
- `CyberBoss/HANDOFF.md`
- `CyberBoss/CHANGELOG.md`

除以上路径外不得修改；尤其禁止修改 App source、vendor、fixed source、
Task DAG/PRD/Roadmap/Acceptance、CB-000–PG-0 evidence、母仓根文件和其他
项目。

## 6. Validation

### Local implementation boundary

```bash
bash -n \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-layout.sh \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/verify-installation.sh
node --test CyberBoss/tests/cloud-install-layout.test.js
cd CyberBoss/app && npm run check && npm test
python3 CyberBoss/scripts/validate_cb100.py --prepare
```

### Authorized OVH acceptance

- rerun immediate live preflight and require activation-safe/non-protect;
- dry-run/check before apply;
- apply the exact committed scripts/templates twice;
- verify exact user/group/mode/path/symlink/release identity;
- `systemd-analyze verify` the installed unit and drop-in;
- prove unit `disabled` and `inactive`;
- prove main unit `User=cyberboss`, `KillMode=control-group`, bounded restart,
  writable-path allowlist and per-project journal namespace/limits;
- perform 100 actual transient-process crash/restart cycles under
  `User=cyberboss`, without fixed sleep or LLM call;
- hold one `flock` owner and reject 100 competing acquisitions, then prove
  one clean acquisition after release;
- prove the service identity cannot read credential directory/config secrets,
  modify `/etc/cyberboss`, immutable release or unrelated paths, while it can
  write its allowed state/workspace paths;
- prove 8765/8780 listener count remains zero and no route/service outside the
  allowlist changes.

### Closure

```bash
python3 CyberBoss/scripts/validate_cb100.py
python3 CyberBoss/scripts/validate_cb000.py
python3 CyberBoss/scripts/validate_prestage0.py
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_task_dag.py \
  CyberBoss/docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_traceability.py \
  CyberBoss/docs/product_design/v0.0.0.4
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_no_wait.py \
  CyberBoss/docs/product_design/v0.0.0.4
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_taskpack.py \
  CyberBoss/docs/product_design/v0.0.0.4
git diff --check
```

## 7. Risks and rollback

- **Shared-host collision:** apply 前重新核验 host identity、资源、路径、unit、
  listeners；任何非本 Run CyberBoss state 或不明 ownership 均停止。
- **Root Runtime:** install 需要 sudo，但主 service 必须固定
  `User=cyberboss`；若应用进程需要 root，立即停止并回滚。
- **Over-broad write/read:** service 仅能写 state/workspace/明确 shared
  paths；credential directory 不授予 service user 读取权限。
- **Release drift:** release ID 必须是本地 implementation commit 的完整 SHA，
  existing release 只允许 exact idempotent match，禁止覆盖。
- **Restart impact:** AC-044 仅短暂启动已安装主 unit 中随本 release
  固定的无网络 staging probe，并用 `/run/systemd/system` 下的 ephemeral
  override 加速确定性 restart；不启动真实 Runtime、不触碰其他 unit；
  完成后停止 unit、删除 override 并 `daemon-reload`。
- **Rollback:** disable/stop 新 unit，恢复 apply 前 symlink/config snapshot，
  删除本 Run 新建且已验证为空的目录；不删除既有文件，不修改其他服务。

## 8. Stop conditions

- 目标 hash、known-host、key-only identity、sudo 或 CB-010 host identity 不一致；
- fresh preflight 为 protect/hazard、端口/路径已有不明占用或资源不足；
- unit 需要 root Runtime、无法限制单 owner、无法通过 systemd verify；
- permission negative tests、100× restart、100× singleton 任一失败；
- apply 会修改无关服务、全局 journald 策略、现有路由或不明已有数据；
- 必须读取 secret value、公开网络、安装后续 Runtime dependency 或进入
  `CB-110` 才能通过；
- 无法形成可回滚、可重复、精确 commit-bound 的 installation。

## 9. Acceptance

`CB-100` 仅在以下全部成立时为 `passed`：

1. `CB-040` 与 `PG-0` 已通过，`CB-110` 及所有后续节点仍
   `not_started`；
2. authorized target 精确匹配 CB-010，fresh preflight 允许 bounded apply；
3. dedicated user/group 为非 root、nologin、唯一 owner；
4. approved directories、owner/group/mode 与 credential denial 全部通过；
5. immutable `releases/<implementation-commit>` 与 atomic `current` symlink
   存在，二次 apply 为 exact idempotent；
6. 仅主 cloud unit 被安装，且 disabled/inactive，无真实 Runtime；
7. unit 的 user/group、working directory、env file、KillMode、restart
   limits、resource limits、sandbox 与 writable paths 通过 verify；
8. CyberBoss 独立 journal namespace/rate/size limits 与 app log cap 已配置，
   不修改 shared-host 全局 journal policy；
9. 100 次实际 crash 均由 systemd 恢复，最终 active owner=1，无固定 sleep、
   LLM 或真实 Runtime；
10. singleton lock 在一个 owner 存在时拒绝全部 100 个竞争者，释放后仅一次
    acquisition 成功；
11. 8765/8780 listener、公开 route、外部 provider write、credential
    value/content read均为 0；
12. `AC-044` 与 CB-100 归属的 `AC-067` 可执行证据完整，local/full
    regression/global validators 通过，remote Git publication 仍为空。
