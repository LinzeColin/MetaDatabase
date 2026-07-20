---
artifact: PRFAQ
project: xhs-douyin-2notion
project_token: x2n
version: v0.0.0.1
status: FINAL_PRODUCT_DESIGN_BASELINE
owner_change_event: CE-X2N-20260719-S00-P01
decision: GO_TO_IMPLEMENTATION_TASKPACK
implementation_authorized: stage_0_governance_preparation_only
owner: LinzeColin
repository_target: LinzeColin/MetaDatabase
skill_path: xhs-douyin-2notion/
repository_visibility: public
runtime_data_visibility: private-local-only
data_root_ref: X2N_DATA_ROOT
research_cutoff: 2026-07-19
timezone: Australia/Sydney
---

# `xhs-douyin-2notion` PR/FAQ

> Scope amendment `CE-X2N-20260719-S00-P05`：项目名保留，终态支持范围扩为小红书、抖音、哔哩哔哩、快手、微博和淘宝；每个平台独立门禁，未知不等于可运行。

## 0. 一页决策

| 项目 | 定版结论 |
|---|---|
| 产品形态 | Chrome Manifest V3 Side Panel + 本地 Companion Service/WebUI + Codex Skill |
| 主运行位置 | 用户桌面本地；仅监听 `127.0.0.1`，通过 Chrome Native Messaging 连接 |
| OVH VPS-1 Singapore | Alpha 不承载采集、账号、媒体或模型数据；未来仅可作为可选控制平面 |
| 小红书 | Clean-room 浏览器适配器；借鉴 `xiaohongshu-exporter` 的 UX/交互，不复制未验证实现 |
| 抖音 | 以固定版本的 `jiji262/douyin-downloader` 作为受控上游，通过稳定 Adapter Contract 包装 |
| 哔哩哔哩/快手/微博/淘宝 | 官方 API/OAuth 优先；当前页 clean-room fallback 与个人列表能力逐平台 Policy/Auth/Technical/Canary Gate |
| MediaCrawler | 仅保留固定 Commit 的审计/竞品研究证据；不安装、不运行、不作为产品 Adapter |
| ShilongLee/Crawler | 自定义非商业 License；仅 clean-room 竞品思想，0 copy/vendor/runtime dependency |
| 主数据库 | 本地 SQLite Canonical Store；Markdown 与 Notion 都是可重建 Sink |
| Runtime 与下载 | 全部 Adapter 下载和 Runtime 共用仓库外 `X2N_DATA_ROOT`；本机绝对解析值不进 Git |
| 媒体策略 | 原始媒体仅临时处理；成功即删除，失败租约最长 24 小时；平台媒体 CDN URL 永不持久化 |
| 分类 | 用户定义唯一一级分类体系；AI 只能选择、建议和解释，不能擅自新增一级分类 |
| “文件夹式”浏览 | Canonical 内容不因重分类移动；生成分类目录索引 + Notion 分类视图，避免重复和断链 |
| 多模态 | 标题/正文 + ASR + OCR + 关键帧视觉理解 + 融合摘要 + 自动分类 + 人工复核 |
| 公共仓库边界 | 只提交代码、契约、合成 Fixture、脱敏证据；Cookie、Token、浏览器 Profile、私人内容和运行数据库禁止进入 Git |
| 发布策略 | 六平台合成 Walking Skeleton → 每个启用能力 20 条以内 Canary → 分层 Owner Alpha；功能均受独立 Feature Flag 控制 |
| 开发授权 | Owner 已授权 Stage 0 治理准备；产品代码、真实账号、外部写入、Stage 1 与远端上传仍未授权 |

**Pursuing Goal**

> 构建一个本地优先、可审计、可恢复的 Chrome＋Codex Skill 系统，把 Owner 明确选择的六平台当前内容或个人列表批次转换为按用户一级分类治理、包含多模态文本、可在 Markdown 与 Notion 中检索的知识资产，同时不持久化平台媒体 CDN 地址、账号凭据或原始媒体。

---

# 1. 面向客户的新闻稿（Working Backwards）

## 标题

**把六平台个人内容从“看过即忘”变成可治理、可搜索、可复用的个人知识库**

## 副标题

`xhs-douyin-2notion` 使用 Chrome 侧边栏和本地处理服务，将 Owner 明确选择的六平台当前内容或个人列表批次安全地同步为 Markdown 和 Notion 记录；视频语音、图片文字和画面语义会被转成可检索文本，并按用户自定义的一级分类治理。

## 新闻稿正文

悉尼，2026 年——长期收藏短视频和图文内容的人通常会遇到同一个问题：平台中的点赞和收藏越来越多，但搜索、分类、跨平台整理和再利用能力有限。已有工具可以下载媒体或导出部分列表，却很少同时解决个人关系、内容去重、多模态理解、自动分类、Notion/Markdown 双输出、隐私隔离和故障恢复。

`xhs-douyin-2notion` 将浏览器交互与本地长任务分开。用户在 Chrome Side Panel 中触发当前页面保存或账号收藏/点赞同步；本地 Companion Service 负责断点续传、临时媒体处理、语音转录、OCR、关键帧视觉理解、分类、Markdown 渲染和 Notion 队列。处理完成后，原始图片和视频默认立即删除，平台媒体 CDN URL 不进入永久数据库、笔记、Notion 或日志。

用户可建立自己的一级分类，例如“AI 与自动化”“金融与投资”“产品与商业”“健康”“旅行”。系统只会从已批准分类中选择，并显示分类理由和置信度；低置信度内容进入“待分类”复核区。一级分类像文件夹一样便于浏览，但系统不会复制 Canonical 内容或因重分类破坏链接。

该系统不会把平台 Cookie、Notion Token、模型密钥或私人收藏内容提交到公共 GitHub 仓库。所有敏感运行数据保存在操作系统的私有应用数据目录中，凭据进入系统 Keychain/Secret Store。Notion 是阅读和筛选界面，而非唯一数据源；即使 Notion 暂时不可用，内容仍先可靠落入本地 Canonical Store，并可在恢复后重新同步。

## 客户价值

1. **找得到**：跨平台统一搜索正文、语音转录、OCR 和视觉摘要。
2. **管得住**：用户控制一级分类，AI 只做受约束的分类建议。
3. **不怕坏**：SQLite 为真相源，Markdown 和 Notion 可重建；任务可断点恢复。
4. **不泄露**：公开的是代码，私人的是账号、内容和凭据；媒体 URL 和原始媒体默认不持久化。
5. **不重复造轮子**：复用成熟下载、浏览器自动化、ASR/OCR/视觉与 Notion API 能力，只开发缺失的编排和治理层。

---

# 2. 外部 FAQ

## Q1：它与 MediaCrawler 有什么不同？

MediaCrawler 的强项是公开内容搜索、指定帖子/作者/评论采集及部分平台媒体下载。下载图片或视频属于“原始媒体获取”，并不自动等于语音转录、OCR、画面理解、融合摘要、个人点赞/收藏关系、分类治理和 Notion/Markdown 双向可追溯同步。

本产品不替代、包装或运行 MediaCrawler。它仅作为固定 Commit 的历史审计/竞品研究参考保留，任何源码、进程、输出或数据都不得进入产品 Runtime。核心产品只实现个人明确选择内容的知识摄取和治理；若未来要求执行该工具，必须由新的 Owner Change Event 与独立 License/Policy Run 重新定界，不能沿用本 Task Pack 授权。

## Q2：为什么不是纯 Chrome 插件？

Chrome Manifest V3 后台采用 Service Worker。官方文档说明，Service Worker 通常会在约 30 秒无活动后终止，单个请求超过 5 分钟也可能被终止。FFmpeg、长视频 ASR、OCR、视觉模型、批量 Notion 写入和断点恢复都不适合依赖插件后台生命周期。

因此插件只负责高频交互、页面上下文和任务触发；本地 Companion 负责长任务。两者通过 Chrome 官方 Native Messaging 通信。

## Q3：为什么不是直接放在 OVH VPS-1 上长期运行？

账号型采集依赖真实浏览器登录态、二维码/手机验证和平台页面变化。本地真实 Chrome 更自然，也减少将 Cookie、浏览器 Profile、私人内容和媒体上传服务器的风险。VPS 长久在线并不能消除会话过期或验证码，也会增加持续轮询和维护成本。

Alpha 明确禁止 VPS 承载平台登录、采集、媒体、多模态内容和 Notion/模型密钥。未来若需要远程触发，可增设只保存脱敏状态的可选控制平面，本地 Agent 主动出站连接并实际执行。

## Q4：系统会保存图片和视频吗？

默认不会长期保存。媒体只进入受控临时目录，用于：

- 视频提取音频并 ASR；
- 抽取关键帧；
- 图片/关键帧 OCR；
- 图像或关键帧视觉理解；
- 内容 Hash 和重复检测。

成功处理后立即删除；失败任务最多保留 24 小时并自动清理。`retain_local_media` 不属于 Alpha 默认能力，未来即使加入也必须逐条显式启用。

## Q5：是否保存平台 CDN URL？

不保存。URL Scrubber 会阻止以下内容进入 Canonical Store、Markdown、Notion、日志和证据包：

- 图片、视频、封面和头像 CDN URL；
- 带签名或时效参数的媒体 URL；
- `xsec_token`、追踪参数和临时访问参数；
- 浏览器网络请求中的敏感 Header。

系统只保留经规范化的内容页面 URL和平台内容 ID。页面 URL 默认由允许列表中的 Host、Path 和内容 ID重建，不保留 Query String。

## Q6：自动分类如何工作？

用户先创建一级分类及定义、别名、正例和反例。分类器综合正文、ASR、OCR、视觉摘要和用户规则，只能：

- 选择一个已批准的一级分类；
- 添加多个辅助标签；
- 给出证据、模型版本和置信度；
- 将不确定内容放入“待分类”；
- 建议新增分类，但不能自行创建。

只有在 Owner Gold Set 上达到约定的高置信度精度 Gate 后，自动归档才可启用；否则降级为“建议分类＋人工确认”。

## Q7：它如何实现像文件夹一样浏览？

系统采用一份 Canonical 内容和多个派生视图：

```text
library/
├── content/
│   ├── xiaohongshu/<content_id>.md
│   └── douyin/<content_id>.md
└── categories/
    ├── AI与自动化/INDEX.md
    ├── 金融与投资/INDEX.md
    └── 待分类/INDEX.md
```

分类目录中的 `INDEX.md` 是自动生成的链接视图，而不是内容副本。重分类只更新索引，不移动 Canonical 文件。Notion 中创建同等的过滤视图，提供 Gallery、List 或 Table 浏览。

## Q8：Notion 是主数据库吗？

不是。SQLite Canonical Store 是唯一可写事实源；Markdown 和 Notion 是 Sink。Notion API 限流、超时或结构变化不会阻塞采集。Outbox 队列会按幂等键重试，并保存同步 Receipt。任何 Notion 页面都可以从 Canonical Store 重建。

## Q9：公开仓库会暴露我的收藏吗？

按设计不会。公共仓库只允许：

- 源代码、配置 Schema 和接口契约；
- 合成或彻底脱敏的 Fixture；
- 小型、脱敏运行 Receipt；
- 文档、测试和许可证声明。

以下内容强制禁止提交：Cookie、Session、浏览器 Profile、Notion Token、模型 API Key、Canonical DB、私人 Markdown、ASR/OCR 输出、原始 JSONL、媒体文件和完整日志。CI 使用 Secret Scan 和 Private-data Canary 阻断泄露。

## Q10：是否支持离线？

本地 Canonical Store、已有 Markdown、分类和人工复核可离线使用。平台采集、Notion 同步和云模型需要网络。本地 ASR/OCR 可在安装相应模型后离线运行；模型能力通过 Provider Adapter 替换，不能与单一供应商绑定。

---

# 3. 内部 FAQ

## Q11：为什么仍然值得开发，而不是直接使用现有项目？

现有项目分别覆盖了局部能力：

- `xiaohongshu-exporter` 提供 Chrome 收藏页采集 UX 和本地导出思路，但主后台 Notion 方法仍直接抛出“开发中”，自动化测试也仍是 TODO；其 Markdown/Notion 示例持久化封面 URL，与本产品策略冲突。
- `douyin-downloader` 是更成熟的抖音采集底座，支持登录账号的喜欢/收藏、SQLite 去重、重试、REST Server 和可选转录，但不提供统一分类治理、OCR/视觉、多平台 Canonical Schema、Markdown/Notion 幂等 Outbox 或 CDN 零持久化保证。
- MediaCrawler 能保存部分平台原始媒体，但不是个人收藏知识化产品。
- `ShilongLee/Crawler` 展示了多平台模块化和统一 Route 词汇，但其非商业 License、Cookie 明文存储/API/日志、无鉴权公网监听、任意 URL preview、代理规避和原始媒体落盘均不可整合；本项目只 clean-room 蒸馏平台隔离与能力协商思想。
- `xhs2obsidian`、`xhs-likes-manager` 等证明收藏/点赞、Markdown、自动分类和本地化需求真实，但成熟度、平台覆盖、Notion、安全和证据链仍不足。

因此要开发的是**薄而稳定的编排与治理层**，不是第四个通用爬虫。

## Q12：哪些能力应复用，哪些必须重写？

### 复用或包装

- `douyin-downloader`：固定 Commit 的外部/子进程 Adapter；
- Chrome/Playwright/CDP：浏览器登录和页面上下文；
- FFmpeg：音频提取、媒体探测和关键帧；
- 可替换 ASR/OCR/Vision Provider；
- Notion 官方 SDK/API；
- SQLite、Alembic、Outbox Pattern；
- 现有项目的 UX 和错误案例作为行为参考。

### 必须自行实现

- 跨平台 Canonical Data Contract；
- Personal Relation 模型；
- URL/Secret Scrubber；
- 一级分类治理和人工复核；
- 多模态融合与模型证据；
- 幂等 Markdown/Notion Sink；
- Checkpoint/Resume 和删除保护；
- 双流水线评测；
- 公开代码/私有运行数据边界；
- 安装、诊断、升级和回滚 Skill。

## Q13：小红书为什么采用 Clean-room Adapter？

`xiaohongshu-exporter` 的仓库页面声明 MIT，但在实施前仍需对固定 Commit 的实际 LICENSE 文件、第三方代码和来源做完整验证。更重要的是，其生产路径和测试证据不足。Clean-room 方式只把公开行为、页面交互和数据字段当作需求参考，由新的合同测试驱动实现，降低许可证、陈旧 API 和隐藏耦合风险。

## Q14：如何防止平台空响应误删历史数据？

平台返回空列表可能由登录过期、页面改版、限流或接口失败造成。Alpha 默认：

1. 采集失败或结果异常时，已有关系状态不变；
2. 取消点赞/收藏只标记为 `unknown`；
3. 只有连续两次“明确成功的完整扫描”均确认缺失，且删除功能 Flag 已启用，才可生成 Tombstone；
4. Alpha 的物理删除必须人工确认；
5. Canonical Content 永不因关系移除而自动删除。

## Q15：如何控制 AI 成本与错误？

- 本地模型优先，云模型显式启用；
- 按内容类型和时长路由，避免对纯文本调用 Vision；
- 关键帧先去重和采样，再进入 OCR/Vision；
- 缓存基于输入 Hash、模型、Prompt 和参数；
- 每日/月度预算上限，达到上限后降级；
- 先规则、再低成本模型、最后高质量模型；
- 不确定分类进入复核，而不是强制归档；
- 记录每次调用的 Provider、Model、版本、输入 Hash、Token/时长、成本字段和结果。

## Q16：为什么一级分类只能有一个？

一级分类的目标是提供稳定治理入口，类似文件夹。允许多个一级分类会重新引入重复、归属不清和视图爆炸。每条内容只有一个 `primary_category_id`，但可有多个辅助标签、多个用户关系和多个集合来源。

## Q17：如何避免“分类改变导致文件路径和链接失效”？

Canonical Markdown 按平台和内容 ID 固定路径保存，分类仅生成 Index/View。标题、作者和分类变化不会改变主文件路径。Notion 页面也通过 `content_id` 与本地映射表稳定关联。

## Q18：什么情况下应停止或降级项目？

见 PRD Kill Criteria。核心原则：

- 法律/许可证或平台规则风险不可接受：停止相关 Adapter；
- 采集完整性在两轮适配后仍低于最低 Gate：停做批量同步，保留当前页面手动保存；
- 自动分类达不到高置信度精度：降级为建议模式，不停止整个产品；
- 维护成本持续大于实际节省：暂停增量开发；
- 发生 Secret/CDN URL 泄露：立即阻断发布并轮换凭据；
- 任何不可逆迁移无可验证回滚：不得发布。

---

# 4. Working Backwards 验证实验

| 实验 ID | 待证伪假设 | 最小实验 | 成功信号 | 失败动作 |
|---|---|---|---|---|
| WB-001 | 用户的真实痛点是“找不到和无法治理”，不是单纯下载 | 对 40 条既有收藏进行手工查找、分类和复用 Baseline | 自动流程显著减少重复步骤且检索成功率提高 | 若仅下载即可满足，缩减为导出工具 |
| WB-002 | Chrome＋本地 Companion 比纯插件更可靠 | 对同一 20 条视频分别运行纯插件 PoC 与 Native Host PoC，并在 30 秒、5 分钟处注入中断 | Native Host 可恢复且扩展重启不丢任务 | 若纯插件足够，则移除本地 UI；预计不成立 |
| WB-003 | 用户一级分类可稳定约束模型 | Owner 定义 5–20 类，标注 100 条 Gold Set | 高置信度自动路由精度达到 Gate，低置信度可复核 | 降级为建议模式或改用规则优先 |
| WB-004 | 不保存原始媒体仍能满足复用需求 | 对 20 条内容完成 ASR/OCR/Vision 后删除媒体，隔日复查 | 文本资产足以完成检索和回顾 | 对少量高价值内容提供逐条显式本地保留 |
| WB-005 | Notion 应作为 Sink 而非主库 | 注入 429、529、断网和错误 Schema | 本地入库不受影响，恢复后无重复补写 | 若无法可靠恢复，Alpha 关闭 Notion Sink |
| WB-006 | 批量账号同步维护成本可接受 | 每个启用平台/能力运行独立 Canary/Owner Manifest 并记录修复工时 | 完整性达 Gate，月维护估计低于节省时间 | 单平台退回“当前页面保存＋手动批量导入” |
| WB-007 | 多模态提高分类和检索质量 | 比较仅正文与正文+ASR/OCR/Vision 的盲测 | 关键内容召回和分类准确性有可测提升 | 对无收益内容类型关闭昂贵模态 |
| WB-008 | 公开仓库可以安全承载代码 | 使用合成数据执行完整 CI、制品和 Release Secret Scan | 0 Secret、0 私人内容、0 CDN 媒体 URL | 阻断发布并重构运行边界 |

---

# 5. 初始客户旅程

## Golden Path：批量同步

```text
首次安装
→ 本地 Companion 健康检查
→ 在专用 Chrome Profile 中登录平台
→ 授权 Notion 父页面
→ 建立一级分类及正反例
→ 选择某一平台受支持的关系/个人列表和有界范围
→ 预览预计条数与权限
→ 小批量 Canary 20 条
→ 临时获取媒体并完成 ASR/OCR/Vision
→ 分类建议与低置信度复核
→ 写入 Canonical Store
→ 生成 Markdown 和分类 Index
→ Outbox 写入 Notion
→ 展示成功、跳过、失败和可重试证据
→ 扩大到完整增量同步
```

## Walking Skeleton：六平台逐一验证

```text
当前页面点击保存
→ 扩展提取最小页面事实
→ Native Messaging 发送任务
→ 本地服务规范化 URL/ID
→ 临时媒体处理
→ 生成摘要和分类建议
→ SQLite Commit
→ Markdown Commit
→ Notion Receipt
→ 临时媒体清理
```

## Degraded Path

```text
平台可访问、模型不可用
→ 保存元数据与正文
→ 多模态状态 pending
→ 分类进入待处理
→ 后续补跑

Notion 不可用
→ SQLite + Markdown 正常完成
→ Outbox retry_after
→ Notion 恢复后幂等补写

Cookie 过期
→ 停止该平台 Adapter
→ 不改变历史关系
→ Side Panel 提示人工登录
```

---

# 6. 价值、成本与“是否值得做”的判定

## 价值公式

不承诺固定收益。每月净收益采用可测公式：

```text
Monthly Net Time Saved
= Items Reused × (Manual Find-and-Process Minutes − Automated Review Minutes)
− Monthly Maintenance Minutes
− Owner Calibration Minutes
```

```text
Monthly Net Monetary Value
= Monthly Net Time Saved / 60 × Owner Shadow Hourly Value
− Cloud Model Cost
− VPS/Storage Incremental Cost
```

## 需要建立的 Baseline

- 每月新增点赞/收藏数量；
- 每月实际回看/复用数量；
- 手工查找一条旧内容的中位时间；
- 手工复制、转录、分类和写 Notion 的中位时间；
- 当前遗漏、重复和失效链接比例；
- 可接受的每月维护工时；
- 本地/云模型成本偏好。

## 粗略开发成本区间

这是复杂度区间，不是工期承诺：

| 层级 | 范围 | 典型工程投入 |
|---|---|---|
| Walking Skeleton | 六平台当前页、Canonical、Markdown、Notion Mock、单模态最小链路 | Stage 包络约 59–129 工程小时 |
| Usable Alpha | 六平台所选关系/列表、断点、ASR/OCR/Vision、分类复核、安装器 | 由逐平台 Gate 与实际工时校准 |
| Assured Alpha | 双流水线、E2E、性能/混沌、安全供应链、跨系统回滚 | Stage 总包络约 350–764 工程小时 |
| Beta/长期维护 | 平台适配、跨 OS 包装、可选控制平面 | 由真实变化率决定 |

影响区间的主要变量是：平台 DOM/API 稳定性、Owner 样本量、目标 OS 数量、本地模型要求和 Notion 页面复杂度。

## Go / Pivot / Kill

- **GO**：六平台合成 Walking Skeleton 均通过；每个实际启用平台/能力的独立 Owner Manifest 达 Gate；无 Secret/CDN 泄露。
- **PIVOT**：批量同步不稳定但当前页面保存稳定；切换为“Save Current + Import Queue”产品。
- **DEGRADE**：分类或模型效果不足；保留采集和文本化，关闭自动归档。
- **KILL ADAPTER**：许可证、平台规则或风控风险不可接受；移除相关 Adapter，不影响 Canonical/Sink。
- **KILL PRODUCT**：连续两个月维护时间高于节省时间，且当前页面降级模式也无净价值。

---

# 7. 已定版、未知和非授权事项

## 已定版

- Public Code + Private Runtime；
- Chrome Side Panel + Local Companion/WebUI；
- Native Messaging；
- SQLite Canonical Store；
- Markdown + Notion Sinks；
- 用户一级分类；
- 媒体临时处理；
- 平台媒体 CDN URL 零持久化；
- MediaCrawler 仅作审计研究参考，产品 Runtime 永不启用；
- VPS Alpha 禁用；
- Feature Flag + Canary + 可回滚发布。

## 开发时自动探测、不得阻塞的未知

- Owner 主力桌面 OS；
- 现有收藏规模；
- 一级分类数量和示例；
- Notion 父页面与权限；
- 是否允许云模型及预算；
- 中文、英文和方言比例；
- 首次同步时间窗口；
- 本地可用 CPU/GPU/RAM/磁盘。

这些未知由安装向导和 Stage 0 Baseline 获取。合成 Fixture 可让工程工作先行，不应在开发中反复向 Owner索取输入。

## 未授权

- 产品代码变更或真实账号运行；
- 向公共仓库提交私人数据；
- VPS 数据平面；
- Chrome Web Store 发布；
- 绕过验证码、风控或平台访问限制；
- 大规模公开爬取；
- 自动取消点赞/收藏；
- 自动物理删除 Canonical 内容；
- 默认永久保存媒体；
- 将 MediaCrawler 代码打包进核心产品。
- 将 MediaCrawler 作为产品 Adapter、外部进程或文件输入运行。

---

# 8. 一句话开发线程约束

> 始终以“个人内容知识治理而非通用爬虫”为边界，以本地 SQLite Canonical Store 为真相源，以 Chrome 为交互面、Local Companion 为执行面，任何实现都不得持久化平台媒体 CDN URL、凭据或原始媒体，不得让 AI 擅自创建一级分类，也不得以牺牲幂等、证据、恢复和公开仓库隐私边界换取功能速度。
