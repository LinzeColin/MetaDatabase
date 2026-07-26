# Run Contract — P1.3 / CB-120 Controlled Workspace and No-Clone Client

## 1. Goal

本 Run 只执行 Task DAG 节点 `P1.3 / CB-120`：

> Install fixed source bundle, no-clone canonical client and bounded workspace.

在 CB-100/CB-110 已验证的同一授权 OVH 主机上，安装绑定精确本地
implementation commit 的 CyberBoss candidate release；建立唯一
`cyberboss` sparse MetaDatabase workspace、root 控制的 alias/realpath 门、
独立 code/data OS identity、固定 no-clone Private-Database client 和可执行
workspace/cache 预算。

本 Run 不切换 `current`，不 enable/start 业务 service，不执行真实
Private-MetaDatabase operation，不激活微信/Codex/provider，不进入
`P1.4 / CB-130`。

## 2. Frozen input and minimum scope

- 输入基线：
  `bacb20147b1f9971b8d47c578599fd3494bed5c3`；
- 依赖：`CB-100=passed`、`CB-020=passed`，`CB-110=passed`；
  `CB-120` 与之后所有 Task、`PG-1`–`PG-5` 均未通过；
- 唯一权威：
  `04_TASK_DAG_EXECUTION_PACK.yaml` 的 `CB-120`、
  `02_PRD_ACCEPTANCE_CONTRACT.md` 的 `AC-013`、`AC-014`、`AC-064`；
- 不创建新 repo；code canonical identity 固定为
  `LinzeColin/MetaDatabase/CyberBoss`；
- 固定 source artifact 由本地已有 worktree 的精确 commit 产生，包含完整
  Corresponding Source、原许可证、provenance、修改记录和未解决许可证冲突；
- 合规按保守表达
  `AGPL-3.0-only AND GPL-3.0-only` 执行，
  `upstream_clarification_received=false`；
- MetaDatabase workspace 固定
  `/srv/cyberboss-workspaces/cyberboss`，唯一 alias 为 `cyberboss`；
- workspace 只通过本地 artifact seed 创建：
  `--filter=blob:none`，sparse paths 为 `CyberBoss` 与 `.github`；
  `.github` 和仓根集成面只读，code write scope 仅 `CyberBoss/**`；
- workspace soft max `4 GiB`，absolute stop `8 GiB`，host reserve
  `4 GiB`；清理只允许普通 `git worktree prune`、`git gc` 和有界 cache
  清理，禁止 `git gc --prune=now`；
- code identity 为 `cyberboss`，data identity 为 `cyberboss-data`：
  - code identity 可写 `CyberBoss/**` 和自己的 Git metadata，但不可读取/
    执行 canonical data client；
  - data identity 可执行受控 wrapper，但不可修改 workspace；
  - data credential root 为
    `/var/lib/cyberboss-data/.config/gh`，本 Run 保持空且
    `activation_pending`；
- canonical client 只从本机既有 KMOS 真源复制：
  `KMDatabase/machine/tools/private_db_client.py`，
  SHA-256
  `8a26302c98a470e75122fbf01ff1d1a23381ccf5db5f26df9ed5f9e59e5c9ffa`；
- wrapper 唯一开放 `ingest/get/list/verify`，显式拒绝
  `clone/put/delete`，本 Run 只运行 plan-only；
- GitHub CLI 固定官方 Linux amd64 `2.96.0` archive，SHA-256
  `83d5c2ccad5498f58bf6368acb1ab32588cf43ab3a4b1c301bf36328b1c8bd60`；
- target 地址只通过受保护本地部署记录解析，必须匹配
  `target_id_sha256=7865f743d174`，使用 strict-known-host、key-only
  BatchMode；地址与 credential 内容不得落库或输出。

## 3. Non-goals

- 不执行 `CB-130` 或任何后续 Task/Pass Gate；
- 不 push，不创建 PR/tag/release，不运行 GitHub CI；
- 不创建、clone 或本地缓存 `LinzeColin/Private-Database`；
- 不执行 `gh auth login`、真实 `gh api`、data ingest/get/list/verify；
- 不执行微信扫码、Codex device auth、authenticated turn 或 provider write；
- 不切换 `current`/`previous`，不 enable/start
  `cyberboss-cloud.service`，不创建公网 listener/route；
- 不修改 vendor 原始源码、许可证、CB-000–CB-110/PG-0 历史 evidence、
  Task DAG、PRD、Roadmap 或 Acceptance；
- 不删除 vendor 原始 README 中的历史来源文字；其保留是 Corresponding
  Source 义务，不构成当前 install/runtime/support/sync/endorsement route；
- 不把 simulator、plan-only、candidate install 或未认证状态称为真实激活。

## 4. Allowed repository modifications

- `CyberBoss/app/README*.md`
- `CyberBoss/app/package.json`
- `CyberBoss/app/scripts/normalize-sticker-gif.js`
- `CyberBoss/app/src/core/app.js`
- `CyberBoss/app/src/core/command-registry.js`
- `CyberBoss/app/src/core/config.js`
- `CyberBoss/app/src/core/workspace-registry.js`
- `CyberBoss/app/src/index.js`
- `CyberBoss/app/src/services/system-message-service.js`
- `CyberBoss/app/test/claudecode-approval.test.js`
- `CyberBoss/app/test/sticker-service.test.js`
- `CyberBoss/app/test/turn-gate-store.test.js`
- `CyberBoss/app/test/upstream-separation.test.js`
- `CyberBoss/app/test/workspace-scope.test.js`
- `CyberBoss/docs/governance/RUN_CONTRACT_P1_3_CB_120.md`
- `CyberBoss/docs/product_design/v0.0.0.4/{MANIFEST.sha256,implementation-kit/**}`
  中 CB-120 直接相关配置、脚本、测试、README、report 与 manifest；
- `CyberBoss/machine/facts/post-baseline-change-ledger.json`
- `CyberBoss/tests/cloud-controlled-workspace.test.js`
- `CyberBoss/scripts/validate_cb120.py`
- `CyberBoss/docs/evidence/CB-120/**`
- closure 时的
  `CyberBoss/machine/facts/task_state.json`、`CyberBoss/README.md`、
  `CyberBoss/HANDOFF.md`、`CyberBoss/CHANGELOG.md`。

其他路径不得修改，尤其是 `CyberBoss/vendor/**`、历史 evidence 与母仓其他项目。

## 5. Local validation

```bash
bash -n \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-controlled-workspace.sh \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/workspace-maintenance.sh
python3 -m py_compile \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-controlled-workspace-artifacts.py \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/private_db_client_safe.py \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/workspace_budget.py
node --test CyberBoss/tests/cloud-controlled-workspace.test.js
python3 \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/test_identity_scope.py
python3 \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/test_workspace_budget.py
cd CyberBoss/app && npm run check && npm test
python3 CyberBoss/scripts/validate_cb120.py --prepare
```

实现 commit 后，artifact builder 必须从 clean worktree 构建：

- commit-bound `CyberBoss` source archive；
- 无本机路径的 partial bare seed；
- exact canonical client；
- exact official GitHub CLI archive；
- hashes 与 manifest；
- `remote_publication=none`。

## 6. Authorized target acceptance

1. fresh read-only preflight 重验 target hash、key-only sudo、service
   disabled/inactive、current pointer、identity/path collision 和 disk reserve；
2. installer `--check` 证明 persistent writes/live commands 均为 false；
3. 只把 exact artifact set 放入
   `/var/lib/cyberboss/incoming/cb120-<commit>`；
4. 运行两次 `--apply` 和一次 `--verify`，三次均绑定同一 implementation
   commit，第二次必须 idempotent；
5. candidate release：
   - source/archive/tree/hash/许可证/冲突/修改 ledger 完整；
   - `npm ci --ignore-scripts`、App check/full test 通过；
   - root-owned、group-readable、不可写；
   - `current`、service、Runtime、listener 均不变；
6. sparse workspace：
   - exact branch/commit；
   - origin 只指向本地 immutable seed，无 GitHub/upstream remote；
   - promisor/filter 为 `blob:none`；
   - sparse list 精确为 `.github`、`CyberBoss`；
   - status clean，registry root canonical 且非 symlink；
7. AC-013/014：
   - `/bind cyberboss` 通过；
   - `/bind /etc`、未知 alias、symlink escape 均拒绝；
   - 拒绝前后 filesystem digest 相同；
8. identity negative：
   - code identity 不可读取/执行 data client；
   - data identity 不可写 code workspace；
   - wrapper plan-only 通过，真实 data calls=0；
   - credential file absent，只读 metadata，content reads=0；
9. budget：
   - live `du`/script state 为 `recover`；
   - deterministic guard/protect/stop/recover ladder 通过；
   - 在同一授权 host 的有限 transient cgroup 内立即执行已有
     resource-pressure fixture，无 OOM、无真实时间 soak；
10. acceptance 后删除 incoming/transient artifacts，确认 process/listener=0、
    current/service 不变。

## 7. Risks and rollback

- **Sparse seed缺 blob：** cone mode 还会 checkout 仓根 blob；builder 必须同时
  hydrate `CyberBoss`、`.github` 与仓根 blob，再在禁止 lazy fetch 下逐一验证。
- **source filter 被本地 upload-pack 忽略：** builder 显式使用
  `uploadpack.allowFilter=true`，并验收 promisor/filter config。
- **path escape：** config、workspace root 和 archive 均拒绝 symlink/
  absolute/traversal；Runtime dispatch 前再次校验 realpath。
- **身份串权：** path owner/mode 与不同 primary group 双重隔离；发现 code
  可执行 data client 或 data 可写 workspace 立即停止。
- **disk pressure：** workspace 超过 8 GiB 立即 stop；低于 host reserve 进入
  protect，不安装后续内容。
- **supply-chain drift：** client/gh/source/seed 任一 hash、version、tree 或
  archive path 不符即停止，不解包未校验内容。
- **rollback：** 只移除本 Run 新建且 commit/hash/owner/path 精确匹配的
  candidate release、workspace、seed、gh version、data identity files；
  非敏感被替换配置从 root-only CB-120 backup 恢复。不得移动既有 current、
  删除 credential、回滚 CB-100/CB-110 toolchain 或使用
  `git gc --prune=now`。

## 8. Stop conditions

- target identity/known-host/sudo/machine 与已通过证据不一致；
- service unexpectedly active/enabled，current 或既有路径出现未知 drift；
- workspace >8 GiB、host reserve 不足或 pressure 出现 OOM；
- 无法把 workspace canonical realpath 限制在
  `/srv/cyberboss-workspaces`；
- 无法隔离 code/data identity 或 credential path；
- source、client、gh、seed hash/tree/version 不符；
- apply/verify 会 clone Private-Database、切换 current、启动 Runtime、写
  provider/data、公开 listener 或修改其他项目；
- 任何 credential content 被读取、输出、复制或 commit；
- 无法形成 exact-commit、idempotent、可回滚证据。

## 9. Acceptance

`CB-120` 仅在以下全部成立时为 `passed`：

1. 依赖通过且只有 CB-120 改变 task state；
2. AC-013：非 allowlisted/escape 全拒绝且 filesystem 不变；
3. AC-014：`/bind cyberboss` 通过，绝对路径与未知 alias 拒绝；
4. AC-064：live budget recover，guard/protect/stop/recover 与有限 cgroup
   pressure Oracle 正确，无 OOM；
5. exact sparse commit/filter/path/remote/clean evidence 通过；
6. candidate source、原许可证、严格双许可证处理、修改 ledger、冲突记录完整，
   不声称上游澄清；
7. code/data identity 和 credential negative tests 通过；
8. canonical client/gh exact hash/version，通过 plan-only，真实 data writes=0；
9. 二次 apply idempotent，current/service/Runtime/listener/provider 均不变；
10. local/full/global validators 通过，remote Git publication 仍为 none；
11. CB-130 与之后任务、PG-1–PG-5 保持 `not_started`。
