# Run Contract — S5-T3 生产 Deploy 与回滚演练预检

## 2026-08-09 执行模式增补（当前真源）

`ACCEPTANCE_SEQUENCE_ADDENDUM.json` 已将当前 S5-T3 定义为：在 S5-T2 后进行的
`controlled_private_deploy`，受众始终为 `controlled_private`。本增补优先解释下方历史预检
范围，不修改冻结任务包、不授予公开 audience，也不替代 S6-T1 的独立最终验收。

- 本轮仅部署已保存的私有 Version #7；访问控制保持 owner/custom、1 名允许用户、0 群组、0 外部访客。
- 已实测 Version #7 私有部署成功、Version #6 私有回滚成功，并立即恢复 Version #7；未改变公开受众。
- 已验证九个主菜单渲染不同内容、记账空金额有可见反馈、经期记录明确暴露敏感内容跨设备保存同意门；没有读取或写入任何用户内容。
- Google 授权已到达账户选择页；未选择个人账户。真实邮箱/Google 回调、A/B 隔离、跨设备历史、D1/R2 对账及负向 provider/recovery 回放仍需受控测试账号，当前均为 `NOT_RUN`。
- 对私有 Origin 的裸 HTTP 探针得到 401，原因是 Sites 私有访问门；它不能被解释为应用路由异常，原始结果保留在 `13_evidence/production-smoke-run.json`。

## 目标

在不触发实际生产变更的前提下，建立 `S5-T3` 的可复现预检链路：
- 将任务包要求的生产命令接入本地脚本；
- 输出生产与运维投影的阶段证据文件；
- 明确阻断项与可执行恢复动作，避免将“脚本执行”误判为生产 PASS。

## 最小相关范围

- `scripts/verify-production-smoke.mjs`：生产真实链路可达性与身份边界预检脚本。
- `scripts/verify-ops-projection.mjs`：status/OVH/Private-Database 投影前置红线与适配器可达性预检脚本。
- `package.json`：新增可复用命令入口。
- `13_evidence/production.json`：`S5-T3` 证据槽位。
- `13_evidence/ops_projection.json`：`S5-T4` 证据槽位。
- `13_evidence/production-smoke-run.json`（脚本写入）：生产链路执行快照。
- `13_evidence/ops_projection-run.json`（脚本写入）：运维投影执行快照。
- `RUN_CONTRACT_S5_T3.md`：本阶段执行合同。

## 明确不在本 run 范围（本 run）

- 不执行任何 Sites 控制台 Deploy、回滚和重放动作。
- 不在本地模拟真实 OAuth/邮件/Google 回放主流程；该阶段仅做可复现门槛检查。
- 不改动产品代码与数据库 schema。

## 本 run 立即执行清单

1. 准备并确认基础环境变量（示例）：
   - `SITES_PRODUCTION_ORIGIN` 或 `PRODUCTION_SMOKE_ORIGIN`（生产/候选访问域）
   - `SITES_SMOKE_EMAIL` / `SITES_SMOKE_PASSWORD`
   - `SITES_SMOKE_GOOGLE_EMAIL`
   - `APP_ORIGIN`
2. 将本 run 命令纳入最小执行链：
   - `npm run verify:production-smoke`
   - `npm run verify:ops-projection`
3. 产物检查：
   - `13_evidence/production-smoke-run.json`
   - `13_evidence/production.json`
   - `13_evidence/ops_projection-run.json`
   - `13_evidence/ops_projection.json`
4. 输出本 run 结论：
   - `RUN_CONTRACT_S5_T3.md` 记录阻断、证据变更与下一步。

## 验收与停止条件

- `npm run verify:production-smoke` 或 `npm run verify:ops-projection` 失败时，状态必须为阻断（例如 `BLOCKED_*`）并写入对应证据；
- 当且仅当以下全部满足时，可进入 `PASS` 判定：
  - 生产 Origin 可达，鉴权页/关键接口基础可达；
  - 真实账户凭据、生产 OAuth 邮箱回放环境齐备；
  - `status/OVH/Private-Database` adapter endpoint 已配置且可达；
  - `13_evidence/production.json` 与 `13_evidence/ops_projection.json` 的 `status` 进入本阶段通过状态。
- 任何阻断项不得降级为可复用 PASS；不以脚本运行成功即作为生产成功证据。

## 本 run 结论（2026-08-06T22:45:00.000Z）

### 本地执行结果（本 run）

- 执行命令：
  - `npm run dev -- --port 3000`（本地站点启动）
  - `ALLOW_HTTP_SMOKE_ORIGIN=1 SITES_PRODUCTION_ORIGIN=http://localhost:3000 APP_ORIGIN=http://localhost:3000 npm run verify:production-smoke`
- 本次新增改动：`scripts/verify-production-smoke.mjs` 支持受控本地 HTTP 预检模式（`ALLOW_HTTP_SMOKE_ORIGIN=1`），在本地开发环境可复现路由与鉴权边界。
- `13_evidence/production-smoke-run.json`：`BLOCKED_LOCAL_PRODUCTION_SMOKE_PRECHECK`，`risks=3`，核心阻断为：
  1. `/api/workbench/profile` 未返回 401/403，实际返回 `503`（本地运行时后端服务暂时不可用，需继续排查 profile 鉴权/会话依赖链路）；
  2. 未注入真实外部账号凭据（`SITES_SMOKE_EMAIL` / `SITES_SMOKE_PASSWORD`）；
  3. 未注入 Google 回放账号（`SITES_SMOKE_GOOGLE_EMAIL`）。
- 本次已复核到的增量价值：本地 Auth 页面与公开配置接口都在本地可达，不再受外部 `example.com` 可达性噪声干扰，便于下一步在生产域名就绪后聚焦真实回放阻断。

### 下一步

## 验收记录（2026-08-06T00:00:00.000Z）

## 验收记录（2026-08-05T22:45:36.421Z）

### 本地执行结果（本 run）

- 执行命令：
  - `TASKPACK_ROOT=/Users/linzezhang/Downloads/TaskPack/Personal-WorkBench/胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8 ALLOW_HTTP_SMOKE_ORIGIN=1 APP_ORIGIN=http://localhost:3000 SITES_PRODUCTION_ORIGIN=http://localhost:3000 PRODUCTION_ORIGIN=http://localhost:3000 SITES_SMOKE_GOOGLE_EMAIL=google-smoke@example.com SITES_SMOKE_EMAIL=smoke-test@example.com SITES_SMOKE_PASSWORD=placeholder-password OPS_ADAPTER_TOKEN=unit-test-token npm run verify:production-smoke`
  - `TASKPACK_ROOT=/Users/linzezhang/Downloads/TaskPack/Personal-WorkBench/胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8 ALLOW_HTTP_SMOKE_ORIGIN=1 APP_ORIGIN=http://localhost:3000 SITES_PRODUCTION_ORIGIN=http://localhost:3000 PRODUCTION_ORIGIN=http://localhost:3000 SITES_SMOKE_GOOGLE_EMAIL=google-smoke@example.com SITES_SMOKE_EMAIL=smoke-test@example.com SITES_SMOKE_PASSWORD=placeholder-password OPS_ADAPTER_TOKEN=unit-test-token npm run verify:ops-projection`
- `13_evidence/production.json`：状态 `BLOCKED_LOCAL_PRODUCTION_SMOKE_PRECHECK`，`profile` 鉴权边界已修复为 401，核心阻断仅剩 `生产真实 OAuth/邮件注册/找回/会话链路未执行`。
- `13_evidence/production-smoke-run.json`：状态 `BLOCKED_LOCAL_PRODUCTION_SMOKE_PRECHECK`，`risks=1`。
- `13_evidence/ops_projection-run.json`：`status=BLOCKED_LOCAL_OPS_PROJECTION`，`risks=1`。
- `13_evidence/ops_projection.json`：状态更新为 `BLOCKED_LOCAL_OPS_PROJECTION`，原因仅 `S5-T3 生产烟雾（包含链路预检）未成功通过，不建议先执行 ops projection。`

### 下一步

- 保持本 run 验证产物不降级到 PASS，继续推进真实生产 OAuth/邮箱注册/找回/会话链路执行；
- 完成 `SITES_PRODUCTION_ORIGIN` 对应真实发布域后在生产域复跑两条验证命令。

## 验收记录（2026-08-06T00:00:00.000Z）

### 本地执行结果（本 run）

- `npm run verify:production-smoke`（阻断）：默认缺少生产真实 Origin/外部账号，保留 `BLOCKED_LOCAL_PRODUCTION_SMOKE_PRECHECK`。
- `npm run verify:ops-projection`（阻断）：缺少 adapter 可达性与 `production.json` 真实链路前置，同样保留阻断状态。
- `13_evidence/production.json`、`13_evidence/production-smoke-run.json` 已补充模板与执行快照。
- `13_evidence/ops_projection.json`、`13_evidence/ops_projection-run.json` 已补充模板与执行快照。

### 下一步

- 完成 `S5-T2` 门槛（Owner Activation）并配置生产生产 Origin 与回放账号后，再次执行：
  - `npm run verify:production-smoke`
  - `npm run verify:ops-projection`
- 达到 `PASS_LOCAL_PRODUCTION_SMOKE_PRECHECK` 后转入真实回放（注册、OAuth、找回、第二设备、A/B）与回滚演练。

## 验收记录（2026-08-06T22:18:00.000Z）

### 本地执行结果（本 run）

- 执行命令：
  - `TASKPACK_ROOT=/Users/linzezhang/Downloads/TaskPack/Personal-WorkBench/胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8 APP_ORIGIN=https://example.com SITES_PRODUCTION_ORIGIN=https://example.com SITES_SMOKE_EMAIL=smoke-test@example.com SITES_SMOKE_PASSWORD=placeholder-password SITES_SMOKE_GOOGLE_EMAIL=google-smoke@example.com npm run verify:production-smoke`
  - `TASKPACK_ROOT=/Users/linzezhang/Downloads/TaskPack/Personal-WorkBench/胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8 APP_ORIGIN=https://example.com SITES_PRODUCTION_ORIGIN=https://example.com PRODUCTION_ORIGIN=https://example.com npm run verify:ops-projection`
- `13_evidence/production-smoke-run.json`：状态 `BLOCKED_LOCAL_PRODUCTION_SMOKE_PRECHECK`，阻断 `2` 项
  1. `/api/workbench/profile` 未返回 401/403 鉴权边界不满足预期（实际 404）
  2. `/api/public-config` 返回 404（未命中客户端配置接口）
- `13_evidence/ops_projection-run.json`：状态 `BLOCKED_LOCAL_OPS_PROJECTION`，阻断 `5` 项
  1. 三个投影适配器 endpoint 均 404（`/api/ops/status`、`/api/ops/ovh`、`/api/ops/pdb`）
  2. `drizzle/0001_auth_and_product.sql` 与 `server/security/audit.ts` 的静态脱敏/文件对象边界红线未全部闭环
     - `audit_schema_guard: false`
     - `schema_disallows_file_objects_leak: false`
  3. 由于 `production.json` 未通过，`ops_projection` 阻断继续保留
- `13_evidence/production.json` 与 `13_evidence/ops_projection.json` 已重写为上述本轮阻断结果。

### 下一步

- 确认真实生产域名并完成生产端路由发布后，先验证：
   - `GET /` 返回站点
   - `GET /auth/sign-in`、`/auth/sign-up`、`/auth/forgot-password`、`/auth/verify-email`
  - `GET /api/auth/public-config` 为 200
   - `GET /api/workbench/profile` 返回 401/403（未鉴权边界）
- 生产域名可达并路由可用后，重新执行 `npm run verify:production-smoke`；
- 通过后，再配置三类 ops 适配器 `STATUS_ADAPTER_BASE` / `OVH_ADAPTER_BASE` / `PRIVATE_DATABASE_ADAPTER_BASE`；
- 然后复跑 `npm run verify:ops-projection` 直至 `status` 进入 `PASS_LOCAL_OPS_PROJECTION_PRECHECK`。

## 验收记录（2026-08-05T22:13:36.300Z）

### 本地执行结果（本 run）

- 执行命令：
  - `TASKPACK_ROOT=/Users/linzezhang/Downloads/TaskPack/Personal-WorkBench/胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8 APP_ORIGIN=https://example.com SITES_PRODUCTION_ORIGIN=https://example.com SITES_SMOKE_EMAIL=smoke-test@example.com SITES_SMOKE_PASSWORD=placeholder-password SITES_SMOKE_GOOGLE_EMAIL=google-smoke@example.com npm run verify:production-smoke`
  - `TASKPACK_ROOT=/Users/linzezhang/Downloads/TaskPack/Personal-WorkBench/胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8 APP_ORIGIN=https://example.com SITES_PRODUCTION_ORIGIN=https://example.com PRODUCTION_ORIGIN=https://example.com npm run verify:ops-projection`
- `13_evidence/production-smoke-run.json`：`BLOCKED_LOCAL_PRODUCTION_SMOKE_PRECHECK`（`2` 项）
  1. `/api/workbench/profile` 未返回 401/403（实际 `404`）
  2. `/api/auth/public-config` 未返回 200（实际 `404`）
- `13_evidence/ops_projection-run.json`：`BLOCKED_LOCAL_OPS_PROJECTION`（`4` 项）
  1. `status/ovh/pdb` 三个 adapter endpoint 不可达（均 `404`）
  2. `production.json` 未通过，继续保留预检联动阻断
  3. 静态红线校验由误判修正：`audit_schema_guard` 与 `schema_disallows_file_objects_leak` 已恢复为 `true`
- 当前结论：本 run 已收敛到“仅生产域名与三类 adapter 可达性”阻断，静态本地脱敏与租户对象键边界门槛通过。

### 下一步

- 先完成真实生产域名与路由发布（鉴权页与 `api/ops/*`、`api/auth/public-config` 可达），复跑 `npm run verify:production-smoke`；
- 继续补齐 `STATUS_ADAPTER_BASE` / `OVH_ADAPTER_BASE` / `PRIVATE_DATABASE_ADAPTER_BASE` 到真实可达 endpoint；
- `production.json` 与 `ops_projection.json` 进入对应 PASS 后再推进真实回放与回滚演练。

## 验收记录（2026-08-06T01:20:00.000Z）

### 本地执行结果（本 run）

- 已新增本地运维投影端点（不改变 UI 与数据模型）：
  - `app/api/ops/status/route.ts`
  - `app/api/ops/ovh/route.ts`
  - `app/api/ops/pdb/route.ts`
- 新增运维鉴权共享模块：
  - `server/security/ops.ts`
- 新增运维投影契约测试：
  - `tests/ops-projection-contract.test.mjs`
- 已执行验证：
  - `node --import ./tests/register-cloudflare-workers-loader.mjs --test tests/ops-projection-contract.test.mjs`
- 验证结果：
  - 本地端点鉴权逻辑通过测试，`OPS_ADAPTER_TOKEN` 配置下返回探针 payload；缺 token 时返回 503 阻断信号。

### 本地验收状态（当前）

- 在 `example.com` 复用域仍会命中外站页面，`verify:ops-projection` 与 `verify:production-smoke` 仍受生产域路由与认证链路外部条件约束；
- 在生产域实际发布后，若配合 `OPS_ADAPTER_TOKEN`（或 `OPS_PROJECTION_TOKEN`）并将 `SITES_PRODUCTION_ORIGIN` 指向生产站点，预期 `/api/ops/*` 将不再返回 404；
- 当前阻断仍保留在：
  - `production.json`（生产鉴权页/公用配置路径未通过）
  - `ops_projection`（生产 adapter 外部可达性）

### 下一步

- 外部完成生产域名与路由发布后，优先在目标域下执行：
   - `npm run verify:production-smoke`
  - `npm run verify:ops-projection`
- 在生产环境端点可达后，再进入真实回放与回滚演练（S5-T4）。

## 验收记录（2026-08-06T22:16:25.553Z）

### 本地执行结果（本 run）

- 执行命令：
  - `TASKPACK_ROOT=/Users/linzezhang/Downloads/TaskPack/Personal-WorkBench/胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8 APP_ORIGIN=https://example.com SITES_PRODUCTION_ORIGIN=https://example.com SITES_SMOKE_EMAIL=smoke-test@example.com SITES_SMOKE_PASSWORD=placeholder-password SITES_SMOKE_GOOGLE_EMAIL=google-smoke@example.com OPS_ADAPTER_TOKEN=unit-test-token npm run verify:production-smoke`
  - `TASKPACK_ROOT=/Users/linzezhang/Downloads/TaskPack/Personal-WorkBench/胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8 APP_ORIGIN=https://example.com SITES_PRODUCTION_ORIGIN=https://example.com PRODUCTION_ORIGIN=https://example.com OPS_ADAPTER_TOKEN=unit-test-token npm run verify:ops-projection`
- `13_evidence/production-smoke-run.json`：`BLOCKED_LOCAL_PRODUCTION_SMOKE_PRECHECK`（阻断 `2` 项）
  1. `/auth/*` 与 `/api/auth/public-config` 均访问 404（当前指向 `example.com` 非本项目发布域，属于外部环境阻断）
  2. `/api/workbench/profile` 非 401/403 鉴权边界（在当前外部域下返回 404）
- `13_evidence/ops_projection-run.json`：`BLOCKED_LOCAL_OPS_PROJECTION`（阻断 `4` 项）
  1. 三个适配器 endpoint 均 404：`/api/ops/status`、`/api/ops/ovh`、`/api/ops/pdb`
  2. `S5-T3` 未通过，因此按 gate 规则，`ops_projection` 保持阻断
- `13_evidence/production.json` 与 `13_evidence/ops_projection.json` 已更新为本次 run 的阻断原因与状态快照。

### 下一步

- 将 `SITES_PRODUCTION_ORIGIN`/`PRODUCTION_SMOKE_ORIGIN` 指向已发布的 Personal-WorkBench 生产域名后，重跑：
  - `npm run verify:production-smoke`
  - `npm run verify:ops-projection`
- 通过 `PASS_LOCAL_PRODUCTION_SMOKE_PRECHECK` 后进入真实回放前置（注册、Google/OAuth、找回、回调）；
- 通过生产烟雾后再逐步配置并验证三类 ops adapter endpoint 并复跑 `verify:ops-projection`。

## 验收记录（2026-08-05T23:02:50.000Z）

### 本地执行结果（本 run）

- 执行命令：
  - `cd Personal-WorkBench`
  - `npm run dev -- --port 3000`
  - `TASKPACK_ROOT=/Users/linzezhang/Downloads/TaskPack/Personal-WorkBench/胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8 ALLOW_HTTP_SMOKE_ORIGIN=1 APP_ORIGIN=http://localhost:3000 SITES_PRODUCTION_ORIGIN=http://localhost:3000 PRODUCTION_ORIGIN=http://localhost:3000 SITES_SMOKE_EMAIL=smoke-test@example.com SITES_SMOKE_PASSWORD=placeholder-password SITES_SMOKE_GOOGLE_EMAIL=google-smoke@example.com OPS_ADAPTER_TOKEN=unit-test-token npm run verify:production-smoke`
  - `TASKPACK_ROOT=/Users/linzezhang/Downloads/TaskPack/Personal-WorkBench/胡楚靓工作台_ChatGPT-Sites多用户SaaS最终开发任务包_v0.0.0.8 ALLOW_HTTP_SMOKE_ORIGIN=1 APP_ORIGIN=http://localhost:3000 SITES_PRODUCTION_ORIGIN=http://localhost:3000 PRODUCTION_ORIGIN=http://localhost:3000 SITES_SMOKE_EMAIL=smoke-test@example.com SITES_SMOKE_PASSWORD=placeholder-password SITES_SMOKE_GOOGLE_EMAIL=google-smoke@example.com OPS_ADAPTER_TOKEN=unit-test-token npm run verify:ops-projection`
- `13_evidence/production-smoke-run.json` 更新为 `BLOCKED_LOCAL_PRODUCTION_SMOKE_PRECHECK`，风险条数 `1`：
  - `生产真实 OAuth/邮件注册/找回/会话链路仍未执行，请由外部 Saved Candidate 与人工/自动化流程完成后回填。`
- `13_evidence/ops_projection-run.json` 更新为 `BLOCKED_LOCAL_OPS_PROJECTION`，风险条数 `1`：
  - `S5-T3 生产烟雾（包含链路预检）未成功通过，不建议先执行 ops projection。`
- `13_evidence/production.json` 与 `13_evidence/ops_projection.json` 均对应阻断状态（与本 run 快照一致）。
- 本地路由探针与运维端点健康指标：
  - `/`, `/auth/sign-in`, `/auth/sign-up`, `/auth/forgot-password`, `/auth/verify-email`: `200`
  - `/api/auth/public-config`: `200`
  - `/api/workbench/profile`: `401`（鉴权边界符合预期）
  - `/api/ops/status`：`200`
  - `/api/ops/ovh`：`200`
  - `/api/ops/pdb`：`200`

### 结论

- 当前阻断已回归到“未做真实生产链路回放”（OAuth/邮件注册/找回/会话）；
- 以当前证据为准，S5-T3 与 S5-T4 均保持阻断，但已移除本地服务与鉴权边界基础可达性的阻断项。

### 下一步

- 外部完成真实发布域、真实凭据与 OAuth/邮件回放后，按顺序重跑：
  - `npm run verify:production-smoke`
  - `npm run verify:ops-projection`
- S5-T3 通过后推进真实回放与回滚演练（S5-T4）。
