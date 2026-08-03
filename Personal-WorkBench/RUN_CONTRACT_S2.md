# S2 Run Contract — 认证、租户隔离与私有对象链

## 目标

在不改变五条 `?reference=` 冻结视觉路由的条件下，完成本地可验证的多账户认证、D1 租户边界和私有 R2 对象链；所有生产或真实账户副作用继续留在 Saved Candidate 门后。

## 最小范围

- `drizzle/`、`db/`：Better Auth 1.6.25 兼容表、业务表与 tenant-first 索引。
- `server/auth/`、`app/auth/`、`app/account/`、`app/api/auth/`：Google、邮箱注册/验证、登录、找回/重设、显式账户绑定及会话配置。
- `server/data/`、`server/files/`、`app/api/workbench/`：服务端 session-first 的租户 CRUD、幂等和私有文件读写替换删除。
- `worker/index.ts`：CSP 与浏览器安全头；仅允许 Turnstile 所需第三方域名。
- `tests/`、`scripts/`、`13_evidence/`：迁移、认证、租户、R2、私有视觉回归和本地 Workers 探测。

## 明确不在范围

- Sites Save/Deploy、GitHub push、真实 Google OAuth、真实收件邮箱、真实 Turnstile token、真实 A/B 账户和生产 D1/R2 数据。
- 任何 Secret、Cookie、Token、密码或用户正文的读取、记录、复制或传输。
- 最终 Hello Kitty 获授权原图和公开发布；该权利门仍由 S1 的 `BLOCKED_ASSET_RIGHTS` 控制。

## 验收与停止条件

- 本地：`npm run test:s2`、`npm run test:auth-runtime`（在 `npm run dev` 运行期间）、`npm test`、`npm run test:visual`、`npm run check` 和 `git diff --check` 均通过。
- 状态真实标注：`test:auth-saved` 输出 `NOT_RUN`，它不是 Saved Candidate PASS。
- 公开或 Saved Candidate 验收前，必须在运行平台设置内配置 Google、邮件、Turnstile 与最终 origin，并在不暴露其值的前提下用真实 A/B 用户重新验证；不得以本地 mock 或 HTTP 200 替代。

## 结果

- 状态：`LOCAL_IMPLEMENTATION_COMPLETE`
- Saved Candidate：`NOT_RUN`
- 公开 Deploy：`BLOCKED_ASSET_RIGHTS`
