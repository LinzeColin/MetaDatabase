# VPS3 第三方生产验收

本文件把任务包的七项生产条件落实为可重复的验收步骤。它不替代真实网址、真实邮箱验证、独立执行的重新部署或第三方判断；本地构建、HTTP 200、截图和 fixture 都不能单独签发生产通过。

## 前提

1. 复审者在 `PWB_BASE_URL` 指向的真实网址中自行注册两个一次性账户 A/B，完成邮件验证并分别记录 ISO 时间：`PWB_TEST_ACCOUNT_A_VERIFIED_AT`、`PWB_TEST_ACCOUNT_B_VERIFIED_AT`。
2. A/B 的邮箱和密码仅通过本机环境变量提供，绝不写入仓库、日志或交付物。
3. 复审者独立保留一次部署回执（例如 Coolify deployment ID）及其 UTC 完成时间；生产代码和本测试不会代替该操作。
4. 使用仓外、私有的临时状态文件，例如 `/private/tmp/pwb-vps3-redeploy-acceptance.json`。它只在预部署与后部署之间保存随机测试记录 ID，成功后会删除。

## 命令

先验证公共表面（不写数据）：

```bash
PWB_BASE_URL=https://mydairy.linzezhang.com npm run accept:vps3:public
```

在同一终端私密地导出账户变量与真实注册见证后，运行预部署阶段：

```bash
export PWB_BASE_URL='https://mydairy.linzezhang.com'
export PWB_TEST_ACCOUNT_A_EMAIL='...'
export PWB_TEST_ACCOUNT_A_PASSWORD='...'
export PWB_TEST_ACCOUNT_A_VERIFIED_AT='2026-08-21T00:00:00Z'
export PWB_TEST_ACCOUNT_B_EMAIL='...'
export PWB_TEST_ACCOUNT_B_PASSWORD='...'
export PWB_TEST_ACCOUNT_B_VERIFIED_AT='2026-08-21T00:00:00Z'
export PWB_REDEPLOY_STATE_FILE='/private/tmp/pwb-vps3-redeploy-acceptance.json'
npm run accept:vps3:pre-redeploy
```

随后由复审者在 VPS3/Coolify 独立完成一次应用重新部署，并确认 `/api/health` 恢复。部署完成后运行：

```bash
export PWB_REDEPLOYMENT_WITNESS='coolify-deployment-id-or-independent-receipt'
export PWB_REDEPLOYED_AT_UTC='2026-08-21T00:10:00Z'
npm run accept:vps3:post-redeploy
```

生产阶段只使用一个桌面浏览器项目，避免两个浏览器配置同时写同一份重部署状态。JSON 结果仅落在已忽略的 `vps3-acceptance-output/`。

## 七项映射与通过规则

| 任务包条件 | 可复核证据 |
| --- | --- |
| 1. 新账户、邮件验证、登录 | 复审者的真实注册/邮箱回执 + 服务器会话 `emailVerified=true` |
| 2. A 待办刷新、登出重登、第二浏览器仍在 | `two-account.spec.ts` 第一项 |
| 3. B 看不到 A 记录和图片 | 模块循环和私有文件 404 断言 |
| 4. 每个模块新增与读回 | 11 个 canonical resource 的循环写入/读取/隔离 |
| 5. A 可读上传图片、B 不可读 | multipart PNG 上传、字节读回、B 404 |
| 6. 重新部署后记录和图片仍在 | `pre-redeploy` 创建状态，独立部署后 `post-redeploy` 读取并清理 |
| 7. 健康端点 | `ready=true`、`postgresql`、`vps3-filesystem` 精确断言 |

只有真实注册与邮件验证回执、两阶段命令、外部部署回执和全部 Playwright 断言都通过时，才能写“生产验收通过”。缺少任一项时结论是 `NOT_ACCEPTED`，不是部分 PASS。
