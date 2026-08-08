# S3-T3 Run Contract — 账户导出/删除/隐私链路本地基线

## 目标

补齐账户页的“导出—删除—隐私同意”链路的本地可验证基线：包括数据导出快照、可撤销删除、隐私同意状态/时间线，以及前端状态流与后端接口对齐。

## 最小相关范围

- `server/data/account-lifecycle.ts`：新增/更新隐私状态与删除状态逻辑与错误映射。
- `app/api/account/export/route.ts`：导出快照接口。
- `app/api/account/delete/route.ts`：删除状态查询与 request/confirm/undo 处理。
- `app/api/account/privacy/route.ts`：隐私状态查询与设置接口。
- `app/account/page.tsx`：页面状态联动、导出/删除/隐私按钮、提示文案。
- `app/globals.css`：`account-*` 页面样式补齐。
- `server/http/api.ts`：账户链路错误转码。
- `tests/privacy.test.mts`、`tests/account-lifecycle.test.mts`、`tests/`.
- `package.json`：新增 `test:privacy`、`test:account-lifecycle` 脚本。

## 明确不在本 run 的范围

- 未触及真实 OAuth / 邮件验证 / Turnstile 网关重跑。
- 未做离线 outbox、真实 R2 物理清理确认、跨设备并发冲突恢复实验。
- 未修改 `drizzle/*` 和 `worker/index.ts` 核心运行时配置。

## 验收与停止条件

- 本地验证全部通过：
  - `npm run test:privacy`
  - `npm run test:account-lifecycle`
  - `npm run typecheck`
- `RUN_CONTRACT_S3_T3` 需输出 `PASS_LOCAL_ACCOUNT_LIFECYCLE` 证据前置条件。
- 如任一用例失败，不推进下一阶段；回退该阶段并复测。

## 风险与未决

- 账户删除成功后，当前行为会删除用户主体与关联数据；未加入真实恢复演练环境（本次为本地验证）。
- 导出口令仍采用本地 mock 储存展示，不作为生产持久化恢复界面。
- 隐私提示文案与“已开启/已撤回”口径在 UI 交互层仍可继续精修。

## 结果（预计）

- 阶段状态：`PASS_LOCAL_ACCOUNT_LIFECYCLE`
- Saved Candidate：`NOT_RUN`
- 公开 Deploy：`BLOCKED_ASSET_RIGHTS`（与 S3-T2 口径保持一致）
