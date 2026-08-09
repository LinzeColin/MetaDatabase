# Run Contract — S5-T2 Owner 生产环境激活前置

## 目标

在不改动既定工程架构与视觉真值的前提下，为 Owner 生产激活建立可复现预检链路（仅证据化，不做本地以外的实际部署动作）：
- 将 Saved Candidate 与生产素材授权边界、Secrets、Origin 与回调一致性形成明文检查；
- 验证 Sites 项目可操作前置（project_id、版本/构建可复现、release 证据）；
- 输出 `13_evidence/owner_activation.json`，明确阻断项与可执行下一步。

## 最小相关范围

- `scripts/verify-owner-activation.mjs`：校验生产激活前置依赖与环境条件，输出 owner activation evidence。
- `package.json`：新增 `verify:owner-activation` 命令。
- `13_evidence/owner_activation.json`：脚本自动生成的阶段证据文件。

## 明确不在本 phase 范围（本 run）

- 除非有本线程 Owner 的直接、明确授权，不在本 run 执行 Sites Settings 配置。获授权的私有配置只允许使用已核验的受控来源，并且只记录键名、Secret 属性和配置 revision；不记录或提交值，也不改变访问策略、创建公开 URL 或 Deploy。事务邮件默认仍为 Resend；兼容后端只能经同一 MailPort、显式 `MAIL_PROVIDER` 选择及对应 Sites Secret 启用。
- 不执行 OAuth callback 注册、Google 邮箱域验证或一般真实 Deploy。若同时满足 `ACCEPTANCE_SEQUENCE_ADDENDUM.json` 的 `origin_bootstrap` 全部前置，且当前 Owner 直接授权仍有效，则只允许对已有 Saved Version 使用私有部署控制分配 Sites Origin；它只服务于 `APP_ORIGIN`/hostname-bound 配置，不是 S5-T3、公开发布或真实认证回放。
- 不执行生产 rollback 演练（留给 S5-T3）。
- 不提交或推送 GitHub；不更改现网配置。

## 验收与停止条件

- `npm run verify:owner-activation` 成功执行并写入 `13_evidence/owner_activation.json`；
- 若预检通过，`status` 需为 `PASS_LOCAL_OWNER_ACTIVATION_PRECHECK`，并记录：
  - 生产登录会话可用（wrangler whoami 成功）；
  - 生产密钥项完整（不含空值占位）；
  - `APP_ORIGIN` 与生产来源一致、回调预检清单完整；
  - `asset_manifest` 显示公开发布权限/授权素材状态允许继续（否则阻断）。
- 若任一关键项缺失，则 `status` 为 `BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK`，并将阻断项写入 `risks`（不得误报最终 PASS）。

## 本 run 立即执行清单（复用复制执行）

1. 准备任务包与项目路径：
   - `export TASKPACK_ROOT=/Users/linzezhang/Downloads/TaskPack/Personal-WorkBench/胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8`
2. 登录 Cloudflare/Pages 控制面（若 `whoami` 返回 400/Not logged in，先清理并重登）：
   - `npx wrangler whoami`
   - `npx wrangler logout`
   - `npx wrangler login --browser=false --scopes pages:write --scopes d1:write --scopes workers:write`
     - 命令会输出一条 Cloudflare OAuth 链接（当前环境为非交互时可复制该链接在浏览器授权）。
     - 授权成功后回调后再回到终端继续命令（若需要可先保留回调窗口不关闭）。
   - `npx wrangler whoami`
   - `npx wrangler pages project list --json`
   - 非交互环境可替代前两步：设置 `CLOUDFLARE_API_TOKEN` 后执行 `npx wrangler whoami` 与 `npx wrangler pages project list --json`（token 需具备 Pages 写/读权限）。
3. 核验并补齐 Sites Settings Secrets：
   - `BETTER_AUTH_SECRET`
   - `APP_ORIGIN`
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - 默认 `RESEND_API_KEY`，或显式 `MAIL_PROVIDER=nitrosend` 与 `NITROSEND_API_KEY`（受控兼容选择）
   - `TURNSTILE_SITE_KEY`
   - `TURNSTILE_SECRET_KEY`
   - `LEGAL_OPERATOR_NAME`
   - `PRIVACY_CONTACT_EMAIL`
   - `MAIL_FROM`（或 `AUTH_FROM_EMAIL`）
4. 完成平台侧合规核验：
   - Google OAuth callback、邮件发送域、Turnstile 验证、隐私声明常量（`PRIVACY_POLICY_VERSION`、`PRIVACY_NOTICE_SHA256`）与资产授权清单交付。
5. 重新执行：
   - `npm run verify:owner-activation`
   - `jq '.status,.checks.wrangler.config,.checks.wrangler.auth_recovery_hint,.risks[0:20]' 13_evidence/owner_activation.json`

## 证据快照（本 phase 必须更新）

- `13_evidence/owner_activation.json`
- `13_evidence/asset_manifest.json`
- `13_evidence/verifier.json`
- `13_evidence/sites_runtime_configuration.json`（如已在 Owner 授权下写入私有 Settings）
- `13_evidence/origin_bootstrap.json`（如执行 `S5-T2-ORIGIN-BOOTSTRAP-001`）
- `13_evidence/owner_activation.json` 的 `risks` 长度与 `next_steps`

## 本 run 结论（2026-08-06T10:38:00.000Z）

### 本地验收结果

- `npm run verify:owner-activation` 已再次执行且返回 `BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK`。
- 本次 run 使用临时全量环境占位值（不含生产可用凭证）复现后，`13_evidence/owner_activation.json` 关键阻断已收敛为 **1 项**：
  1. `~/.wrangler/config/default.toml` 无可用 `oauth_token`（当前登录态缺失）
- 风险快照已收敛：`checks.wrangler.config.exists=false`、`checks.wrangler.config.has_token=false`、`checks.wrangler.auth_mode='SKIP'`；`checks.owner_approval.production_side_effect_authorization=true`、`checks.asset_rights.current_state='APPROVED'`。

### 下一步

- 在外部完成 OAuth 授权后，先执行：
  - `npx wrangler login --browser=false --scopes pages:write --scopes d1:write --scopes workers:write`（若会话长期中断，请先执行 `npx wrangler logout` 再重试）
  - `npx wrangler whoami`
  - `npx wrangler pages project list --json`
  - `npm run verify:owner-activation`
- 再补齐并确认：
  - 本地登录态成功后，`checks.wrangler.auth_mode` 与 `checks.wrangler.whoami.ok` 进入绿色；
  - `checks.wrangler.pages_project_list.ok` 可见；
  - `asset_manifest.current_state` 继续保持 `APPROVED`；
  - `checks.asset_rights`、`checks.owner_approval` 不再新增阻断。

## 本 run 结论（2026-08-06T22:10:00.000Z）

### 本地验收结果

- 已执行：
- `TASKPACK_ROOT=/Users/linzezhang/Downloads/TaskPack/Personal-WorkBench/胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8` 环境下运行 `npm run verify:assets -- --record`
  - `npm run verify:assets`
  - `TASKPACK_ROOT=... APP_ORIGIN=https://example.com npm run verify:owner-activation`
- `npm run verify:assets` 已通过：
  - `status: PASS_PRIVATE_CANDIDATE_PUBLIC_DEPLOY_BLOCKED`
  - `asset_count: 42`
  - `masks_verified: 5`
  - `asset_manifest` 与任务包输入一致
- `npm run verify:owner-activation` 仍为：
  - `BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK (15)`
  - 阻断项保留 15 项，且现有核心阻断为：
    1. wrangler 登录态缺失（`~/.wrangler/config/default.toml` 不存在可用 `oauth_token`）
    2. 生产密钥缺失：`BETTER_AUTH_SECRET`、`GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`、`RESEND_API_KEY`、`TURNSTILE_SITE_KEY`、`TURNSTILE_SECRET_KEY`、`LEGAL_OPERATOR_NAME`、`PRIVACY_CONTACT_EMAIL`
    3. 发件人缺失（`MAIL_FROM` 与 `AUTH_FROM_EMAIL`）
    4. 隐私常量缺失（`PRIVACY_POLICY_VERSION`、`PRIVACY_NOTICE_SHA256`）
    5. 资产公开状态仍为 `BLOCKED_ASSET_RIGHTS`（`checks.asset_rights.current_state`）

### 结论

- 本 run 的变更仅完成资产入口可复现校验闭环；Owner 生产激活仍受外部凭据与隐私/资产发布条件阻断，**未进入可部署预检通道**。

### 下一步

- 外部完成 Cloudflare 登录后先执行：
  - `npx wrangler login --browser=false --scopes pages:write --scopes d1:write --scopes workers:write`
  - `npx wrangler whoami`
  - `npx wrangler pages project list --json`
  - `npm run verify:owner-activation`
- 在 owner 侧完成后，补齐并再次核对：
  - `checks.wrangler.auth_mode` 与 `checks.wrangler.whoami.ok`
  - `checks.wrangler.pages_project_list.ok`
  - `checks.required_secrets` 全量齐备且无空值
  - `checks.privacy_gate` 全量通过
  - `checks.asset_rights.current_state == APPROVED`

## 本 run 结论（2026-08-05T22:16:53.642Z）

### 本地验收结果

- 已执行：
  - `TASKPACK_ROOT=/Users/linzezhang/Downloads/TaskPack/Personal-WorkBench/胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8 npm run verify:owner-activation`
- `13_evidence/owner_activation.json` 更新为：
  - `status: BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK`
  - `risks: 17`
- 本轮新增/重申阻断：
  1. wrangler 登录态缺失：`~/.wrangler/config/default.toml` 不存在；
  2. `APP_ORIGIN` 未配置（未能形成 callback 核验上下文）；
  3. 所有关键生产密钥与第三方凭据缺失；
  4. 邮件发件人缺失（`MAIL_FROM`/`AUTH_FROM_EMAIL`）；
  5. 隐私声明环境值缺失；
  6. `asset_manifest` 仍为 `PUBLIC_DEPLOY_BLOCKED`（公开素材权利未完成最终发布态）。

### 下一步

- 先完成 wrangler 登录后再复跑：
  - `npx wrangler logout`
  - `npx wrangler login --browser=false --scopes pages:write --scopes d1:write --scopes workers:write`
  - `npx wrangler whoami`
  - `npx wrangler pages project list --json`
- 确定 `APP_ORIGIN` 后运行：
  - `TASKPACK_ROOT=... APP_ORIGIN=https://<生产域名> npm run verify:owner-activation`
- 以任务包列项逐项补齐并复验：
  - `BETTER_AUTH_SECRET`、`GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`、`RESEND_API_KEY`、`TURNSTILE_SITE_KEY`、`TURNSTILE_SECRET_KEY`、`LEGAL_OPERATOR_NAME`、`PRIVACY_CONTACT_EMAIL`、`MAIL_FROM`（或 `AUTH_FROM_EMAIL`）、`PRIVACY_POLICY_VERSION`、`PRIVACY_NOTICE_SHA256`
- `APP_ORIGIN` 与上述环境项稳定后，再推进 `S5-T3` 的生产 smoke 预检。

## 本 run 结论（2026-08-08T20:41:47Z）

### 已核验的外部与本地状态

- 通过 Sites 控制面读取现有项目：项目处于 `active`，当前身份为 `owner`；`latest_version_number=0`，`current_live_url=null`、`current_preview_url=null`，生产环境变量 `revision=0` 且无 entries。
- `npx --no-install wrangler whoami` 返回未认证；未尝试登录、未读取或写入 token。
- `npm run build` 通过，产物包含鉴权页、账户生命周期 API、工作台资源 API 与运维投影路由。
- `npm run test:s2` 通过：SQLite schema、认证契约、租户隔离、API 边界与 R2 对象键约束均为本地 PASS；`test:auth-saved` 明确返回 `NOT_RUN`，不构成真实身份链路验收。
- 重新执行 `npm run verify:owner-activation`，写入 `13_evidence/owner_activation.json`：`BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK`，共 17 项风险。

### 当前可证明结论

- 本地工程可构建、核心多租户与安全契约可验证；但并不能替代真实生产认证、邮件、Google OAuth、Turnstile 与跨设备回放。
- 公开部署不可推进：`asset_manifest` 仍为 `PRIVATE_CANDIDATE_PASS_PUBLIC_DEPLOY_BLOCKED`，且不存在最终公开授权素材记录；Sites 侧也尚未形成可部署版本或运行时环境。
- 本 run 未创建版本、未部署、未更改 Sites 环境、未上传 GitHub，符合“任务包整体完成后再上传”的约束。

### 下一步

- 由生产 Owner 在 Sites 控制面配置真实运行时环境与最终授权素材记录，并完成 Cloudflare 登录/授权；不得在仓库或对话中提供密钥。
- 完成后重跑 `npm run verify:owner-activation`；只有该证据通过，才恢复 S5-T3 的真实 OAuth/邮箱/会话回放。

## 本 run 结论（2026-08-09T07:03:09+10:00）

### 本地验收结果

- 重新读取 Sites 控制面：项目仍为 `active` 且当前操作身份具备 owner 权限；访问策略仍为私有自定义访问，未保存任何版本、预览/生产 URL 仍为空，生产环境变量仍为空。
- 修复 `scripts/verify-owner-activation.mjs` 的证据脱敏边界：环境配置仅记录存在性与匹配结果；发件邮箱、运营者名称、隐私值、密钥片段、CLI 原始输出和绝对本机路径均不再写入 `13_evidence/owner_activation.json`。
- 新增 `npm run test:owner-activation`：2/2 通过，使用伪造密钥/邮箱/CLI 输出确认任何 sentinel 都不会出现在生成的 JSON 证据中。
- 以不加载生产变量的干净环境重新运行 `npm run verify:owner-activation`：预期返回 `BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK (17)`；真实剩余项仍是运行时配置、公开授权素材、生产回调/邮件/Turnstile 与真实回放证据，未被弱化为 PASS。
- 未创建 Sites version、未部署、未变更 Sites 环境或访问策略、未上传 GitHub。

### 下一步

- 在 Sites 控制面实际配置完成且最终公开授权素材记录就绪后，重跑本预检；仅当风险清空后才能进入 `S5-T3`。
- 将真实 Google、邮件、Turnstile 与跨设备 E2E 作为独立生产证据执行，不得以本地预检替代。
