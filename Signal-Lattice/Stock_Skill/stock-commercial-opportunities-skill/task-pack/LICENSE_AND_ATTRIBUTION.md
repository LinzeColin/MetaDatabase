# License、归属与数据边界

## 本任务包

v3 Skill 指令、templates、synthetic fixtures 和 Python scripts 为本任务独立编写，随 MetaDatabase 的 proprietary 项目边界保存。仓库公开可见不等于授予开源许可。本文件不替代法律意见。

## 版本谱系

- v1/v2 原 ZIP 作为历史来源完整归档，其内容/第三方引用遵循各自文件中的声明。
- v3 没有把 v1/v2 旧 Skill 安装到本机，也没有把旧 ID 作为 alias。
- archives 不得静默改写；任何迁移必须新增 artifact/hash/changelog。

## 外部项目

本包仅链接并抽象高层模式，没有复制其源代码、提示词、长段文档、数据或品牌资产：

- OpenBB：研究快照标示 AGPLv3；未复制或链接运行时代码。
- EdgarTools：研究快照标示 MIT；当前 v3 不依赖。
- FinRobot、TradingAgents：研究快照标示 Apache-2.0；未复制实现。
- AlphaSense、Koyfin、TIKR：商业/专有产品；只引用公开产品形态，不包含其数据或付费内容。
- SEC、ASIC、ASX、Investor.gov：以官方链接和最小释义作为研究入口；来源的访问、版权与再使用条款仍适用。

未来若集成任何项目，必须固定 exact version/commit，复核 LICENSE/NOTICE、依赖、数据 provider 条款、网络访问和再分发义务；“开源代码”不自动使上游数据可公开再分发。

## 金融数据

当前包不包含真实 price、market cap、consensus、valuation、transcript、portfolio、transaction、account、borrow、customer 或 MNPI 数据。所有 issuer/ticker/exchange 示例均为 synthetic `DEMO` fixtures。

真实运行得到的数据仍归原 provider/权利人约束。公开输出应只保存允许再分发的最小事实、来源 URL/locator、provider/timestamp、schema 和用户生成的分析；付费或受限原始导出留在获授权 private plane。

## 运行依赖

三个 scripts 仅使用 Python 标准库；测试同样无第三方运行依赖。`agents/openai.yaml` 与 Markdown/JSON/JSONL/CSV 是静态资产。官方 Skill validator 是外部开发工具，不随包再分发。

## 金融声明

本包是研究方法和源码，不是个性化投资建议、交易邀请、目标价、收益预测或自动交易系统。任何真实证券结论都需要 current data、法域/许可核验和适当专业审阅。
