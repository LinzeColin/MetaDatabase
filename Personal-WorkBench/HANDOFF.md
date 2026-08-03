# Personal-WorkBench — S2 本地完成交接

## 当前目标

“胡楚靓工作台”已完成 S2 的本地可验证实现：认证入口、账户边界、D1 迁移、服务端租户 CRUD、私有 R2 对象链与浏览器安全头均已纳入源码。当前 run 没有保存 Sites、部署、GitHub push 或真实用户/供应商测试；下一 run 不进入 S3，除非明确切换阶段。

## 当前状态

- 阶段：`S2_LOCAL_IMPLEMENTATION_COMPLETE`
- Saved Candidate：`NOT_RUN`。未配置也未读取 Google、邮件、Turnstile、最终 origin 或任何账户材料；真实回调、真实邮箱和真实 A/B 账户隔离尚未发生。
- 公开 Deploy：仍为 `BLOCKED_ASSET_RIGHTS`。最终获授权 Hello Kitty 原图及权利记录未进入 workspace，当前私有参考裁切素材不可用于公开发布。
- Sites：仍是 S0 的独立、Owner-only、未 Deploy Site；绑定逻辑名称仍为 D1=`DB`、R2=`FILES`。
- 依赖风险：`npm audit --omit=dev --audit-level=critical` 当前报告 7 项（4 moderate / 3 high，0 critical），修复建议会强制改动任务包锁定的 Next/Drizzle 链路；本轮未执行破坏性自动升级。

## 已完成

- `drizzle/0001_auth_and_product.sql` 与任务包冻结文件 SHA-256 一致：`9e353bf3148267cd3b6e86654643a202321b1c3ef361b6590944e0d237fee497`。`0002_s2_tenant_indexes.sql` 仅为 task-pack 漏掉 tenant-first 索引的 `outbox_events` 与 `security_audit_events` 添加索引，不修改冻结 `0001`。
- Better Auth 和 Drizzle adapter 精确锁定为 `1.6.25`；配置包含邮箱验证、12–128 位密码、密码重设撤销会话、Google 最小 scope、禁用隐式绑定、显式 Google 绑定入口、D1 限流、Turnstile 和安全 Cookie。
- 认证 UI 已提供登录、注册、忘记/重设密码、验证邮箱与账户设置；Turnstile 公钥仅由 `/api/auth/public-config` 返回，永不返回 secret 或供应商配置。
- `app/api/workbench/` 覆盖 14 个多记录资源和一个 profile 单例资源。所有写入口先验服务端已验证 session，拒绝任意嵌套的客户端 tenant/owner 字段，使用参数化 `user_id` 谓词、幂等键和无正文审计行。
- 私有文件对象键固定为 `users/{userId}/{module}/{objectId}`；图片做 MIME、魔数、尺寸、像素上限和 10 MiB 校验，读取/替换/删除先按 D1 `id + user_id` 验证所有权。
- `worker/index.ts` 已统一设置 CSP、anti-frame、nosniff、referrer、permissions 与 cross-origin headers；仅 Turnstile 使用的 `challenges.cloudflare.com` 为允许的第三方表面。
- 五条冻结 reference 路线未改动：结构回归和三轮视觉验收仍为 5/5 PASS。旧的未使用 ChatGPT 头部认证辅助文件已移除，避免与 Better Auth 形成双重身份来源。

## 证据与命令

- `13_evidence/schema.json`：空库、重复执行、索引和触发器为 `PASS_LOCAL_SQLITE`（25 tables / 4 triggers）。
- `13_evidence/auth.json`、`13_evidence/auth-saved.json`、`13_evidence/auth-local-runtime.json`：本地认证契约通过；本地 Workers 无材料状态实测 `/api/auth/get-session=503`、`/api/auth/public-config=200`；Saved Candidate 明确 `NOT_RUN`。
- `13_evidence/tenant_matrix.json`：15 个资源的 server-side tenant contract；SQLite A/B 读写隔离测试通过。
- `13_evidence/r2.json`：私有对象键、校验、所有权优先与幂等合约通过；真实 R2 round trip `NOT_RUN`。
- S2 命令：`npm run test:s2` 通过（`test:auth-saved` 预期输出 `NOT_RUN`）；`npm run check`、`npm test`、`npm run test:visual`、`git diff --check` 通过。
- `RUN_CONTRACT_S2.md` 固化范围、停止条件和真实外部验收边界。

## 关键文件

- 身份与会话：`server/auth/`、`app/api/auth/[...all]/route.ts`、`app/auth/`、`app/account/page.tsx`
- 数据隔离：`server/security/tenant.ts`、`server/data/`、`app/api/workbench/[resource]/`
- 私有文件：`server/files/`、`app/api/workbench/files/`
- 迁移与索引：`drizzle/0001_auth_and_product.sql`、`drizzle/0002_s2_tenant_indexes.sql`
- 安全头：`worker/index.ts`
- 验收：`scripts/verify-*.mjs`、`tests/*contract*`、`tests/schema.test.mjs`、`tests/tenant-isolation.test.mjs`、`tests/r2.test.mts`

## 下一步与外部验收门

1. 维持当前 S2 状态并等待下一阶段指令；不要将本地合约 PASS 写成真实 Google/邮件/Turnstile 或真实用户 PASS。
2. Saved Candidate 阶段需要由运行平台内配置完成后（不在聊天中提供任何值）重新执行 D1 迁移、真实 Google/邮件/Turnstile 流程、真实 A/B IDOR、R2 upload/read/replace/delete 和跨设备会话验证。
3. S3 只可在明确切换阶段后开始，并必须继续保持所有 `?reference=` 路线无登录态、Cookie、迁移或调试信息。
4. 公开 Deploy 前仍必须在同容器/裁切框内提供最终获授权 Hello Kitty 原图与权利记录；不得以现有裁切素材或本地测试替代。
