# 最终盲点、反证与 Surprise 复核

本文件把剩余问题转化为明确工程边界，不再要求用户追加决策。

## 已接受的平台事实

1. GitHub-hosted Runner 是临时环境，但底层物理介质擦除由 GitHub 负责；项目只承诺无用户侧持久化、无项目控制范围内的持久明文。
2. GitHub `schedule` 支持 IANA timezone，但官方明确说明事件可能排队延迟或被丢弃，公共仓长期无活动也可能停用；04:30 是本地调度目标而非精确启动 SLA。每次运行按水位幂等补偿，周日 Full Reconcile 检查差异，公开新鲜度 Evidence 与简单 Auto 只负责暴露异常；正常成功运行更新公开 Evidence，避免无活动状态。
3. Gmail `gmail.modify` 权限比单一 Trash 动作更宽；为降低凭证治理复杂度，采用一个凭证，但以代码级 endpoint guard、无发送实现、网络目的地限制和安全测试约束。
4. Gmail 标准 API无法直接枚举 Blocked Addresses；系统扫描 Spam/Trash 并只读审计 Filters，不作不可验证声明。
5. Gmail Trash 中消息可能约 30 天后被平台清理；M3 前必须完成远端恢复 Gate。
6. 同一个私有仓是用户指定的唯一持久数据仓，不增加第二故障域；Recovery Key 独立交付是数据可恢复的核心补偿。
7. 私有仓改名通过 Repository ID 和 GitHub App repository restriction 处理，不硬编码名称。
8. age 规范要求每个文件使用新的随机文件密钥、Nonce 和 X25519 临时秘密，因此相同明文重加密也会得到不同密文。Raw 永不无故重加密，采用 Recipient Epoch 管理未来对象；Timeline 用 Snapshot Root 与解密验证后的明文摘要判定幂等，密文摘要只用于传输与恢复完整性。
9. GitHub Release Assets 不提供同名原子替换；采用验证后串行 delete-upload，健康稳态恰好 1、任何时刻最多 1，删除后失败显式进入零资产修复态，不创建临时或历史图片。
10. Timeline 的报表“缺失”不能仅凭市场开市推断；没有独立活动证据只能标记 NOT_OBSERVED。
11. Moomoo PDF 密码未知不妨碍完整 EML、附件和 M3；结构化解析显式延迟。
12. 新发件人即时召回与零误伤存在冲突，已裁定零误伤优先，新地址保持原状直到注册表更新。
13. 公开 Evidence 必须足够诊断但不能泄漏精确邮件时间、数量、主题、证券或私有路径；使用桶化状态和 Opaque Root。
14. Codex Automation 可能失败，已从关键路径移除；用户始终回到开发线程，不需要找 Auto。
15. 真实金融数据不进入模型，故“模型侧双流水线”评估的是开发/运维代理的权限、诚实性和防注入，而不是让模型处理报表。

## 反证实验

- 故意伪造 Moomoo 显示名和主题：必须保持邮件不动。
- 在线程中混入用户回复和无关消息：只允许目标单封进入 Trash。
- 私有远端密文损坏：M3 必须为 0。
- GitHub Actions Cache/Artifact 被误配置：CI 必须阻止合并。
- Codex Auto 完全禁用：04:30 GitHub 数据面必须继续正常。
- 连续运行同一批次：Private Root、对象数量和 Gmail 最终标签必须稳定。
- 在 DST 边界和美国休市日渲染 Timeline：时间和交易日延迟必须符合 Golden Oracle。
- 公开 Evidence 注入真实形态数据：扫描器必须阻止发布。

## 最终结论

产品范围、权限、运行时间、数据仓、M3、Timeline、Codex/GitHub 分工、密钥交付和非目标均已无歧义冻结。开发中只有明确 Stop Condition、不可逆风险或超出授权范围时暂停；普通可逆选择按本任务包默认值继续，不向用户追加工程细节问题。
