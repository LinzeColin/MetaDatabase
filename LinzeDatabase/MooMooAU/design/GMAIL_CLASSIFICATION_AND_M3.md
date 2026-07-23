# Gmail 分类、零误伤与 M3 设计

## 1. 目标对象

只处理入站、确定性已验证的 Moomoo AU 相关单封消息。Sent 与 Drafts 永久排除。

## 2. 两阶段发现

### 最小发现

`messages.list(includeSpamTrash=true)` 返回 Message ID/Thread ID；随后仅取完成验证所需的最小 Header/Metadata。未知发件人不得获取完整 RAW。

### 完整获取

只有满足第一验证的消息才能调用 `messages.get(format=RAW)`。

## 3. Verified Sender Registry

Stage 0 不把未经一手证据确认的候选地址提升为 verified seed。Stage 3 只能从可审计的一手来源或
受保护 Owner 证据登记精确地址；未知候选保持 `UNKNOWN`，不得读取完整 RAW 或执行 M3。

注册表必须版本化并记录：精确地址、允许域、认证对齐策略、模板/业务指纹、证据来源、首次/最近验证时间、状态、替换版本。第三方生态发送者只能按精确地址和强 Moomoo 特征注册，不允许宽泛域名通配。

## 4. 三条件合取

```text
exact verified sender
AND authentication alignment
AND supported Moomoo AU business fingerprint
```

主题、显示名、正文关键词或附件名均不能独立通过。

第一次验证控制完整 RAW 获取；第二次验证在 M3 前重新读取当前消息头/标签并使用独立函数执行，防 TOCTOU 和规则漂移。

## 5. Gmail 位置

- All Mail / Inbox / Archive；
- Spam；
- Trash；
- Filters 只读审计。

Standard Gmail API 没有独立列举 Blocked Addresses 的端点；系统不作不可验证声明。Spam/Trash/Filters 只能表明可观察结果。

## 6. M3 Gate

```text
Raw byte hash known
→ age ciphertext generated
→ private remote commit succeeded
→ remote ciphertext refetched
→ age decrypt succeeded
→ decrypted Raw SHA equals Gmail Raw SHA
→ Processed complete OR explicit safe deferred state
→ second sender/auth/business verification passed
→ mutation budget available
→ exact users.messages.trash
→ refetch message and confirm TRASH label
```

已在 Trash 的消息完成归档和状态对账后标记 `ALREADY_TRASHED`，不重复调用。

## 7. 明确禁止

- `users.threads.trash`；
- `users.messages.delete`；
- batch delete/modify；
- send/draft/import/insert；
- 按 Thread ID、主题关键词或显示名进行 M3；
- 对新发件人自动学习后立即 M3；
- 在远端恢复前修改 Gmail。

## 8. Mutation Budget

- Alpha/Beta：0；
- 首次 Canary：每次 Run 最多 1；
- 稳定后分阶段提升，但默认仍有有界上限；
- 任意异常自动设置为 0；
- Full Reconcile 不绕过 Budget。
