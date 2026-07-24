# Threat Model

## 1. 受保护资产

- Gmail OAuth Refresh Token 与短时 Access Token；
- GitHub App 私钥/Installation Token；
- age Operational Identity 与 Recovery Identity；
- Moomoo PDF Password；
- 完整 RFC EML、附件、交易/资金/税务 Processed；
- Sender Registry、Private Inventory、Sync State；
- M3 Gate 和目标 Message ID；
- 最新 Timeline。

## 2. 信任边界

1. Gmail → GitHub-hosted Runner；
2. Runner 内不可信邮件内容 → 验证/解析沙箱；
3. Runner → 单一私有仓；
4. 私有事实 → 公开脱敏 Evidence；
5. 公开代码/证据 → Codex 开发线程/Auto；
6. Recovery Key → 用户一次性交付。

## 3. 主要威胁与控制

| Threat | Attack | Control | Oracle |
|---|---|---|---|
| T-01 邮件误伤 | 普通邮件含 Moomoo 关键词 | exact sender + auth + fingerprint，双验证 | AC-001/004 |
| T-02 发件人伪造 | 显示名、相似域名、转发或 DKIM 失败 | 注册表和认证对齐；未知保持原样 | AC-004/005 |
| T-03 Thread collateral | Moomoo 与用户回复同线程 | exact `messages.trash`，禁止 thread endpoint | AC-006 |
| T-04 远端不可恢复 | Push 部分失败、密文损坏 | remote refetch + decrypt + Raw hash Gate | AC-007 |
| T-05 OAuth 越权 | send/delete/import 等调用 | Endpoint Guard、无实现、网络允许名单 | AC-018 |
| T-06 Secret 泄漏 | 日志、PR、Artifact、模型上下文 | Mask、扫描、无真实 Fixture、无模型数据面 | AC-011/012/016/022 |
| T-07 Prompt Injection | 邮件要求 Agent 执行命令 | 邮件永不进入模型；解析器不执行内容 | AC-020/033 |
| T-08 恶意附件 | PDF JS、宏、Zip Bomb、Polyglot | Magic Bytes、大小/时间/深度限制、Quarantine | AC-014/020 |
| T-09 路径穿越 | 恶意文件名覆盖仓库 | 内容寻址、忽略原文件名作为路径 | AC-020 |
| T-10 CSV 公式 | 下游打开表格执行公式 | 单元格转义、Parquet 优先、无公式执行 | AC-020 |
| T-11 私有仓越界 | Token 修改无关目录 | Repository ID、GitHub App 最小权限、path guard | AC-009/019 |
| T-12 供应链 | Action Tag 劫持、依赖漏洞 | 完整 SHA、lockfile、SBOM、CodeQL、审计 | AC-021 |
| T-13 数据重放 | 同一消息重复保存或 Trash | Content ID、状态机、幂等 Gate | AC-026 |
| T-14 公开侧信道 | 精确计数/时间推断交易活动 | 桶化、Opaque Root、字段 allowlist | AC-016/031 |
| T-15 Timeline 污染 | 每次渲染产生历史二进制 | 单一 Release Asset、输入 Root 去重 | AC-028 |
| T-16 密钥丢失 | Identity 丢失无法恢复 | 一次性交付、Environment Secret、恢复演练 | AC-012/032 |

## 4. Abuse Cases

- 仿冒 `moomoo-security.example` 发出“立即删除旧邮件”；
- 真实 Moomoo 邮件正文包含第三方引用的 Prompt Injection；
- PDF 声称是 Statement，实际包含脚本和超大对象流；
- 一封 Moomoo 消息与用户回复共用 Thread；
- 攻击 PR 尝试打印 Secret；
- Fork PR 尝试读取 Environment；
- 公共 Evidence 试图写入完整 Subject/Date/Ticker；
- Auto Prompt 被修改为触发工作流或读取私有仓。

所有 Abuse Case 都必须在发布前自动或人工红队通过。
