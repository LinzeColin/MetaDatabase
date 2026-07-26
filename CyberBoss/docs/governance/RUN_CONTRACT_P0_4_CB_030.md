# Run Contract — P0.4 / CB-030

## 1. Goal

运行并验证固定源码包随附的 WeChat iLink 与 Codex App Server simulator，
仅在协议证据证明具体缺口时最小扩展。覆盖 channel 收发、重复消息、候选
cursor、provider failures，以及 Runtime initialize、thread/turn、progress、
approval、completion、error、overload、crash/reconnect 和 false-success。
将 Codex device auth 与 WeChat QR 登录、受保护状态和 re-login 合并为一张
可复制 activation sheet；真实 adapter 未安全激活时保持
`activation_pending`，不阻塞后续开发。

## 2. Minimum scope

- 以固定 CyberBoss source、CB-000 App Server schema evidence 和当前 OpenAI
  Codex App Server 官方协议为证据核对 simulator；
- 原样运行 supplied simulator，先记录基线，再只修复可复现的启动或协议
  缺口；
- WeChat simulator 覆盖 QR/login、`getupdates`、`sendmessage`、empty batch、
  duplicate update、cursor replay/out-of-order，以及 401/403/429/500/503、
  deterministic timeout、connection reset、unknown send outcome 和 duplicate
  acknowledgement fixtures；
- Codex simulator 覆盖 initialize/initialized gate、thread start/resume、
  turn start、text/progress、approval response、completion、retryable/terminal
  error、bounded-queue overload、interrupt、process crash/reconnect、
  false-success、late/duplicate event 和 deterministic artifact oracle；
- 使用 synthetic、无 secret、无 PII、无真实时间等待的 contract tests；
- 只读检查本机与授权 OVH staging 的 CLI/auth-state 可用性；不得输出 auth
  内容、account、email、token、QR payload 或私聊；
- 生成 `auth-gates.md`、脱敏命令输出、明确标为 fixture 或 real 的 WeChat
  截图、安全报告和验证报告；
- 覆盖 AC-001、AC-010、AC-056、AC-065；真实 AC-001/AC-010 activation
  Oracle 未满足时不得声称 verified。

## 3. Non-goals

- 不执行 `P0.5 / CB-040`；
- 不实现 durable inbox/outbox、SQLite state machine、scheduler、Timeline
  canonical sync 或真实 E2E；
- 不反复尝试真实微信登录，不绕过账号地区限制、ban 或 risk-control；
- 不执行会创建、刷新、吊销或打印凭据的真实认证动作；
- 不读取或复制 `auth.json`、微信 bearer/session 文件内容；
- 不安装/部署/启动 CyberBoss Runtime，不写 Cloudflare、R2、OCI 或
  Private-MetaDatabase；
- 不创建新 repository，不恢复 upstream remote，不修改母仓其他项目；
- 不 push，不创建 PR/tag/release。

## 4. Inputs to inspect

- `04_TASK_DAG_EXECUTION_PACK.yaml` 的 `CB-030`
- `02_PRD_ACCEPTANCE_CONTRACT.md` 的 AC-001、AC-010、AC-056、AC-065
- `05_ACCELERATED_VERIFICATION_MODEL_SECURITY_RELEASE.md` 的 simulator contract
- `06_OPERATIONS_STATUS_HANDOVER.md` 的 Codex/WeChat activation 与 re-login
- `09_PREAUTHORIZED_DECISIONS_ACTIVATION_INPUTS.md`
- `machine/source-lock.json`
- `docs/evidence/CB-000/codex-protocol-methods.json`
- `app/src/adapters/channel/weixin/`
- `app/src/adapters/runtime/codex/`
- `implementation-kit/simulators/`
- 本机与 CB-010 已授权 OVH staging 的部署记录、CLI 存在性和 auth-state
  status；只允许脱敏、只读检查
- 当前 OpenAI Codex App Server 官方手册；不使用非官方协议猜测

## 5. Allowed modifications

- `CyberBoss/docs/governance/RUN_CONTRACT_P0_4_CB_030.md`
- `CyberBoss/docs/evidence/CB-030/**`
- `CyberBoss/machine/facts/task_state.json`
- `CyberBoss/scripts/validate_cb030.py`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/simulators/**`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/simulator-contract.test.mjs`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/auth_activation_check.py`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/secret_scan.py`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/test_external_adapters.py`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md`
- `CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256`
- `CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256`
- `CyberBoss/docs/product_design/v0.0.0.4/03_ARCHITECTURE_DATA_SECURITY.md`
- `CyberBoss/docs/product_design/v0.0.0.4/06_OPERATIONS_STATUS_HANDOVER.md`
- `CyberBoss/docs/product_design/v0.0.0.4/09_PREAUTHORIZED_DECISIONS_ACTIVATION_INPUTS.md`
- `CyberBoss/README.md`
- `CyberBoss/HANDOFF.md`
- `CyberBoss/CHANGELOG.md`

`CyberBoss/app/**` 只有在 simulator contract test 证明现有 adapter 存在本
phase 必须处置的具体 pinned-protocol 缺陷时才允许最小修改，并必须同步
CB-000 source-change evidence。`CyberBoss/vendor/**`、母仓根文件及其他项目
不可修改。

## 6. Validation

```bash
node --test \
  CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/simulator-contract.test.mjs
npm --prefix CyberBoss/app run check
npm --prefix CyberBoss/app test
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/auth_activation_check.py \
  --mode local --output CyberBoss/docs/evidence/CB-030/auth-probe.local.redacted.json
python3 CyberBoss/scripts/validate_cb030.py
python3 CyberBoss/scripts/validate_cb000.py
python3 CyberBoss/scripts/validate_prestage0.py
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_taskpack.py \
  CyberBoss/docs/product_design/v0.0.0.4
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_task_dag.py \
  CyberBoss/docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_traceability.py \
  CyberBoss/docs/product_design/v0.0.0.4
python3 CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_no_wait.py \
  CyberBoss/docs/product_design/v0.0.0.4
git diff --check
```

历史 CB-020 validator 对 `current_run=P0.3` 的 phase lock 在当前 HEAD 会按设计
报 downstream state；其身份、安全和许可证回归由 CB-030 validator 直接调用
相同底层 tests/secret scan/CB-000，并在精确 P0.3 commit 的临时
`codex/cyberboss-*` 本地分支/worktree 中再次运行原 validator。验证后立即删除
该临时 worktree 与 branch；detached HEAD 不满足 Prestage 的 branch scope，
不得把该门禁失败误报为历史行为回归。

## 7. Risks and rollback

- Simulator 被误报为真实 provider：所有输出、截图和报告强制标记
  `fixture`；真实状态独立记录。
- 凭据或 QR payload 泄露：只检查存在性、mode、CLI status 与哈希无关的
  boolean；不读取文件内容；输出再运行 known-secret equality/pattern scan。
- 真实账号风控：本 Run 不自动扫码、不提交登录；若只读 probe 返回 ban 或
  risk-control，只停止 WeChat activation 并保留 simulator 继续。
- WebSocket 暴露：simulator 只接受 loopback host，使用 ephemeral local
  port，测试结束强制关闭 child process。
- 固定等待：fault fixtures 立即返回确定性结果或断开连接；测试使用事件
  predicate/timeout safety bound，不用 sleep 作为成功 Oracle。
- 本地回滚为单一 P0.4 commit；没有外部 mutation，因此不需要 provider
  rollback。

## 8. Stop conditions

- 任何真实 credential、auth JSON、token、email/account ID、QR payload 或
  私聊即将出现在 stdout、Git 或截图；
- 真实 WeChat adapter 返回 ban/risk-control，或 device auth 流程要求在非
  交互日志中打印秘密；
- simulator 需要绑定非 loopback 地址或访问公网；
- 需要修改 P0.5、durable runtime、外部 provider 或 `CyberBoss/**` 之外；
- AC-056/AC-065 出现未处置失败，或证据无法区分 fixture 与 real；
- 需要 push、PR、tag、release 或部署。

## 9. Acceptance

`CB-030` 仅在以下全部成立时为 `passed`：

1. 两个 supplied simulator 可从 clean local command 启动，默认仅绑定
   loopback，测试结束无残留 listener/process；
2. WeChat contract test 可执行证明 QR/login、receive/send、empty batch、
   duplicate/cursor replay/out-of-order 和全部 failure/unknown/duplicate-ack
   fixtures；
3. Codex contract test 可执行证明 initialize gate、thread/turn、progress、
   approval、completion、错误、overload、interrupt、crash/reconnect、
   false-success、late/duplicate event 与 artifact Oracle；
4. `auth-gates.md` 合并 Codex device auth 与 WeChat QR 的准备、执行、验证、
   文件权限、stop/revoke/re-login 步骤，不含真实值；
5. 真实 Codex/WeChat state 只可为 `verified`、`activation_pending` 或
   `failed`，且真实 AC-001/AC-010 未跑时保持 `activation_pending`；
6. 缺失 credential fixture 下全部非激活测试通过，无全局等待节点
   （AC-056）；
7. secret、port、workspace 与 fixture security scan 的 P0/P1 findings=0
   （AC-065）；
8. CB-000/020 已完成边界、固定来源、Corresponding Source、NOTICE、129 项
   依赖与严格 GPL/AGPL 冲突记录继续通过回归；
9. CB-040 及后续 Task、PG-0–PG-5 均未推进，Git 远端仍无 CyberBoss 发布。
