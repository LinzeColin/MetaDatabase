# Personal-WorkBench — 持续推进手册

## 当前目标

完成 `S5-T1` Save Version 私有候选的冻结准备；当前已冻结的本地候选须交给独立 Verifier。只有精确 commit 的独立裁决和 Sites source linkage 均可证实时，才保存私有 Version。不得公开部署。

## 当前状态

- 当前推进阶段：`S5-T1_PRIVATE_CANDIDATE_READY_FOR_INDEPENDENT_VERIFIER`
- 2026-08-09：首个冻结候选 `3210a4737e575978a627a9a8b6d092c2d9162a1e` 的独立审查 Round 1 为 `BLOCKED`；其正式 S4-T3 追溯/15 项验收/Sites 私有 Version 证据尚不存在，且不能由本地 `verify:release` 替代。该结论保留为历史审查事实，新的修复不会倒改它。
- 2026-08-09：已修复审查发现的本地 P1：服务端敏感云端门现在要求当前 policy 的明确同意、未撤回和 active 删除状态；覆盖账单、体重、日记、经期、日记图片与含敏感内容的旧数据导入。账户删除改为 R2 删除失败即保持 pending 并可重试，不再删除元数据/用户。替代候选已在本地提交，仍未创建 Sites Version、修改 Sites 环境、改变访问策略、部署或上传 GitHub。
- 2026-08-09：本地 P0 验证已重跑通过（unit、privacy、modules、e2e、quality、visual、recovery、check、build 与干净环境 `verify:release`）；`verify:release` 仍明确为 `NOT_ISSUED_PRE_VERIFIER`，不可替代 S4-T3 独立裁决。尚未创建 Sites Version、修改 Sites 环境、改变访问策略、部署或上传 GitHub。
- 2026-08-09：生产/运维预检证据已收敛为状态、时延、存在性和脱敏引用；不再写入命令输出、响应正文、原始嵌套证据、本机绝对路径或配置值。对应回归由 `test:release-evidence` 覆盖。
- 2026-08-08T20:41Z：现有 ChatGPT Sites 项目处于 `active` 且当前身份为 `owner`，但仍无已保存版本、预览/生产 URL 或生产环境变量；未创建版本、未部署、未上传 GitHub。
- 最新 `npm run verify:owner-activation`：`BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK`（17 项风险）。Cloudflare CLI 未登录、生产环境变量为空、公开授权素材记录未落盘仍是当前阻断。
- 本地构建已通过；`npm run test:s2` 通过 schema、认证契约、租户隔离、API 和 R2 约束，但 Saved Candidate 真实认证回放仍为 `NOT_RUN`。
- `S5-T3` 保持下游：本地路由与鉴权探针可达；真实 OAuth/邮箱注册/找回/会话链路与生产域回放尚未执行。
- `PRE_S5_T1_LOCAL_PREFLIGHT` 已通过（仅本地/非生产证据化）；任务包 canonical `S5-T1`（保存私有 Version）仍为 `NOT_RUN_BUILD_LAST_MILE`，不得由本地预检替代。
- `S5-T2` 当前状态：`BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK`（当前剩余阻断为 `wrangler` 认证态与 `asset_manifest` 公开授权状态）。
- `S5-T3` 当前状态：`BLOCKED_LOCAL_PRODUCTION_SMOKE_PRECHECK`（本地路由与鉴权探针可达；阻断在于真实 OAuth/邮箱注册/找回/会话链路与生产域回放尚未执行）
- 2026-08-09T06:52:26+10:00：补齐本地邮箱验证恢复 UX：注册成功后引导至验证页；验证页可安全地重发验证邮件；验证完成后回到登录页显示登录指引。该改动仅通过同源常量回调，不在 URL 中放置邮箱，也未触及 Sites、密钥、公开素材或 S5 生产门状态。
- 2026-08-09T07:03:09+10:00：S5-T2 预检证据已完成脱敏加固。Sites 控制面仍显示 owner 权限、私有自定义访问、0 个保存版本、无预览/生产 URL、0 个生产环境变量；本地预检仍为 `BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK (17)`，但不再将密钥片段、邮箱、CLI 原文或绝对本机路径写入证据。
- 2026-08-09T07:19:50+10:00：发布前置脚本现明确为 `PRE_S5_T1_LOCAL_PREFLIGHT`，不冒充任务包的 `S5-T1` Saved Version 验收。默认探针改为无密钥受控路由 harness（503/200），不会隐式启动 dev 或加载本地变量；只有显式 `S2_LOCAL_AUTH_ORIGIN` 才探测操作者已启动的服务。干净环境 `npm run verify:public-launch` 通过，但报告仍为 `public_deploy_eligible=false`、4 个外部门未满足；未创建 Sites Version、未部署、未改环境、未上传 GitHub。
- 公开部署状态：`BLOCKED_ASSET_RIGHTS`；`asset_manifest` 尚无最终公开授权素材记录，且本地预检不授予 Deploy 权限。
- 验收脚本已兼容非交互场景：`npx wrangler whoami` 若提示 400/未登录，会在 `13_evidence/owner_activation.json` 输出 `checks.wrangler.auth_recovery_hint`；本地 token 即使过期也会尝试执行 `whoami`，以保留可复现失败证据；如配置过期，也可通过 `CLOUDFLARE_API_TOKEN` 验证（非交互环境）。
- 里程碑状态：
  - `npm run test:quality`：通过，`13_evidence/quality.json` 为 `PASS_LOCAL_QUALITY`
  - `npm run test:visual`：通过，`13_evidence/visual/manifest.json` 为 `PASS`
- `npm run test:resilience`：通过，`13_evidence/resilience.json` 为 `PASS_LOCAL_RETRY_RESILIENCE`
- `npm run verify:public-launch`：本地前置检查通过，产出 `13_evidence/public_launch_preflight.json`；不代表 canonical `S5-T1` 已完成或可部署。
- `npm run verify:owner-activation`：再次失败，产出 `13_evidence/owner_activation.json`，状态 `BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK`。
  - 已使用本地完整占位变量演练时阻断降至 2 条：
    1) 未检测到 `wrangler oauth_token`
    2) `asset_manifest` 仍处于 `BLOCKED_ASSET_RIGHTS`
- `npm run verify:production-smoke`：当前 BLOCKED，产出 `13_evidence/production.json` 与 `13_evidence/production-smoke-run.json`
- `npm run verify:ops-projection`：当前 BLOCKED，产出 `13_evidence/ops_projection.json` 与 `13_evidence/ops_projection-run.json`
- `verify:release` / `taskpack` 预检沿用 S5-T1 现状
- S5-T2 可执行清单已补齐在 [RUN_CONTRACT_S5_T2.md](/Users/linzezhang/.codex/worktrees/ef81/MetaDatabase/Personal-WorkBench/RUN_CONTRACT_S5_T2.md)（含复制执行命令与证据刷新要求）

## 已改动

- `server/security/privacy-consent.ts`
  - 新增敏感云端处理的唯一服务端门：要求当前版本同意、未撤回且账户未处于 pending 删除；普通模块不受阻塞。
- `app/api/workbench/[resource]/*`、`app/api/workbench/files/*`、`server/files/private-files.ts`
  - 敏感记录与日记图片在读取、创建、替换以及幂等记录写入前均执行服务端门；本人删除路径保持可用以支持数据清除。
- `server/data/legacy-import.ts`、`app/api/workbench/legacy-import/*`
  - 含账单、体重、日记、经期或日记图片的导入，在写入导入状态/幂等键前必须通过同意门；仅普通数据的导入仍可预览。
- `server/data/account-lifecycle.ts`
  - R2 对象删除失败或缺失绑定时 fail-closed，保留 pending 状态、恢复口令、文件元数据和后续删除步骤用于安全重试。
- `tests/privacy.test.mts`、`tests/r2.test.mts`、`tests/legacy-import.test.mts`、`tests/account-lifecycle.test.mts`、`tests/api-contract.test.mjs`
  - 覆盖未同意、旧 policy、撤回、日记对象、旧数据导入与 R2 删除中断/重试的负向和恢复路径。

- `app/_components/workbench/outbox-queue.ts`
  - 新增 outbox 队列读写与重放策略模块，提炼 `read/write/append/replay` 逻辑。
- `app/_components/workbench/todo-page-client.tsx`
  - 将待发队列读写与重放改为共享 outbox 模块，`503`/冲突/网络异常下不继续无序重发，保留未完成动作。
- `tests/outbox-replay.test.mts`
  - 新增离线重放回归：成功、冲突、503、网络异常场景。
- `scripts/verify-offline-replay.mts`
  - 新增离线重放验证脚本，产出 `13_evidence/resilience.json`。
- `RUN_CONTRACT_S4_T2.md`
  - 新增本阶段任务合同。
- `RUN_CONTRACT_S4_T3.md`
  - 新增本阶段任务合同与候选冻结预检收束标准。
- `scripts/verify-release.mjs`
  - 保持 release 预检脚本与证据链不变（`13_evidence/verifier.json`）。
- `RUN_CONTRACT_S5_T1.md`
  - 新建本阶段任务合同。
- `scripts/verify-public-launch-preflight.mjs`
  - 新增发布前置统一预检脚本；默认使用无密钥受控路由 harness，不隐式启动 dev 或加载本地变量。显式传入 `S2_LOCAL_AUTH_ORIGIN` 时才探测操作者已启动的本地服务。
- `package.json`
  - 新增 `verify:public-launch` 脚本。
- `scripts/verify-owner-activation.mjs`
  - 新增 Owner 生产激活本地预检脚本，输出 `13_evidence/owner_activation.json`。
- `scripts/verify-owner-activation.mjs`（本次更新）
  - 增加 `SITES_BINDINGS_CONTRACT.json` 与 `13_evidence/verifier.json` 的一致性校验：D1/R2 绑定一致性、约定密钥覆盖、release 预检状态。
- `scripts/verify-production-smoke.mjs`
  - 新增生产链路预检脚本，输出 `13_evidence/production.json` 与 `13_evidence/production-smoke-run.json`；预检报告只保留脱敏状态，不保留 Origin、响应正文或命令原文。
- `scripts/verify-ops-projection.mjs`
  - 新增状态系统投影前置脚本，输出 `13_evidence/ops_projection.json` 与 `13_evidence/ops_projection-run.json`；不记录 adapter endpoint、token 或响应正文。
- `package.json`
  - 新增命令别名：`verify:production-smoke`、`verify:ops-projection`、`test:unit`、`test:recovery`、`test:regression`。
- `server/data/account-lifecycle.ts`
  - 将隐私常量对齐任务包公开版本：`ACCOUNT_PRIVACY_POLICY_VERSION = "2026-08-03.v2"`，`ACCOUNT_PRIVACY_NOTICE_SHA256 = "5c5403...a2f7e956"`，消除占位 hash 导致的本地隐私证据误报。
- `RUN_CONTRACT_S5_T2.md`
  - 新增本阶段任务合同（Owner 生产激活前置）并对齐执行边界。
- `RUN_CONTRACT_S5_T3.md`
  - 新增 S5-T3 预检合同。
- `app/auth/_components/auth-flow.ts`
  - 集中认证请求与受控回调路径，新增邮箱验证重发请求契约。
- `app/auth/_components/auth-form.tsx`
  - 注册后进入验证页；验证页渲染重发邮件表单；验证成功后显示登录指引。
- `tests/auth-contract.test.mts`、`tests/e2e-smoke.test.mjs`
  - 覆盖重发验证邮件、无邮箱泄露的回调、验证页与验证后登录提示的构建产物渲染。
- `scripts/verify-auth-contract.mjs`
  - 将认证契约校验对齐至新的请求构造模块。
- `scripts/verify-owner-activation.mjs`
  - 将 S5-T2 证据降为存在性、状态与匹配结论；剔除密钥片段、个人邮箱、CLI 输出、原始嵌套证据与绝对本机路径。
- `tests/owner-activation-evidence.test.mjs`
  - 以临时目录和伪造值验证证据 JSON 不泄漏配置或命令输出。
- `package.json`
  - 新增 `test:owner-activation` 回归入口。
- `13_evidence/production.json`
  - 从任务包封存模板初始化，作为 S5-T3 证据槽位。
- `13_evidence/ops_projection.json`
  - 从任务包封存模板初始化，作为 S5-T4 证据槽位。

## 验证命令与结果

- 本轮安全修补（2026-08-09）：`npm run lint`、`npm run typecheck`、`npm run test:unit`、`npm run test:privacy`、`npm run test:account-lifecycle`、`npm run test:legacy-import`、`npm run test:modules`、`npm run build`、`npm run test:e2e`、`npm run test:quality`、`npm run test:visual`、`npm run test:recovery`、`npm run check`、`npm run test:release-evidence` 均通过。
- 干净环境 `npm run verify:release`：通过，状态 `PASS_BUILD_LAST_MILE_READINESS`，verdict 仍为 `NOT_ISSUED_PRE_VERIFIER`；不构成 S4-T3 或 S5-T1 通过。

- `npm run test:quality`（通过）
- `npm run test:visual`（通过）
- `npm run test:resilience`（通过）
- `python3 12_scripts/verify_taskpack.py`（通过；`PASS_FOR_SEALED_TASKPACK`）
- `npm run verify:release`（通过；`13_evidence/verifier.json` 写入）
- `npm run test:s2`（通过）
- `npm run verify:public-launch`（PRE-S5-T1 本地检查通过；`13_evidence/public_launch_preflight.json` 写入；不等同于任务包 S5-T1）
- `npm run verify:owner-activation`（当前 BLOCKED；`13_evidence/owner_activation.json` 写入）
- `npm run verify:production-smoke`（当前 BLOCKED；`13_evidence/production.json` 与 `13_evidence/production-smoke-run.json`）
- `npm run verify:ops-projection`（当前 BLOCKED；`13_evidence/ops_projection.json` 与 `13_evidence/ops_projection-run.json`）
- 本轮本地复测（2026-08-05T23:02:26-32Z）：`npm run verify:production-smoke`、`npm run verify:ops-projection` 在本地 3000 端口均可访问，`/api/auth/public-config` 与 `/api/workbench/profile` 已达标（200/401），三类 `/api/ops/*` 均返回 200，但阻断仍在真实生产 OAuth/邮件回放链路未执行。
- 最新一次 `npm run verify:owner-activation`（2026-08-05T21:37:34.215Z）：`checks.wrangler.auth_mode` 在缺失 `wrangler` 登录时仍为 `BLOCKED`，阻断项固定为：
  - `wrangler oauth_token` 缺失（需执行登录）
  - `OWNER_APPROVAL.production_side_effect_authorization=false`
  - `asset_manifest` 仍 `BLOCKED_ASSET_RIGHTS`
  `generated_at` 已刷新。
  注：本轮使用最小化占位生产环境变量（包含完整隐私哈希）复跑，仅保留上述 3 项阻断。
- 次次运行（2026-08-05T21:41:30.723Z）：`npm run verify:owner-activation` 再次返回 `BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK`，三项阻断未变化。
- `npm run test:auth-runtime`（通过，`PASS_LOCAL_NO_SECRET_AUTH_BOUNDARY`；默认不启动本地 dev，显式 Origin 模式才探测已启动服务）
- `npm run test:e2e`（通过）
- `npm run test:legacy-import`（通过）
- 本轮本地认证恢复修补（2026-08-09T06:52:26+10:00）：`npm run test:auth`（5/5 通过）、`npm run build`（通过）、`npm run lint`（0 error；4 项既有 warning）、`npm run test:e2e`（3/3 通过）。这些仅证明本地候选；真实邮箱、Google OAuth、Turnstile 与生产域回放仍未执行。
- `npm run typecheck` 已通过：待办操作错误消息已收敛为安全回退文案，临时 `tests/pw-temp.spec.ts` 已被精确排除且保持未跟踪；未以跳过项目源码检查的方式绕过 TypeScript。
- 本轮 S5-T2 证据加固（2026-08-09T07:03:09+10:00）：`npm run test:owner-activation`（2/2 通过）、`npm run lint`（0 error；4 项既有 warning）、干净环境 `npm run verify:owner-activation`（预期 `BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK (17)`）；生成证据已确认无 `value`、`values`、`stdout`、`stderr` 或 `raw` 字段。

证据：
- `13_evidence/quality.json`
- `13_evidence/visual/manifest.json`
- `13_evidence/resilience.json`
- `13_evidence/verifier.json`
- `13_evidence/auth.json`
- `13_evidence/tenant_matrix.json`
- `13_evidence/r2.json`
- `13_evidence/auth-saved.json`
- `13_evidence/auth-local-runtime.json`
- `13_evidence/public_launch_preflight.json`
- `13_evidence/production.json`
- `13_evidence/production-smoke-run.json`
- `13_evidence/ops_projection.json`
- `13_evidence/ops_projection-run.json`

## 未解决风险

- `S4-T3` 仍未通过：首个冻结候选的独立 Round 1 已确认缺少正式 15/15 acceptance traceability、精确 subject binding 和真实 Sites 私有 Version 证据；当前修复候选必须独立复核。
- 通用 Verifier 的任务包导入器未识别该任务包的 canonical manifest 布局；不可伪造导入成功或正向报告，需使用兼容适配器/人工任务包追溯证据完成正式裁决。

- 未登录 wrangler（`wrangler whoami` 失败）：仅影响 CLI 侧的 Pages 核验；Sites 控制面已独立复核当前身份为 owner，但这不替代运行时环境、素材授权或真实认证链路验收。
- 当前机本地未落盘可用 wrangler token（默认路径 `~/Library/Preferences/.wrangler/config/default.toml` 目前不存在可用 `oauth_token`）
- `wrangler whoami` 常见失败（400 Bad Request）可先执行 `wrangler logout` 后 `wrangler login`，再重试 `whoami` 与 `pages project list --json`
- 已尝试 `npx wrangler login --browser=false --scopes pages:write --scopes d1:write --scopes workers:write`（2026-08-05 21:35）：
  - 已抓到授权链接并等待回调，但本次会话 2 分钟超时未完成回调（未接收到授权码）。
  - 观察到日志落盘：`/Users/linzezhang/Library/Preferences/.wrangler/logs/wrangler-2026-08-05_21-35-09_011.log`，结尾错误为 `user oauth authorization timeout`。
  - 需要在外部浏览器打开授权链接并完成 callback 后，重试本机登录命令并继续 `npx wrangler whoami`。
  - 实测提示：`localhost:8976` 会被 callback 命中；若回调失败，可手动核验回调 URL 最终应含 `code` 与 `state`，并避免 `127.0.0.1` 转发误配。
- 已再次尝试 `npx wrangler login`（2026-08-05 21:39）：
  - 本次再次打印 OAuth 授权链接并等待 2 分钟超时退出，未接收到授权码。
  - 观察到日志落盘：`/Users/linzezhang/Library/Preferences/.wrangler/logs/wrangler-2026-08-05_21-39-24_141.log`，同样记录 `user oauth authorization timeout`。
- 证据状态更新：`13_evidence/owner_activation.json` 的 `checks.wrangler.whoami.reason` 仍为“wrangler 配置缺失/异常”，且 `generated_at` 已更新为 `2026-08-05T21:41:30.723Z`。
- 当前建议保留：在外部环境执行 `npx wrangler login`（`--browser=false`，并完成回调）后，再在本机执行 `npx wrangler whoami` 与 `npx wrangler pages project list --json`。
- `RUN_CONTRACT_S5_T2.md` 已补充上述非交互登录命令与回调说明（含可复制链接流程）。
- 本地 `owner_activation` 已能区分 `auth_mode`：`LOCAL_TOKEN`（本地 token 可用） / `CLOUDFLARE_API_TOKEN`（非交互 token） / `SKIP`（认证不可执行）
- `owner_activation` 已带入 `checks.wrangler.config`：可直接核验本机 `.wrangler/config/default.toml` 中 `expiration_time` 与 token 状态，若已过期请先 `wrangler login` 重置会话。
- 当前证据链已带入 `owner_activation` 的 wrangler 认证恢复提示字段，可直接看 `checks.wrangler.whoami.auth_recovery_hint` 获取重登建议。
- 必需生产密钥已在本地模拟校验中临时注入验证，外部仍缺失实际可用的 Sites Secrets（`BETTER_AUTH_SECRET`、`APP_ORIGIN`、`GOOGLE_*`、`RESEND_API_KEY`、`TURNSTILE_*`、`LEGAL_OPERATOR_NAME`、`PRIVACY_CONTACT_EMAIL`、`MAIL_FROM`/`AUTH_FROM_EMAIL`）
- `SITES_BINDINGS_CONTRACT.json` 约定密钥在实际部署环境暂未写入核验（本地仅验证清单完整性）
- `SITES_BINDINGS_CONTRACT.json` 的 `project_id` 仍是 `generated_by_sites_and_never_hand_invented` 占位符，需在正式 provision 后复核与生产配置一致
- `OWNER_APPROVAL.production_side_effect_authorization` 为 `true`
- `CLOUDFLARE_API_TOKEN` 未设置（非交互 `wrangler` 调试时的替代认证入口）
- `PRIVACY_POLICY_VERSION` 与 `PRIVACY_NOTICE_SHA256` 可通过环境模拟对齐任务包值（`2026-08-03.v2` 与 SHA）。
- 公开素材授权状态 `BLOCKED_ASSET_RIGHTS` 仍需处理
- `13_evidence/verifier.json` 与 `13_evidence/public_launch_preflight.json` 仅为本地预检，不代表正式上线裁决。
- 公开部署仍受素材授权与生产渠道凭据准备状态限制。
- `npm run verify:production-smoke` 已确认本地 401 鉴权与 `/api/auth/public-config` 可达，阻断收敛到“真实 OAuth/邮箱注册/找回/会话链路”外部执行前置。
- `npm run verify:ops-projection` 已确认 `/api/ops/status`、`/api/ops/ovh`、`/api/ops/pdb` 可达与鉴权（401→200）路径闭环，残留阻断由 `production-smoke` 未通过导致的联动红线。
- 本轮 `production-smoke` 风险收敛为 `1` 项（真实回放未执行），`ops-projection` 风险收敛为 `1` 项（S5-T3 阻断），说明本地可复现预检已进入外部门槛阶段。

## 下一步

1. 对当前已通过本地回归的精确冻结候选执行与 Builder 分离的 S4-T3 Verifier；`NOT_RUN`、`UNKNOWN` 或本地自检不得计为 PASS。
2. 只有该候选的独立裁决和验收追溯真实通过后，才复核 Sites 的精确 source linkage、私有访问与保存 Version 所需权限；仅保存私有 Version，记录真实 `saved_version.json`。
3. S5-T1 完成后才可进入 S5-T2 的生产环境激活；真实 OAuth、邮件、Turnstile、公开素材权利和生产部署仍全部保持下游。
