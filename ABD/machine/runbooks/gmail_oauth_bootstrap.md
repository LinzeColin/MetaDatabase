# ABD Gmail OAuth Bootstrap｜S00/P04

> 当前状态：`CONSENT_NOT_REQUESTED`；Gmail 模块关闭；核心任务继续；S00/P04 未生成授权链接、未访问账户、未接收或保存任何 token。

## 1. 目的与边界

本 runbook 定义未来运行期的单一账户 Gmail 授权流程。它不是可直接执行的授权链接，也不是授权成功证明。只有 Gmail 收集器、回调安全、加密令牌存储、方法白名单、恢复测试和当前费用/配额核验全部就绪后，系统才可以在上下文内让所有者打开 Google 系统浏览器页面完成一次明确 consent。

未同意、取消、scope 不匹配、token 失效、应用状态未知或任何激活门未通过时：只关闭 Gmail 自动证据模块，开发、构建、部署准备、市场与模型工作、影子评估、非 Gmail 证据账本和 Stage Review 继续执行各自独立门。

## 2. 权限真实含义

请求的唯一 scope 是 `https://www.googleapis.com/auth/gmail.modify`。Google 将其描述为可读取、撰写和发送邮件，但不允许绕过垃圾箱即时永久删除。ABD 需要它来读取邮件/附件并调用 `messages.trash`；这只是必要性说明，不代表 scope 天然足够窄。应用层必须独立拒绝发送、草稿、导入、插入、设置修改和永久删除。

`https://mail.google.com/` 永不请求，因为它允许包括即时永久删除在内的更宽能力。任何返回 scope 多于或少于精确 `gmail.modify` 集合的授权结果都不得激活 Gmail。

## 3. 未来运行期前置门

必须全部通过：

1. Gmail 模块和方法白名单已有运行制品与测试证据。
2. Google Cloud 项目、OAuth client 类型、受众、Publishing 状态和验证要求已核验。
3. 生产 redirect URI 是所有者控制域名上的精确 HTTPS URI；不得使用通配符或未授权域名。
4. `state` 是服务端保存、一次性、短时且无个人信息的随机值；回调必须恒时比对并消费。
5. 使用 PKCE `S256`，`code_verifier` 只存在于短时服务端会话。
6. client credential 和 token 加密静态存储于仓库之外；禁止写入日志、证据、Git、命令历史或 URL。
7. 当前 Gmail API 费用、配额和 OAuth 应用状态仍满足 A$0 新增现金门。
8. 已准备一封受控测试邮件，可验证读取、归档、移入垃圾箱、恢复和 SHA-256 一致性；不使用真实关键证据做首次测试。

## 4. 授权请求合同

```json
{
  "runbook_contract_id": "ABD-GMAIL-OAUTH-BOOTSTRAP-S00-P04",
  "current_state": "CONSENT_NOT_REQUESTED",
  "requested_scopes_exact": [
    "https://www.googleapis.com/auth/gmail.modify"
  ],
  "forbidden_scopes": [
    "https://mail.google.com/"
  ],
  "request_parameters": {
    "access_type": "offline",
    "include_granted_scopes": false,
    "prompt": "CONSENT_ONLY_FOR_INITIAL_OR_OWNER_EXPLICIT_REENABLE",
    "response_type": "code",
    "state": "REQUIRED_SINGLE_USE_SERVER_SIDE",
    "pkce": "S256_REQUIRED",
    "redirect_uri": "EXACT_HTTPS_OWNER_CONTROLLED_URI"
  },
  "allowed_methods": [
    "users.getProfile",
    "users.history.list",
    "users.messages.list",
    "users.messages.get",
    "users.messages.attachments.get",
    "users.messages.trash",
    "users.messages.untrash"
  ],
  "always_denied_methods": [
    "users.drafts.create",
    "users.drafts.send",
    "users.messages.batchDelete",
    "users.messages.delete",
    "users.messages.import",
    "users.messages.insert",
    "users.messages.send",
    "users.settings.*",
    "users.threads.delete"
  ],
  "degraded_action": "DISABLE_GMAIL_MODULE_CONTINUE_CORE",
  "secret_material_in_runbook": false,
  "external_action_performed_in_s00_p04": false
}
```

`include_granted_scopes=false` 是 ABD 的显式收窄选择：本产品只有一个 Gmail scope，禁止把同一 Google 项目历史上其他 grant 聚合进本次 receipt。未来增加 scope 必须独立修改 Canonical/授权/预算/验收合同，不能静默增量授权。

## 5. 所有者未来看到的一次动作

系统只在全部前置门通过后显示一张中文授权说明卡，说明：

- 请求方和所有者控制的域名；
- 精确 scope 及其比产品实际使用更宽的风险；
- ABD 实际允许和永远禁止的方法；
- token 加密位置类别、撤销入口和拒绝后的影响；
- “同意”只开启后续验证，不会立刻移动任何邮件；
- “拒绝/取消”只关闭 Gmail，其他安全任务继续。

链接必须由运行时短时生成并直接交给系统浏览器，不得写入本 runbook、日志或证据。不得使用内嵌浏览器，也不得替用户点击或接受授权。

## 6. 回调与激活

回调只接受一次。先验证 `state`、PKCE、精确 redirect URI 和错误字段，再在服务端交换 code。任何 code、token 或 client secret 都不得进入状态 receipt。返回 scope 必须精确等于 `gmail.modify`；token 必须成功加密落盘并读回验证，否则立即保持 Gmail 关闭并安全丢弃本地 token。

授权 receipt 只记录状态、scope 名称、门结果和无秘密证明。receipt 本身不是 readiness：完成只读自检及受控 `trash → untrash → hash readback` 恢复演练后，才可把状态从 `CONSENT_GRANTED_UNVERIFIED` 改为 `ACTIVE`。

## 7. 失效、拒绝和撤销

- 所有者拒绝或取消：`CONSENT_DENIED`，不自动再次提示。
- refresh token 无效、过期或被撤销：先关闭 Gmail；只有所有者明确重新启用时才再次进入 consent。
- Google OAuth 应用处于 External + Testing 时，包含 Gmail scope 的 refresh token 可能 7 天失效；不得把“一次性”写成永不过期。
- scope 不匹配：不激活，删除本地 token；仅在已有明确运行期撤销授权时程序化 revoke，否则提供 Google Account 第三方访问移除说明。
- token/client secret 泄露：进入 `SECURITY_ISOLATED`，按 P02 `SECURITY_OR_SUPPLY_CHAIN_INCIDENT` 处理，不适用普通“只关 Gmail 继续”简化规则。

Google 程序化撤销可能使同一项目下已授予的全部 scope 失效，并可能有传播延迟；撤销证据必须记录 HTTP 状态而不记录 token。用户也可在 Google Account 的第三方访问页面移除访问。

## 8. 当前停止点与官方来源

S00/P04 到此停止：合同可重放，但外部能力仍为 `UNVERIFIED`，Gmail 保持关闭。下一步是 Stage 0 整体复审，不是请求真实 Gmail 授权。

- Gmail scopes：https://developers.google.com/workspace/gmail/api/auth/scopes
- `messages.trash`：https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/trash
- OAuth web-server flow：https://developers.google.com/identity/protocols/oauth2/web-server
- OAuth policies：https://developers.google.com/identity/protocols/oauth2/policies
- OAuth token expiry：https://developers.google.com/identity/protocols/oauth2
- Google Account third-party access：https://support.google.com/accounts/answer/14012355

以上均于 `2026-07-19` 核验；它们是时间敏感快照，真实启用前必须复核。
