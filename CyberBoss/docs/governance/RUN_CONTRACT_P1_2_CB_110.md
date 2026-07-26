# Run Contract — P1.2 / CB-110 Pinned Cloud Runtime Toolchain

## 1. Goal

执行 Task DAG 的唯一节点 `P1.2 / CB-110`：

> Install and pin Node/Codex plus disabled Claude adapter.

在 CB-100 已验证的同一授权 OVH 主机上，以项目级、不可变、可重复安装方式
部署 Node.js `24.18.0` 与 Codex CLI `0.146.0-alpha.3.1`，准备受保护的
`CODEX_HOME`，验证 SQLite adapter、Codex App Server loopback ready/initialize
协议，并在受控启动入口落实 Claude `feature flag + eval` 双门默认拒绝。

本 Run 不执行设备认证，不安装 Claude Code，不启动 CyberBoss 业务 Runtime，
不进入 `P1.3 / CB-120`。

## 2. Frozen input and minimum scope

- 输入基线：
  `35a8d3716b41922298bc0cbe9aa4ff4b78af0266`；
- `CB-100=passed`、`CB-030=passed`、`PG-0=passed`；
  `CB-110` 与之后所有 Task、`PG-1`–`PG-5` 均未通过；
- Task DAG 中 `CB-110` 的 inputs/outputs/actions/verification/risks/rollback/
  stop conditions 与 `AC-011`、`AC-017`、`AC-065` 为唯一任务权威；
- 精确安装：
  - Node.js `24.18.0` Linux x64，
    archive SHA-256
    `55aa7153f9d88f28d765fcdad5ae6945b5c0f98a36881703817e4c450fa76742`；
  - `@openai/codex@0.146.0-alpha.3.1`，
    main archive SHA-256
    `3473d6d6416979b43118d203fa4e584c4e5af939206eee854d9db60c7555df17`；
  - Linux x64 platform archive SHA-256
    `d495bfa843ed9198327cc087b69b99aff09a66d4f5e7139137bc72d02ccf3e53`；
- 只从版本清单列明的 Node.js 官方 archive 与 npm 官方 registry 精确 URL
  下载，下载后先校验 SHA-256，再解包；不执行 package lifecycle script，
  不使用 `latest`、范围版本、Git URL 或运行时源码拉取；
- 工具链只落在：
  `/opt/cyberboss-cloud/shared/toolchains/{node,codex,bin}`；
  不写 `/usr/local`，不替换主机全局 Node/Codex；
- `CODEX_HOME=/var/lib/cyberboss/.codex`，必须为 `0700 cyberboss:cyberboss`；
  只检查 `auth.json` 是否存在及其 metadata，不读取、复制或输出内容；
- 版本 evidence artifact 只写
  `/opt/cyberboss-cloud/releases/<implementation-commit>/version-manifest.json`；
  不移动 `current`/`previous` symlink，不修改 CB-100 immutable release；
- 以精确 implementation commit 部署脚本与 version spec；目标地址只通过
  受保护本地部署记录解析，必须匹配
  `target_id_sha256=7865f743d174`，并使用 strict-known-host、key-only
  BatchMode；
- 目标传输只允许一个
  `/tmp/cyberboss-cb110.XXXXXXXX` 模式的 `0700` caller-owned ephemeral
  staging 目录；只接收精确 commit 的 CB-110 kit 文件，退出时必须清除；
- Codex App Server 验收使用 transient process，只监听
  `ws://127.0.0.1:8765`，完成 `/readyz` 与
  `initialize`/`initialized` 后立即清理；
- Claude Code 因非必要且目标资源/供应链面应最小化而不安装；凭据保持缺失，
  `CB_CLAUDE_RUNTIME=false`、`CB_CLAUDE_EVAL_PASSED=false`。只有二者均为
  exact `true` 时受控启动入口才允许继续；本 Run 不实际启用。

## 3. Non-goals

- 不执行 `CB-120` 或建立 workspace copy/alias；
- 不运行微信扫码、Codex device auth、真实 turn 或 Claude 登录；
- 不启动/enable `cyberboss-cloud.service`，不运行真实业务 Runtime；
- 不建立公网 callback、DNS、Cloudflare route、R2/OCI、Status 或其他服务；
- 不写 Private-MetaDatabase，不运行 provider write；
- 不读取或复制任何 credential/session/private key 内容；
- 不创建 repo、remote、submodule、Git URL dependency 或上游关系；
- 不修改 fixed App/vendor source、许可证、冲突记录、Task DAG、PRD、Roadmap、
  Acceptance 或 CB-000–CB-100/PG-0 历史 evidence；
- 不 push，不创建 PR/tag/release，不运行 GitHub CI；
- 不把 App Server 未认证 ready 或 simulator 称为真实 authenticated turn。

## 4. Inputs to inspect

- `04_TASK_DAG_EXECUTION_PACK.yaml` 的 `CB-110`
- `02_PRD_ACCEPTANCE_CONTRACT.md` 的 `AC-011`、`AC-017`、`AC-065`
- `12_CURRENT_ROADMAP.md` 的 Lane B 与 PG-1
- `machine/source-lock.json`
- `docs/evidence/CB-030/**`
- `docs/evidence/CB-040/implementation-plan.json`
- `docs/evidence/CB-100/**`
- `implementation-kit/scripts/bootstrap-host.sh`
- `implementation-kit/scripts/run-cyberboss.sh`
- `implementation-kit/scripts/auth_activation_check.py`
- `implementation-kit/config/cyberboss.env.example`
- `machine/facts/task_state.json`
- 受保护本地 OVH deployment identity/baseline/known-host records（值不落库）

## 5. Allowed repository modifications

- `CyberBoss/docs/governance/RUN_CONTRACT_P1_2_CB_110.md`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/runtime-versions.json`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-runtime-toolchain.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/probe-codex-app-server.mjs`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/run-cyberboss.sh`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256`
- `CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256`
- `CyberBoss/tests/cloud-runtime-version.test.js`
- `CyberBoss/scripts/validate_cb110.py`
- `CyberBoss/docs/evidence/CB-110/**`
- `CyberBoss/machine/facts/task_state.json`
- `CyberBoss/README.md`
- `CyberBoss/HANDOFF.md`
- `CyberBoss/CHANGELOG.md`

除以上路径外不得修改。尤其禁止修改 `CyberBoss/app/**`、
`CyberBoss/vendor/**`、历史 evidence 和母仓其他项目。

## 6. Validation

### Local implementation boundary

```bash
bash -n \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-runtime-toolchain.sh \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/run-cyberboss.sh
node --check \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/probe-codex-app-server.mjs
node --test CyberBoss/tests/cloud-runtime-version.test.js
cd CyberBoss/app && npm run check && npm test
python3 CyberBoss/scripts/validate_cb110.py --prepare
```

### Authorized OVH acceptance

- rerun fresh read-only host/identity/listener/toolchain preflight；
- `--check` 必须证明无 live command 和 persistent write；
- apply 精确 commit 的 runtime spec/toolchain installer 两次；
- 验证 exact versions、archive hashes、root ownership、immutable modes、
  project-local command paths 和 idempotent second apply；
- 以 `cyberboss` 身份运行 `node --version` 与内存 SQLite self-test；
- 以 `cyberboss` 身份、专用 `CODEX_HOME` 临时启动 App Server：
  - `/readyz` 返回 ready；
  - WebSocket `initialize` 获得 result，随后发送 `initialized`；
  - 活跃期间 `8765` 只见 `127.0.0.1` listener；
  - 从目标外部对目标公网地址扫描 `8765` 必须不可达；
  - 验收结束进程与 listener 必须为 0；
- 只以 metadata 探针确认 target Codex auth 为 `activation_pending`，不执行
  device auth、不读取 auth content；
- 验证 Claude binary/credential absent、默认 flag/eval false，并对四种双门
  组合执行 dispatch test：仅 `true+true` 可越过 gate，但不启动适配器；
- secret/path/port/publication/scope scan P0/P1 findings 必须为 0。

### Closure

```bash
python3 CyberBoss/scripts/validate_cb110.py
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

CB-000 固定基线验证必须在 frozen input commit 上执行；不得为了让历史
validator 接受后续实现而改写 CB-000 evidence/source lock。

## 7. Risks and rollback

- **Supply-chain drift:** 任何 version/URL/hash/package identity 不符立即停止；
  不执行未校验 archive。
- **Shared-host collision:** apply 前核对 existing path 类型、owner、mode 与
  exact version；不明已有内容立即停止，不覆盖。
- **Auth exposure:** 安装器只建目录，metadata probe 不读内容；若命令要求
  public callback 或需要输出 token，标记 `activation_pending` 并停止该动作。
- **Listener exposure:** 启动参数固定 loopback，活跃与结束时均验证 listener；
  发现 non-loopback 立即杀掉 transient process 并回滚。
- **Claude accidental activation:** 两个 root-controlled gate 缺一即拒绝；
  本阶段不安装 binary/credential。
- **Rollback:** 仅删除本 Run 新建且 hash/owner/path 均精确匹配的 toolchain
  version、project bin links 与 version-manifest release；保留任何既有
  `CODEX_HOME` 与认证文件，不移动 CB-100 `current`/`previous`。

## 8. Stop conditions

- target hash、known-host、key-only identity、sudo、host machine identity 与
  CB-010/CB-100 不一致；
- fresh preflight 为 protect/hazard、端口已有不明 listener、目标路径已有
  drift/不明 ownership 或空间不足；
- archive/hash/version/platform、Node SQLite self-test 或 Codex protocol
  initialize 不一致；
- App Server 无法 ready、只可通过 non-loopback/public callback 才能 ready；
- 发现 auth/secret content 被读取、输出、复制或 commit；
- Claude 默认配置可越过 gate，或必须真实启用 Claude 才能通过；
- apply 会修改全局 Node/Codex、其他 service/route/repo/data/provider；
- 无法形成 exact commit-bound、idempotent、可清理的安装。

## 9. Acceptance

`CB-110` 仅在以下全部成立时为 `passed`：

1. 依赖节点通过，只有 `CB-110` 改变 task state；
2. exact Node/Codex versions 与三个 archive SHA-256 均通过；
3. Node SQLite self-test 通过；
4. Codex App Server `/readyz` 与 protocol initialize 通过；
5. 活跃期间 8765 仅监听 `127.0.0.1`，外部不可达，结束后 listener/process=0；
6. `CODEX_HOME` 为受保护 service-user 目录，auth content reads=0；
7. target Codex real auth 准确保持 `activation_pending`，device-auth 命令已准备
   但未执行；
8. Claude binary/credential absent，默认双门关闭，负向 dispatch 全部拒绝；
9. P0/P1 security findings=0，无 public callback/Runtime/provider/data write；
10. version manifest 绑定精确 implementation commit，二次 apply idempotent；
11. fixed source、双许可证冲突记录与历史 evidence 未改；
12. local/full regression/global validators 通过，remote Git publication 仍为空。
