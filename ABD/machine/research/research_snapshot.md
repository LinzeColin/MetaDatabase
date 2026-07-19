# 公开调研快照

检索日期：2026-07-19。只研究与ABD直接相关对象，不遍历用户其他仓库。

| ID | 来源 | 类型 | 裁定 | 用途 |
|---|---|---|---|---|
| SRC-001 | [Gmail API 概览](https://developers.google.com/workspace/gmail/api/guides) | 官方文档 | ADOPT | 授权读取邮箱；定时检索；附件归档 |
| SRC-002 | [Gmail API：获取附件](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages.attachments/get) | 官方文档 | ADOPT | 附件下载；权限范围 |
| SRC-003 | [Gmail API：移入垃圾箱](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/trash) | 官方文档 | ADOPT | 保存验证后删除邮件 |
| SRC-004 | [Gmail API 授权范围](https://developers.google.com/workspace/gmail/api/auth/scopes) | 官方文档 | ADOPT | 最小权限；gmail.modify |
| SRC-005 | [Gmail API 配额](https://developers.google.com/workspace/gmail/api/reference/quota) | 官方文档 | ADOPT | 每15分钟轮询预算；重试与退避 |
| SRC-006 | [OpenAI Codex](https://github.com/openai/codex) | 官方开源项目 | ADAPT | 每日审计代理；修复任务执行 |
| SRC-007 | [Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/) | 官方文档 | ADOPT | 全球访问；无需公开 OVH 入站端口 |
| SRC-008 | [OVH VPS 配置器](https://www.ovhcloud.com/en-au/vps/configurator/) | 官方产品页 | ADOPT | VPS-1 资源边界；容量约束 |
| SRC-009 | [TAB Conditions of Use](https://help.tab.com.au/troubleshooting-support/conditions-of-use) | 平台官方条款 | SOURCE_SPECIFIC | 来源能力合同；页面访问频率与账户边界 |
| SRC-010 | [TAB Activity Statements](https://help.tab.com.au/managing-your-account/activity-statements) | 平台官方帮助 | ADOPT | 月度账单邮件；交易证据与对账 |
| SRC-011 | [Sportsbet Rules, Terms & Conditions](https://helpcentre.sportsbet.com.au/hc/en-us/articles/115004802547-Sportsbet-Rules-Terms-Conditions) | 平台官方条款 | SOURCE_SPECIFIC | 最低金额；平台与结算能力合同 |
| SRC-012 | [ACMA 在线赛中投注规则说明](https://www.acma.gov.au/articles/2023-12/wagering-companies-breach-play-betting-rules) | 监管机构 | ADOPT | 实时市场建议通道约束 |
| SRC-013 | [flumine](https://github.com/betcode-org/flumine) | 开源项目 | ADAPT | 事件驱动结构；风险控制；模拟与纸面运行 |
| SRC-014 | [penaltyblog](https://github.com/martineastwood/penaltyblog) | 开源项目 | ADAPT | 足球比分分布模型；去水方法 |
| SRC-015 | [OddsHarvester](https://github.com/jordantete/OddsHarvester) | 开源项目 | ADAPT | 浏览器采集器；解析测试夹具；健康检查 |
| SRC-016 | [sportsbook-odds-scraper](https://github.com/declanwalpole/sportsbook-odds-scraper) | 开源项目 | RESEARCH_ONLY | 澳洲平台字段映射研究 |
| SRC-017 | [sports-betting-ml](https://github.com/ianalloway/sports-betting-ml) | 开源项目 | RESEARCH_ONLY | 市场概率与模型概率比较；凯利仓位示例 |
| SRC-018 | [Odds API read-only tooling](https://github.com/odds-api/odds-api) | 开源工具 | ADAPT_MOCKS_ONLY | 只读建议系统边界；模拟数据和风险提示 |
| SRC-019 | [The Betting Odds Rating System](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0198668) | 研究论文 | ADOPT_EVIDENCE | 市场价格作为强先验；赔率预测能力 |
| SRC-020 | [Knowing when to bet](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0287601) | 研究论文 | ADOPT_EVIDENCE | 不建议区域；不确定性决策 |
| SRC-021 | [Machine learning for sports betting: accuracy or calibration?](https://arxiv.org/abs/2303.06021) | 研究论文 | ADOPT_EVIDENCE | 校准优先；Brier 与对数损失 |
| SRC-022 | [Correction study on outlier-driven sports betting profitability](https://arxiv.org/abs/2306.01740) | 研究论文 | ADOPT_EVIDENCE | 异常值鲁棒性；删除最高盈利1%复测 |
| SRC-023 | [Risk-Constrained Kelly Gambling](https://arxiv.org/abs/1603.06183) | 研究论文 | ADOPT_EVIDENCE | 长期增长与回撤约束 |
| SRC-024 | [NIST Secure Software Development Framework](https://csrc.nist.gov/pubs/sp/800/218/final) | 安全标准 | ADOPT_CONTROL_BASELINE | 安全设计、构建、测试、维护 |
| SRC-025 | [NIST AI Risk Management Framework](https://airc.nist.gov/airmf-resources/airmf/) | 人工智能治理标准 | ADOPT_CONTROL_BASELINE | 模型风险与系统说明卡 |
| SRC-026 | [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/) | 应用安全标准 | ADOPT_CONTROL_BASELINE | 应用安全验收 |
| SRC-027 | [SLSA Build Requirements](https://slsa.dev/spec/v1.2/build-requirements) | 供应链安全标准 | ADOPT_CONTROL_BASELINE | 制品来源、构建证明 |
| SRC-028 | [ClamAV 扫描文档](https://docs.clamav.net/manual/Usage/Scanning.html) | 官方安全工具文档 | ADOPT | 邮件附件恶意软件扫描 |

## 研究边界

- 未声称穷尽互联网；来源、检索日期、采用/适配/拒绝和缺口均结构化保存。
- 官方文档和监管来源优先于开源项目说明。
- 开源项目只复用架构、测试和数学思想；许可证、数据用途和目标来源能力必须单独验证。
- 30%月目标没有被任何公开项目或论文证明可保证；任务包把它设计成可行性、证伪和长期实际验证合同。
- 邮件附件的保存/垃圾箱动作采用Gmail官方程序接口；Codex只做每日审计和修复，不承担破坏性删除判断。
