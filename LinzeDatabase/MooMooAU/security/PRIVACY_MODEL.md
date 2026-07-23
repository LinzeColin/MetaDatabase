# Privacy Model

## 数据分类

| 级别 | 示例 | 存储 |
|---|---|---|
| Secret | OAuth、GitHub App、age Identity、PDF Password | GitHub protected Secrets；不进入 Git |
| Restricted Raw | EML、附件、认证 Header、Message ID | 私有仓 `.age` |
| Restricted Processed | 交易、现金、股息、税务、时间线事实、精确 Inventory | 私有仓 `.age` |
| Public Contract | Schema、字段定义、Parser 版本 | 公开仓明文 |
| Public Evidence | 桶化状态、新鲜度、测试结论、Opaque Root | 公开仓明文 |

## 数据最小化

- 未验证候选只取最小 Metadata；
- 只有通过第一验证才获取完整 RAW；
- 原文件名不直接作为路径；
- 公开 Evidence 用 allowlist，不靠事后 blacklist；
- Codex 和 Auto 只看公开 Evidence；
- Timeline 图中不显示账户号、金额、Ticker、完整 Subject 或 Message ID。

## 保留

- Raw：append-only，长期保留以支持税务、审计和重处理；
- Processed：按 Schema/Parser 版本保留；
- Timeline：只有一个最新加密图片；
- Actions Log：只含脱敏运行信息，按仓库最短可用保留策略；
- Artifact/Cache：敏感数据禁用；
- Gmail：M3 后由 Gmail Trash 生命周期处理，系统不永久 delete。

## 删除与密钥

Git 历史和 LFS 的物理删除复杂，因此默认不对已归档 Raw 做普通删除；法律或用户删除需求必须进入独立安全版本。密钥轮换不等于历史数据自动删除，Cryptographic Erasure 也需明确对象与身份范围。

## 公开侧信道控制

- 数量桶而非精确数量；
- 新鲜度桶而非精确到达时间；
- Opaque HMAC/Merkle Root 而非可枚举原始 SHA；
- 不公开私有 Commit URL 或目录；
- 错误码不包含 Subject、Sender、Filename、Account 或 Ticker。
