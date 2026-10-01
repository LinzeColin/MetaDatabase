# 阅迁规格（一页）

## 要解决什么问题

微信读书里的笔记、划线、想法分散，换设备或换工具就丢。阅迁让用户建一个账户，把这些笔记长期、加密地存起来，能跨设备同步、搜索、导出，随时可以删干净。

## 给谁用

有微信读书笔记、希望迁移或长期保存的个人用户（多租户，账户之间严格隔离）。

## 明确不做

- 不把微信读书密钥写进 URL、日志、状态、行为事件或导出文件；只存不可逆指纹和账户级加密凭据。
- 运行期不调用模型，不依赖 Agent 与 Token。
- 不提供公开管理子域；不因邮箱相同自动合并账户。
- 不把本地测试当作生产可用证据；真实密钥出现在聊天、工单或日志里一律视为泄露。
- 不用 `npx wrangler deploy` 裸部署（会清空线上变量）。

## 验收判据（每条可自动检查）

| 判据 | 检查 |
|---|---|
| 核心、账户、运维、安全与静态页面 | `cd WeReadPort && npm ci --ignore-scripts --no-audit --no-fund && npm run verify:integration` |
| 全局中文与 README 承诺 | `npm run verify`（含 `scripts/check-zh-cn.js`）；`service/tests/test_platform_ops.py` 要求 README 含「运行期不调用模型」与「Agent 与 Token 依赖均为零」 |
| 公开入口存活 | `curl -fsS https://weread.linzezhang.com/healthz` 返回 `"status":"ALIVE"` |
| 依赖就绪（SQLite、R2、worker 心跳、OAuth） | `curl -fsS https://weread.linzezhang.com/readyz` 返回 `"status":"READY"`；503 即未就绪 |
| 账户服务与发布身份 | `curl -fsS https://weread-api.linzezhang.com/readyz` 返回 `"ready":true` 且 `version` 与 `src/core/constants.js` 的 `APP_VERSION` 一致 |
| 业务判据：同步后能读回微信读书笔记正文 | Owner 手动触发 `tests/browser/production_account_e2e.py`（需 `WRP_E2E_WEREAD_KEY`） |

## 已知坑

- 部署 Worker 只走 `npm run deploy:cloudflare`；裸跑 `wrangler deploy` 会清掉线上 8 个变量（2026-08-12 发生过一次，靠 `wrangler rollback` 约 3 分钟恢复）。
- `OAuth` 与 R2 的真实可用性只能由目标环境证据裁决；本机测试不能冒充。
- 真实账户 E2E 中途失败且删号也失败时，Owner 的微信读书密钥会留在孤儿账户里（`CREDENTIAL_IN_USE`），所以只手动跑。
- 7×24 是目标，不是已发生的长期运行证明。
- 文档中文检查 `scripts/check-zh-cn.js` 会读 README：新增英文大写标题或内部英文标识会报错。
