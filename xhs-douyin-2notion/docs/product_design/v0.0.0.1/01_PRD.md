---
artifact: PRD
project: xhs-douyin-2notion
project_token: x2n
version: v0.0.0.1
status: FINAL_PRODUCT_DESIGN_BASELINE
owner_change_event: CE-X2N-20260719-S00-P01
design_authorized: true
implementation_authorized: stage_0_governance_preparation_only
research_cutoff: 2026-07-19
owner: LinzeColin
---

# `xhs-douyin-2notion` 产品需求文档

> Scope amendment `CE-X2N-20260719-S00-P05`：项目名作为稳定品牌保留，终态平台范围扩为小红书、抖音、哔哩哔哩、快手、微博和淘宝；产品边界仍是个人内容知识治理，不是通用爬虫。

## 1. 文档控制

| 字段 | 值 |
|---|---|
| 版本 | `v0.0.0.1` |
| 产品代号 | `x2n` |
| 目标仓库 | `LinzeColin/MetaDatabase` |
| 子项目路径 | `xhs-douyin-2notion/` |
| 仓库可见性 | Public |
| 运行数据 | Private / Local-only |
| Runtime 与下载根 | `X2N_DATA_ROOT`（仓库外，Owner 本机解析值不进入 Git） |
| 产品阶段 | Pre-Stage 00 Governance Baseline |
| 开发状态 | 已授权 Stage 0 治理准备；产品代码、真实账号、外部写入、Stage 1 与远端上传未授权 |
| 适用时间 | 以 2026-07-19 的仓库和官方文档调研为基础 |
| 变更规则 | 任何事实、范围、Gate 或依赖变更必须记录 ADR/Change Event，不得静默修改 |

### 1.1 事实标记

- **FACT**：来自已核验的一手仓库、源代码或官方文档。
- **DECISION**：本任务包已定版的产品决策。
- **ASSUMPTION**：可逆默认值，需用 Baseline 验证。
- **UNKNOWN**：当前无足够证据，已转化为前置任务或运行时探测。
- **RECOMMENDATION**：在约束下的默认实现建议，可由 ADR 替换。

---

# 2. 产品定义

## 2.1 产品问题

用户在小红书、抖音、哔哩哔哩、快手、微博和淘宝积累个人收藏、点赞、列表和当前内容，但平台内的跨平台组织、长期可访问性、内容理解和知识复用能力有限。单纯下载图片/视频或导出链接不能解决：

1. 六个平台的个人内容与关系统一；
2. 一条内容多种关系的去重；
3. 视频语音、图片文字和画面语义的检索；
4. 用户自定义分类的稳定治理；
5. Markdown 和 Notion 的幂等同步；
6. 平台页面、登录和接口变化下的恢复；
7. 公共代码仓库与私人内容/凭据隔离；
8. 不保存平台媒体 CDN 地址的合规与长期稳定要求。

## 2.2 产品目标

构建一个本地优先、可审计、可恢复的 Chrome＋Codex Skill 系统，把 Owner 明确选择的六平台当前内容或个人列表批次转换为按用户一级分类治理、包含多模态文本、可在 Markdown 与 Notion 中检索的知识资产，同时不持久化平台媒体 CDN 地址、账号凭据或原始媒体。

## 2.3 产品非目标

- 通用、大规模、持续在线的公共内容爬虫；
- 绕过验证码、风控、访问控制或平台限制；
- 多账号矩阵、代理池或云端账号农场；
- Alpha 阶段的移动端应用；
- Alpha 阶段的 Chrome Web Store 发布；
- Alpha 阶段的 OVH VPS 数据平面；
- 永久保存平台图片/视频/头像/封面；
- 默认抓取评论；
- 自动取消点赞、取消收藏或物理删除历史内容；
- Notion 双向编辑回写；
- 以 Notion 作为唯一事实源；
- 对所有 OS 同时达到完全原生安装体验；
- 自研 FFmpeg、ASR、OCR、Vision 基础模型；
- 将 MediaCrawler 源码或受限许可证代码 vendor 进核心产品。

## 2.4 产品原则

1. **Canonical First**：SQLite Canonical Store 是唯一可写事实源；Sink 可重建。
2. **Evidence First**：每个输入、转换、模型结果和外部写入都有版本、Hash 和 Receipt。
3. **Local First**：平台登录、Cookie、媒体和私人内容默认不离开用户设备。
4. **Least Persistence**：媒体只临时存在；CDN URL、签名参数和凭据不进入永久层。
5. **Human-owned Taxonomy**：一级分类属于用户，模型只能受约束选择和建议。
6. **Fail Closed on Destruction**：错误、空响应和过期会话不能触发删除。
7. **Adapter Isolation**：上游项目和平台实现只存在于 Adapter 边界，不污染 Canonical Schema。
8. **Reversible Delivery**：Feature Flag、Canary、版本化迁移和回滚优先于一次性“大重构”。
9. **Public Code, Private Runtime**：公共仓库不因便捷而承载任何私人运行资产。
10. **Knowledge Product, Not Crawler**：成功由可检索、可分类、可复用和可恢复衡量，不由下载量衡量。

---

# 3. 用户、场景和价值

## 3.1 核心用户

| 用户 | 主要任务 | 当前痛点 | 目标价值 |
|---|---|---|---|
| Owner / Knowledge Worker | 整理个人点赞与收藏 | 平台孤岛、找不到、重复、无法全文检索 | 一处统一管理和快速复用 |
| Researcher | 从视频/图文提取事实、观点和线索 | 语音和图片文字不可搜索 | ASR/OCR/Vision 生成可引用文本 |
| Builder / Product Designer | 建立 AI、产品、金融等主题素材库 | 手工复制、分类和 Notion 写入耗时 | 自动化流水线和可审计分类 |
| Operator | 运行、升级和恢复同步 | 登录过期、平台改版、模型/API 失败 | 诊断、Checkpoint、重试和回滚 |
| Future Contributor | 在 Public Repo 维护适配器 | 容易误提交私人数据或引入许可证风险 | 清晰边界、Fixture、合同测试和贡献规则 |

## 3.2 Jobs-to-be-Done

- 当我看到六个平台中任一有价值内容时，我要一键保存并立即知道它被归入哪里。
- 当我想整理历史收藏和点赞时，我要批量增量同步，而不是逐条复制。
- 当内容是视频或图片时，我要搜索其中说了什么、写了什么和展示了什么。
- 当分类不确定时，我要快速复核，而不是让模型胡乱建立目录。
- 当平台、Notion 或模型失败时，我要保留已完成工作，并能从中断处继续。
- 当项目代码公开时，我要确信凭据、私人收藏和平台媒体地址不会进入 Git 或 Release。
- 当未来更换模型、Notion Schema 或采集器时，我要重建派生结果，而不是重做全部收藏。

## 3.3 核心使用场景

1. **当前页面保存**：任意已打开且通过独立平台 Gate 的六平台内容。
2. **小红书收藏同步**：全量首次导入和后续增量。
3. **小红书点赞同步**：低门槛 Inbox，默认需要更严格复核。
4. **抖音收藏/收藏夹同步**：保留收藏夹来源关系。
5. **抖音点赞同步**：批量增量和去重。
6. **新平台个人列表**：哔哩哔哩、快手、微博、淘宝只同步 Owner 明确选择且当时官方授权支持的有界列表。
7. **多模态补处理**：对历史记录重新运行新模型。
8. **一级分类治理**：创建、编辑、合并、停用分类和正反例。
9. **人工复核**：低置信度、冲突、模型失败和未知类型。
10. **Markdown 浏览**：固定 Canonical 路径和分类 Index。
11. **Notion 浏览**：Items、Categories 和自动创建的过滤视图。
12. **故障恢复**：会话过期、Notion 限流、模型超时、磁盘不足、中途退出。
13. **数据导出/删除**：按用户请求导出 Canonical 数据或清理本地运行数据。

---

# 4. 战略目标、OKR 和成功定义

## 4.1 战略目标

### O1：把六平台个人内容转成可靠、可检索的 Canonical 知识资产

- KR1：在 Owner 真实 80 条验收样本中，必填 Canonical 字段完整率达到 `>=95%`，且静默丢失为 `0`。
- KR2：同一批输入连续运行两次，Canonical、Markdown 和 Notion 新增重复数均为 `0`。
- KR3：在采集、媒体处理、模型、分类、Markdown、Notion 任一阶段强制终止后，可恢复且无数据丢失/重复。

### O2：实现有边界的多模态理解和分类治理

- KR1：清晰普通话视频 Gold Set 的 ASR 中位 CER 初始 Gate `<=15%`；不满足时显示质量等级并允许替换 Provider。
- KR2：清晰截图/海报 OCR Gold Set 的中位 CER 初始 Gate `<=12%`；低质量图片单独分层，不混淆总体结果。
- KR3：自动归档阈值必须在 Gold Set 上达到高置信度精度 `>=90%`；否则保持“建议分类”模式。
- KR4：AI 未经 Owner 操作创建一级分类次数为 `0`。

### O3：维持 Public Code 与 Private Runtime 的安全边界

- KR1：Git 历史、工作树、构建制品和 Release 中 Secret 命中为 `0`。
- KR2：Canonical DB、Markdown、Notion 导出、日志和证据中平台媒体 CDN URL 命中为 `0`。
- KR3：成功任务完成后的临时原始媒体残留为 `0`；失败媒体超过 24 小时残留为 `0`。
- KR4：真实账号 Cookie、浏览器 Profile、Notion Token、模型 Key 上传公共仓库次数为 `0`。

### O4：让系统的维护成本低于其知识复用收益

- KR1：建立月度手工流程 Baseline 和自动化后对照，不用假设收益代替测量。
- KR2：连续两个月记录维护时间、处理量、复用量和节省时间。
- KR3：若维护时间持续高于节省时间，触发 Pivot/Kill Review，而不是继续堆功能。

## 4.2 指标定义

| 指标 ID | 指标 | Baseline | 初始目标 | 测量方法 | 观察期 |
|---|---|---:|---:|---|---|
| MET-001 | Canonical 必填字段完整率 | UNKNOWN | `>=95%` | 80 条人工真值对比 | Alpha Gate |
| MET-002 | 静默丢失数 | UNKNOWN | `0` | 页面清单与入库 ID 差集 | 每次验收 |
| MET-003 | 重复率 | UNKNOWN | `0` 新增重复 | 二次运行差异 + 唯一约束 | 每次回归 |
| MET-004 | 任务恢复成功率 | UNKNOWN | `100%` 测试场景 | 故障注入矩阵 | Release Gate |
| MET-005 | CDN URL 持久化数 | UNKNOWN | `0` | 域名/模式扫描四个持久层 | 每次 CI/Release |
| MET-006 | Secret 泄露数 | UNKNOWN | `0` | Gitleaks/自定义 Canary/制品扫描 | 每次 CI/Release |
| MET-007 | 高置信度分类精度 | UNKNOWN | `>=90%` | Owner Gold Set；报告置信区间 | Alpha Gate |
| MET-008 | 分类覆盖率 | UNKNOWN | 报告，不强求 | 达到精度 Gate 的自动归档比例 | 每版 |
| MET-009 | ASR CER | UNKNOWN | 清晰普通话中位 `<=15%` | 人工转录 Gold Set | 模型 Gate |
| MET-010 | OCR CER | UNKNOWN | 清晰图片中位 `<=12%` | 人工文本 Gold Set | 模型 Gate |
| MET-011 | Notion 最终一致性 | UNKNOWN | `100%` 已承诺 Outbox 最终有 Receipt/Dead Letter | 故障注入 | 每次回归 |
| MET-012 | 临时媒体清理 | UNKNOWN | 成功立即、失败 `<=24h` | 文件 Lease 扫描 | 每小时/启动时 |
| MET-013 | 月净节省时间 | UNKNOWN | `>0` | Baseline 与运行数据公式 | 两个月 |
| MET-014 | 月维护时间 | UNKNOWN | 低于月节省时间 | 维护事件记录 | 两个月 |
| MET-015 | 当前页保存端到端成功率 | UNKNOWN | `>=98%` 在支持页面 Fixture/Canary | E2E + Owner Canary | Alpha |
| MET-016 | 批量 Adapter 成功率 | UNKNOWN | 每平台 `>=90%` 已识别条目，无静默错误 | 真实样本对比 | Alpha |

> 阈值是初始 Acceptance Contract，不是对平台或模型能力的承诺。Stage 0/Gold Set 建立后，只能通过 Owner 批准的变更记录调整。

---

# 5. 现状调研与 Build/Buy/Integrate 决策

## 5.1 上游项目矩阵

| 项目 | 已核验能力 | 缺口/风险 | 产品决策 |
|---|---|---|---|
| `zhulin025/xiaohongshu-exporter` | MV3 扩展、收藏页自动滚动、范围/暂停、本地 JSON/CSV/HTML/Markdown、进度 UX | 主后台 Notion 方法直接抛“开发中”；独立 Notion 文件使用旧 API 并嵌入外部封面 URL；自动测试 TODO；页面选择器脆弱 | 只作为 UX/行为参考；Clean-room 重写小红书 Adapter 和 Notion Sink |
| `jiji262/douyin-downloader` | 登录账号 likes/favorites/收藏夹、SQLite 去重、重试、浏览器回退、REST Server、可选转录、MIT | 上游 Schema/命令会变化；收藏模式有运行边界；图文无 ASR；未提供统一 OCR/Vision/分类/Notion | 固定 Commit，通过 Adapter Contract 包装；保留替换能力 |
| `NanmiCoder/MediaCrawler` | 公开搜索/detail/creator/comments、多平台原始媒体下载、本地 CDP/WebUI | 非商业学习许可证；不是个人关系知识治理；原始媒体保存不等于语义理解；原始模型可能保留媒体 URL | 只保留固定 Commit 的审计研究证据；不安装、不运行、不作为 Adapter，不得 vendor |
| `ShilongLee/Crawler` | 七平台 FastAPI 模块、统一 detail/search/comments/replies/user 路由、平台隔离 | 自定义非商业许可证；明文 Cookie DB/API/日志、无鉴权公网监听、任意 URL preview、代理轮换/规避、原始媒体落盘；无 Canonical/恢复/知识 Sink | 0 行复制、0 Vendor、0 Runtime Dependency；仅 clean-room 蒸馏平台隔离与能力模型 |
| `jinghan23/xhs-likes-manager` | XHS 点赞/收藏、规则标签、人工复核、Markdown | 小型项目、无 Notion、多模态仍为改进项 | 参考个人关系和复核工作流 |
| `ytf606/xhs2obsidian` | XHS 收藏/点赞/帖子、Markdown、本地媒体、AI 分类、增量 | 新项目、仅 XHS、媒体策略不同、无本产品安全/Notion Contract | 参考目录和增量 UX，不作为核心依赖 |
| `bnchiang96/xiaohongshu-importer` | 分享链接导入 Obsidian、分类、可选媒体 | 单条导入、仅 XHS | 参考当前页降级路径 |
| `openmood/SyncToNotion` | 分享链接解析后进入 Notion | 不是账号历史同步，云端隐私边界不同 | 参考 Save-to-Notion 交互 |
| Chrome Native Messaging/Side Panel | 官方扩展到本地应用通信、浏览器侧栏 UI | 需要本地 Host 安装和 Extension ID 绑定 | 作为产品标准边界 |
| Notion API | Data Source、Page、View、限流和 Retry-After | 外部 API、Schema/Version 变化、限流 | Outbox＋幂等 Receipt；Notion 只是 Sink |

## 5.2 Build / Buy / Integrate

### Build

- Canonical Schema；
- URL/Secret Scrubber；
- Personal Relation 与分类治理；
- Chrome Side Panel 和 Native Messaging Contract；
- 小红书 Clean-room Adapter；
- 多模态 Pipeline 编排；
- Markdown/Notion 幂等 Sink；
- Checkpoint、Outbox、Evidence、诊断和恢复；
- 双流水线质量/安全评测；
- Codex Skill 和安装/升级脚本。

### Integrate

- 固定版本的 `douyin-downloader`；
- FFmpeg；
- SQLite；
- Playwright/CDP；
- Notion 官方 API/SDK；
- 本地或云 ASR/OCR/Vision Provider；
- OS Keychain；
- 标准安全、依赖和许可证扫描工具。

### Do not Build

- 通用爬虫平台；
- 自研浏览器引擎；
- 自研媒体编解码器；
- 自研基础模型；
- VPS 账号基础设施；
- 反检测、验证码绕过或代理池。

---

# 6. 产品范围

## 6.1 Alpha In Scope

- Chrome Desktop MV3 Side Panel；
- Local Companion Service；
- Local WebUI；
- Native Messaging；
- 当前页保存：小红书、抖音、哔哩哔哩、快手、微博、淘宝，逐平台独立 Gate；
- 个人小红书收藏和点赞；
- 个人抖音收藏/收藏夹和点赞；
- 哔哩哔哩、快手、微博、淘宝的 Owner 明确选择个人列表；仅当官方 Scope/Policy/预算/技术 Gate 支持时启用；
- 增量、去重、Checkpoint 和 Resume；
- 内容/关系分离的 Canonical Store；
- 临时媒体处理和 URL Scrubber；
- 视频 ASR；
- 图片/关键帧 OCR；
- 关键帧 Vision；
- 多模态融合摘要；
- 用户一级分类、辅助标签、AI 建议和人工复核；
- Markdown Canonical 文件和分类 Index；
- Notion Items/Categories、分类视图和 Outbox；
- 运行 Receipt、诊断、错误分层和 Dead Letter；
- Feature Flag、Canary、Blue-Green 本地版本、回滚；
- 软件正确性流水线；
- 模型能力与安全流水线；
- Public Repo 边界和合成 Fixture；
- Owner Alpha 安装和验收包。

## 6.2 Beta Candidates（不属于 v0.0.0.1 开发授权）

- OVH VPS-1 可选控制平面；
- 远程触发和脱敏状态；
- 跨设备同步；
- Chrome Web Store；
- 完整跨 OS 安装器；
- 逐条显式永久本地媒体；
- 评论、作者订阅、搜索研究；
- 六平台之外的其他平台 Adapter；
- Notion 双向变更；
- 自动分类体系建议合并；
- 更强本地 Vision 模型；
- 共享团队空间。

---

# 7. 功能需求

## 7.1 需求总表

| ID | 需求 | 优先级 | Alpha |
|---|---|---:|---:|
| REQ.X2N.001 | Chrome Side Panel 作为高频交互入口 | P0 | 是 |
| REQ.X2N.002 | Native Messaging 连接本地 Companion | P0 | 是 |
| REQ.X2N.003 | 六平台当前页面一键保存，逐平台独立 Gate | P0 | 是 |
| REQ.X2N.004 | 小红书收藏批量/增量同步 | P0 | 是 |
| REQ.X2N.005 | 小红书点赞批量/增量同步 | P0 | 是 |
| REQ.X2N.006 | 抖音收藏/收藏夹批量/增量同步 | P0 | 是 |
| REQ.X2N.007 | 抖音点赞批量/增量同步 | P0 | 是 |
| REQ.X2N.008 | Content 与 UserRelation 分离的 Canonical Schema | P0 | 是 |
| REQ.X2N.009 | 全链路幂等、去重、Checkpoint、Resume | P0 | 是 |
| REQ.X2N.010 | 临时媒体、CDN URL 零持久化和安全清理 | P0 | 是 |
| REQ.X2N.011 | 视频 ASR 及质量/来源记录 | P0 | 是 |
| REQ.X2N.012 | 图片/关键帧 OCR | P0 | 是 |
| REQ.X2N.013 | 关键帧 Vision 和视觉摘要 | P1 | 是 |
| REQ.X2N.014 | 多模态融合摘要和检索文本 | P0 | 是 |
| REQ.X2N.015 | 用户一级分类 Registry | P0 | 是 |
| REQ.X2N.016 | 受约束自动分类、解释和人工复核 | P0 | 是 |
| REQ.X2N.017 | Markdown Canonical Sink 与分类 Index | P0 | 是 |
| REQ.X2N.018 | Notion Items/Categories/View Sink | P0 | 是 |
| REQ.X2N.019 | Outbox、限流、Retry、Dead Letter 和 Receipt | P0 | 是 |
| REQ.X2N.020 | Provenance、运行证据和可审计性 | P0 | 是 |
| REQ.X2N.021 | Public Code / Private Runtime 安全边界 | P0 | 是 |
| REQ.X2N.022 | 可观测、诊断、降级和恢复 | P0 | 是 |
| REQ.X2N.023 | Feature Flag、Canary、迁移和回滚 | P0 | 是 |
| REQ.X2N.024 | 受限上游研究隔离 | P0 | 仅保留审计证据，产品 Runtime 零接入 |
| REQ.X2N.025 | 数据导出、保留和删除控制 | P1 | 是 |
| REQ.X2N.026 | 安装、配置、健康检查和升级 Skill | P0 | 是 |
| REQ.X2N.027 | 安全、依赖、许可证和供应链 Assurance | P0 | 是 |
| REQ.X2N.028 | 软件正确性＋模型能力安全双流水线 | P0 | 是 |
| REQ.X2N.029 | 哔哩哔哩当前页与 Owner 所选个人列表 | P0 | 是，Policy/Auth Gate 后 |
| REQ.X2N.030 | 快手当前页与 Owner 所选个人列表 | P0 | 是，OAuth/Consent Gate 后 |
| REQ.X2N.031 | 微博当前页与 Owner 所选个人列表 | P0 | 是，Policy/预算 Gate 后 |
| REQ.X2N.032 | 淘宝当前页与 Owner 所选个人列表 | P0 | 是，OAuth/Retention Gate 后 |

## 7.2 详细需求

### REQ.X2N.001 — Chrome Side Panel

- 在支持页面显示当前平台、内容 ID、登录/Adapter 状态。
- 提供“保存当前页”“同步收藏”“同步点赞”“预览/Canary”。
- 显示队列、进度、失败和可重试状态。
- 展示分类建议、证据和人工修正。
- 不保存平台 Cookie、Notion Token 或模型 Key。
- Service Worker 重启后从 Companion 重新读取状态，而非依赖内存。

### REQ.X2N.002 — Native Messaging

- Host Manifest 的 `allowed_origins` 只允许固定 Extension ID，不使用通配符。
- 消息使用版本化 JSON Schema。
- 每个请求含 `request_id`、`schema_version`、`action`、`payload_hash`。
- Companion 验证调用方、大小、字段和允许动作。
- 不接受任意 Shell Command、任意 URL 或任意本地路径。
- Extension 断开不得终止后端任务。

### REQ.X2N.003 — 当前页保存

- 支持六个平台已打开且通过 Capability Gate 的详情页；每个平台状态独立展示。
- 先提取稳定内容 ID、规范页面 URL、标题、作者、正文/简介和内容类型。
- 页面 DOM 提取失败时允许调用平台 Adapter 进行补充。
- 当前页保存是批量 Adapter 失效时的强制降级能力。
- 当前页也不得自动滚动、调用任意 URL 代理或改变账号状态。
- 保存前可选择一级分类或“自动建议”。

### REQ.X2N.004/005 — 小红书收藏与点赞

- 使用专用真实 Chrome Profile 和显式用户登录。
- 不绕过验证码；需要验证时暂停该 Adapter 并提示最小动作。
- 首次同步支持范围和 Canary；后续根据平台能力采用 ID/时间/Checkpoint 增量。
- 保存 `relation_type`、收藏夹/专辑来源、首次/最后见到时间。
- 空结果不得标记历史关系删除。
- DOM/API 变化必须通过 Fixture 和 Canary 检测。

### REQ.X2N.006/007 — 抖音收藏与点赞

- 通过 `DouyinAdapter` 包装固定版本 `jiji262/douyin-downloader`。
- 不让上游路径、表结构、状态码成为 Canonical Contract。
- 支持登录账号 likes、favorites 和收藏夹来源。
- 上游不可用时保留当前页保存。
- 对上游退出码、HTTP 状态、任务状态和输出 Schema 做合同验证。
- 上游升级先在 Fixture/Canary 上运行，不直接替换生产版本。

### REQ.X2N.008 — Canonical Schema

核心实体：

- `content`
- `account_ref`
- `user_relation`
- `source_observation`
- `media_lease`
- `artifact`
- `taxonomy_category`
- `classification`
- `sync_checkpoint`
- `outbox_event`
- `sink_receipt`
- `run`
- `evidence`
- `model_invocation`
- `dead_letter`

唯一标识：

```text
content_key = platform + ":" + platform_content_id
relation_key = account_ref_hash + ":" + content_key + ":" + relation_type + ":" + source_collection_id?
artifact_key = content_key + ":" + artifact_type + ":" + input_hash + ":" + processor_version
sink_key = sink + ":" + content_key + ":" + sink_schema_version
```

### REQ.X2N.009 — 幂等和恢复

- SQLite 唯一约束作为最终去重 Oracle。
- 每一步先记录状态，再执行副作用，再写 Receipt。
- 处理器使用内容 Hash 和版本作为缓存键。
- Checkpoint 必须可在进程 Kill、断电模拟和浏览器关闭后恢复。
- Notion 使用 Outbox；Markdown 使用原子临时文件＋rename。
- 重跑不得重复创建 Notion 页面。

### REQ.X2N.010 — 媒体和 URL 生命周期

- 平台媒体 URL 仅存在于内存或加密/权限受限的短生命周期任务记录。
- 任何落盘临时清单必须经过 URL Redaction，不记录完整 CDN URL。
- 下载目标只允许 `https` 和平台允许域名，禁止重定向到私网/本地地址。
- 校验 MIME、扩展名、大小、时长和内容 Hash。
- 成功处理后立即删除媒体；失败 Lease 最大 24 小时。
- 启动、每小时和正常退出时运行清理器。
- Canonical 页面 URL 去 Query、Fragment，并剔除 `xsec_token` 等参数。
- CDN Leak Scanner 覆盖 DB dump、Markdown、Notion Export、日志、CI Artifact 和 Git Diff。

### REQ.X2N.011 — ASR

- 从视频中提取标准音频格式。
- Provider Contract 支持本地和云端。
- 保存纯文本、可选时间段、语言、质量指标、模型/版本、输入 Hash。
- 音频或 Provider 失败不阻塞元数据入库。
- 重新运行新模型生成新 Artifact，不覆盖旧证据。
- 云端上传必须显式启用并受预算限制。

### REQ.X2N.012 — OCR

- 对图文图片和视频关键帧进行 OCR。
- 去重相似帧，避免重复文本和成本。
- 保存文本、帧/图片索引、Bounding Box（Provider 支持时）、语言和质量。
- OCR 输出按不可信内容处理，不能成为系统指令。

### REQ.X2N.013 — Vision

- 对代表性图片/关键帧生成可检索的视觉描述。
- 关键帧采样由时长、场景变化和预算决定。
- 禁止把原始平台媒体 URL传给模型；使用临时本地文件或受控上传。
- 对敏感/不支持内容给出明确失败码，不伪造描述。

### REQ.X2N.014 — 多模态融合

- 输入包含标题、正文、作者文本、ASR、OCR、视觉摘要。
- 输出包含：短摘要、详细摘要、关键观点、实体/主题、可检索文本、质量/缺失说明。
- 输入内容与系统指令分隔；任何帖子中的“忽略规则”等文本都作为数据。
- 保存 Prompt Template 版本、模型版本、输入 Hash 和证据引用。
- 不允许模型修改配置、分类 Registry、文件路径或外部系统。

### REQ.X2N.015 — 一级分类 Registry

每个分类包含：

```yaml
category_id: stable-uuid
name: 用户可读名称
slug: 稳定、安全、唯一
description: 分类边界
aliases: []
positive_examples: []
negative_examples: []
priority: integer
enabled: true
version: integer
created_by: owner
```

- 用户创建、编辑、合并、停用。
- 名称变更不改变 `category_id` 或 Canonical 路径。
- 合并产生映射和可回滚迁移。
- 系统始终提供“待分类”。

### REQ.X2N.016 — 分类与复核

- 分类器只能从 Enabled Registry 中返回一个 `primary_category_id`。
- 可返回多个辅助标签。
- 输出证据片段、候选排序、模型/规则版本和置信度。
- 自动归档阈值由 Gold Set 校准，不直接信任原始模型置信度。
- 不达 Gate 时自动切换 Suggestion-only。
- 用户修正进入训练/评测数据，但私人样本不提交公共仓库。
- 点赞默认更保守：进入 Inbox 或更高阈值；收藏可按普通阈值。

### REQ.X2N.017 — Markdown Sink

Canonical 路径：

```text
X2N_DATA_ROOT/runtime/library/content/<platform>/<content_id>.md
```

派生分类视图：

```text
X2N_DATA_ROOT/runtime/library/categories/<category_slug>/INDEX.md
```

- 文件名不依赖标题。
- YAML Frontmatter 包含稳定 ID、平台、关系、分类、标签、处理状态和 Provenance。
- 不嵌入平台媒体 URL。
- 不把 Transcript/OCR 过长内容塞入 Frontmatter。
- 使用原子写入和确定性渲染，支持全量重建。
- 分类 Index 是生成文件，不是第二事实源。

### REQ.X2N.018/019 — Notion Sink 与 Outbox

- 初始化 `Items` 和 `Categories` Data Source。
- 创建或更新平台、关系、分类、复核、失败等视图。
- 使用 `content_key` 唯一属性和本地 `notion_mapping` 实现 Upsert。
- 默认写入元数据、摘要、ASR、OCR、视觉摘要、分类、原帖规范 URL，不上传原始媒体。
- 长文本按 Notion 限制分块；超长内容可放子页或仅写摘要＋本地路径提示。
- 默认请求速率低于官方平均限额，动态处理 429/529 和 `Retry-After`。
- 外部写入前落 Outbox，成功后写 Receipt。
- Schema 变化必须版本化迁移；不自动破坏用户自定义字段。
- Notion 不可用时不阻塞 Canonical/Markdown。

### REQ.X2N.020 — Provenance

每条最终记录必须可追溯到：

- Platform Adapter 名称和版本；
- Source Observation 时间；
- 内容 ID和规范 URL；
- 原始文本 Hash；
- 媒体内容 Hash；
- ASR/OCR/Vision/Fusion Processor 和模型；
- Taxonomy 版本；
- 分类证据；
- Markdown Renderer 版本；
- Notion Schema 版本和 Receipt；
- Run ID、Task ID和错误/重试记录。

### REQ.X2N.021 — Public/Private 边界

- 代码仓库不保存真实运行数据。
- Runtime 与全部 Adapter 下载必须使用仓库外 `X2N_DATA_ROOT`；各上游默认下载目录一律不得直接使用。
- Secret 使用 OS Keychain；配置文件只保存 Secret Reference。
- 浏览器 Profile 独立、受权限保护、加入禁止提交模式。
- Fixture 必须合成或彻底脱敏。
- CI 使用假 Token、Mock Server 和合成页面。
- Release Artifact 不包含本地绝对路径、用户名或缓存。

### REQ.X2N.022 — 可观测和恢复

- 结构化日志默认不含正文、ASR/OCR 原文、URL Query 或 Secret。
- Metrics：任务量、阶段耗时、失败类型、重试、队列、清理、模型成本、分类复核。
- Health：Extension、Native Host、Companion、DB、FFmpeg、Provider、Notion、Adapter。
- 一键诊断生成脱敏 Bundle。
- Error Taxonomy 区分：用户动作、平台变化、网络、Provider、数据、系统、策略阻断。
- Recovery 支持重建 Markdown/Notion、重跑 Artifact、恢复 Outbox 和清理 Lease。

### REQ.X2N.023 — Feature Flag/Release

- 所有平台批量 Adapter、多模态类型、自动分类和 Notion 均有 Flag；受限爬虫项目不是可启用 Feature。
- Walking Skeleton 默认只开当前页和本地 Canonical/Markdown。
- Canary 最多 20 条；通过后扩至 80 条验收样本。
- DB 使用版本化迁移和备份。
- 本地 Companion 采用 Blue/Green 版本目录或可并存虚拟环境。
- 回滚不回滚 Canonical 数据，只回滚代码和 Schema 兼容层；破坏性迁移禁止无备份执行。

### REQ.X2N.024 — 受限上游研究隔离

- `NanmiCoder/MediaCrawler` 与其他受限爬虫只可作为固定 Commit 的审计/竞品研究参考；
- 产品不安装、不执行、不包装，不接收其文件/数据库/网络输出，也不继承其内部数据模型；
- 源码复制、Vendor、Runtime Dependency、Container/Installer 捆绑和产品 Feature Flag 均为禁止；
- Public Artifact 仅可保留脱敏摘要、Commit、License、Hash、SBOM `excluded` 记录与 clean-room 决策；
- 任何未来执行诉求必须由新 Owner Change Event 和独立 License/Policy Run 授权，不属于 v0.0.0.1。

### REQ.X2N.025 — 数据生命周期

- 支持导出 Canonical JSONL、Markdown 和运行摘要。
- 用户可删除单条 Content、某平台关系或全部本地运行数据。
- 删除前显示影响范围并生成可选备份。
- Notion 删除默认不自动同步回本地。
- 物理删除需显式确认；关系取消优先 Tombstone。
- 临时媒体和日志按 TTL 清理。
- Public Repo 证据只保留聚合/脱敏值。

### REQ.X2N.026/027/028 — Skill、Assurance、双流水线

- Skill 提供安装、配置、运行、诊断、验收、升级、回滚命令。
- 代码正确性流水线覆盖 lint/type/unit/contract/integration/E2E/performance/chaos/security/SBOM/license。
- 模型流水线覆盖 Gold Set、ASR/OCR、融合、分类、Prompt Injection、内容安全、成本和漂移。
- 两条流水线都通过才可进入 Alpha。
- 不同模型/规则互审只用于发现盲区，不以“多数投票”掩盖共同偏差。
- 任何模型或上游升级都触发对应范围的回归，不允许仅凭版本更新发布。

### REQ.X2N.029/030/031/032 — 新增四平台适配

- 哔哩哔哩、快手、微博和淘宝分别实现独立 `current_page` 与 `selected_collection` Capability；不存在统一“点赞/收藏”概念时不得伪造映射。
- 官方 API/OAuth 优先；当前页 clean-room fallback 需要独立 Policy、Auth、Technical 和 Canary Gate。
- 不允许自动滚动、自动翻页、代理轮换、地域/频率规避、验证码绕过、设备/鼠标指纹模拟、Cookie 导出或未文档化签名复制。
- 每个平台单独 Feature Flag/Kill Switch；Policy/Scope/预算/DOM 任一未知时只禁用该平台，不降低其他平台的证据标准。
- 预览/下载只通过 Local Companion 的安全媒体 Lease；平台 CDN URL、凭据和原始媒体不得进入持久层。
- 分类只消费 Canonical Artifact；AI 不能创建一级分类。

---

# 8. 工作流与操作流

## 8.1 首次安装

```text
安装 Skill 源码
→ 验证仓库治理和运行目录
→ 安装 Companion 依赖
→ 安装/检测 FFmpeg
→ 构建 Chrome Extension
→ 注册 Native Messaging Host
→ 加载开发者模式扩展
→ Companion 仅监听 127.0.0.1
→ 运行合成 Fixture Self-test
→ 建立专用浏览器 Profile
→ Owner 仅在需要 Canary 的平台专用 Profile 手工登录/授权
→ 配置 Notion Integration 和父页面
→ 定义一级分类
→ 选择本地/云 Provider 和预算
→ 运行 20 条 Canary
```

### 错误路径

- Native Host 找不到：显示 OS 对应注册位置和修复命令。
- Extension ID 变化：重新生成 Host Manifest 的精确 `allowed_origins`。
- FFmpeg 缺失：元数据路径继续，多模态标记 blocked。
- Notion 未授权：跳过 Notion，Canonical/Markdown 正常。
- 分类未定义：全部进入“待分类”，不阻塞采集。
- Provider 未配置：仅做可用的本地/文本处理。

## 8.2 当前页保存

```text
Side Panel 读取页面上下文
→ 校验支持域名和详情页
→ 解析稳定 ID
→ 规范化页面 URL
→ 用户选择关系和可选分类
→ Companion 创建 Run/Observation
→ Adapter 补充事实
→ 媒体临时处理
→ Canonical Transaction
→ 分类/复核
→ Markdown
→ Notion Outbox
→ 清理
→ UI 显示 Receipt
```

## 8.3 批量同步

```text
选择平台/关系/范围
→ 预检登录和 Adapter 健康
→ Dry-run 显示预计条目和权限
→ Canary
→ Owner 明确触发有界可见批次/分页动作（禁止自动滚动）
→ 每个有界批次写 Observation 和 Checkpoint
→ 内容去重
→ 多模态队列（低并发）
→ 分类队列
→ Sink 队列
→ 完整性对账
→ 运行摘要
```

## 8.4 多模态

```text
Media Lease
→ 安全下载
→ MIME/大小/时长/Hash
→ 图像：去重 → OCR → Vision
→ 视频：FFprobe → Audio → ASR → Scene Detect → Keyframes → OCR/Vision
→ Artifact Validation
→ Fusion
→ Classification
→ Delete Media
```

## 8.5 人工复核

```text
待分类/冲突/低质量列表
→ 显示摘要、证据和候选
→ Owner 选择一级分类/标签
→ 写 Classification Revision
→ 更新 Markdown Index
→ Notion Outbox Update
→ Gold Set 可选采纳
```

## 8.6 删除/关系变化

```text
新一轮成功完整扫描未见关系
→ 标记 unknown
→ 第二次成功完整扫描仍未见
→ 生成 tombstone_candidate
→ Alpha 人工确认
→ relation.status=removed
→ 更新视图
→ Content 保留
```

## 8.7 恢复

```text
启动
→ DB integrity_check
→ 扫描 active Run/Lease/Outbox
→ 过期 Lease 清理
→ 从最后 Durable Checkpoint 恢复
→ 幂等重放未完成步骤
→ 对账 Sink Receipt
→ 输出恢复证据
```

---

# 9. 信息架构和 UX

## 9.1 Chrome Side Panel

导航不超过五个一级区：

1. **Save**：当前页保存和分类；
2. **Sync**：平台/关系/范围/Canary；
3. **Review**：待分类、失败和冲突；
4. **Status**：队列、健康和最近运行；
5. **Settings**：只包含非 Secret 引用和打开本地 WebUI。

## 9.2 Local WebUI

- Dashboard；
- Sources；
- Taxonomy；
- Review Queue；
- Processing Jobs；
- Library；
- Notion；
- Models & Budget；
- Diagnostics；
- Data Lifecycle。

## 9.3 Notion

### Data Source: Items

- `Name`
- `Content Key`
- `Platform`
- `Content Type`
- `Relations`
- `Collection`
- `Primary Category`
- `Tags`
- `Author`
- `Canonical Source URL`
- `Published At`
- `Captured At`
- `Summary`
- `Transcript Status`
- `OCR Status`
- `Vision Status`
- `Classification Confidence`
- `Review Status`
- `Processing Version`
- `Local Markdown Key`
- `Sync Status`

### Data Source: Categories

- `Name`
- `Category ID`
- `Definition`
- `Aliases`
- `Positive Examples`
- `Negative Examples`
- `Enabled`
- `Taxonomy Version`
- Relation to Items

### Views

- All Items；
- By Primary Category；
- Likes Inbox；
- Favorites Library；
- Needs Review；
- Processing Failed；
- Recently Added；
- Xiaohongshu；
- Douyin；
- Optional Dashboard。

---

# 10. 数据、容量和性能

## 10.1 初始容量假设

| 维度 | Alpha 设计容量 | 说明 |
|---|---:|---|
| Canonical Content | 10,000 条 | 单用户本地知识库 |
| UserRelation | 30,000 条 | 同一内容可有多个关系/收藏夹 |
| 单次批量任务 | 1,000 条 | 更大任务分段 |
| 并发媒体处理 | 默认 1，最大 2 | 控制 CPU、磁盘和风控 |
| Notion 请求 | 默认目标 `<=2 req/s` | 低于官方平均 3 req/s并自适应 |
| 失败媒体 TTL | `<=24h` | 成功立即删除 |
| 运行 Receipt | 每 Run 小型脱敏摘要 | 完整日志不进 Git |
| 本地 DB | SQLite WAL | 单用户、低并发适配 |

## 10.2 性能要求

- Side Panel 交互响应目标：本地状态读取 P95 `<300ms`。
- 当前页创建任务目标：P95 `<1s`，不含后续媒体/模型。
- 1000 条纯元数据去重/入库不应因 O(n²) 算法退化。
- Markdown 全量重建按内容数近似线性。
- Notion 写入由外部限流主导，不设伪精确“每分钟完成数”，只要求不丢失和可恢复。
- 多模态吞吐按“视频分钟/处理分钟”和硬件记录，不承诺统一速度。
- 本地模型内存超限时必须降级到低资源 Provider 或排队，不崩溃整个服务。

## 10.3 压力层级

- S：20 条 Canary；
- M：80 条 Acceptance；
- L：1,000 条单任务；
- XL：10,000 条 Canonical 重建；
- Long-video：30/60/120 分钟；
- Image-heavy：单条 50 张图片；
- Burst：连续 100 次当前页保存；
- Recovery：每个阶段随机 Kill 100 次。

---

# 11. 安全、隐私和法律约束

## 11.1 数据分级

| 级别 | 示例 | 位置 | Git |
|---|---|---|---|
| Public | 源码、Schema、合成 Fixture、文档 | Repo | 允许 |
| Internal Derived | 聚合指标、脱敏 Receipt | Repo 指定 artifact 或 CI | 条件允许 |
| Private Content | 收藏正文、ASR、OCR、摘要、分类 | Runtime Root | 禁止 |
| Secret | Cookie、Token、Key、Profile | Keychain/受保护目录 | 永久禁止 |
| Ephemeral Sensitive | CDN URL、媒体文件、网络响应 | Memory/Temp Lease | 禁止持久化 |

## 11.2 关键安全要求

- STRIDE Threat Model；
- Native Host Extension ID allowlist；
- Loopback-only＋随机 Session Token/OS ACL；
- CSP 禁止 `eval` 和远程脚本；
- 输出 HTML/Markdown/Notion 内容净化；
- SSRF：域名、IP、协议、重定向和 DNS Rebinding 校验；
- 文件大小、时长、格式、解压和媒体解析限制；
- FFmpeg/OCR/模型子进程沙箱、超时和资源限制；
- 不把帖子文本当指令；
- OS Keychain；
- 依赖 Lock、Hash、SBOM、License Scan；
- Secret Scan、PII/Private Fixture Scan、CDN Leak Scan；
- 日志字段 Allowlist；
- 备份加密和最小保留；
- 无遥测默认；
- 任何未来遥测显式 Opt-in 和脱敏。

## 11.3 平台与许可证

- 不设计验证码绕过、反检测或大规模抓取；
- 默认低频、用户触发、单账号；
- MediaCrawler 受非商业学习许可证限制，只作为外部可选研究工具；
- `douyin-downloader` 当前 LICENSE 为 MIT，但仍须保存版权和 NOTICE；
- `xiaohongshu-exporter` 在固定 Commit 上必须再次核验 LICENSE/第三方来源；无明确证据前不复制代码；
- 上游升级必须重新做许可证、Schema、行为和安全审查；
- 法律/平台政策判断超出工程证据时标记 UNKNOWN，并在分发或商业化前寻求专业意见。

---

# 12. 可靠性、可用性和运维

## 12.1 可靠性目标

- Canonical Transaction 不依赖 Notion 成功；
- 处理阶段可重放；
- 删除操作 Fail Closed；
- 外部服务故障不导致静默丢失；
- 每个 Run 有终态：success / partial / blocked / failed / cancelled；
- partial 必须列明缺失 Artifact；
- Dead Letter 可重新驱动；
- DB 迁移前自动备份；
- 版本回滚可读取新版本生成的数据，或有明确兼容层；
- Temp Cleaner 与任务 Lease 协调，避免删除正在处理的文件。

## 12.2 SLO（Alpha 内部）

| SLO | 目标 |
|---|---|
| Canonical Durability | 已 Commit 内容在故障注入后 0 丢失 |
| Idempotency | 重跑 0 重复副作用 |
| Current-page Availability | 支持页面 E2E/Canary 成功率 `>=98%` |
| Batch Adapter Observed Success | 每平台真实样本 `>=90%` 且 0 静默错误 |
| Recovery | 所有定义故障点可恢复 |
| Secret/CDN | 0 泄露 |
| Data Destruction | 0 未授权物理删除 |

---

# 13. 成本收益、敏感性与机会成本

## 13.1 成本构成

- 初始工程：Extension、Companion、Adapters、Pipeline、Sinks、Assurance；
- Owner 一次性输入：登录、Notion、分类、Gold Set；
- 本地计算：CPU/GPU、电力、磁盘；
- 云模型：音频分钟、图像/Token 和调用次数；
- 平台适配维护；
- 安全/依赖升级；
- Notion Schema 维护；
- 复核时间。

## 13.2 收益构成

- 减少重复复制、下载、转录、分类和 Notion 写入；
- 提高旧内容检索成功率；
- 形成可全文搜索的跨平台语料；
- 更快为研究、产品和投资决策找到既有证据；
- 减少平台链接失效造成的知识损失；
- 复用统一 Adapter/Sink/Model 架构扩展其他来源。

## 13.3 敏感性分析

| 变量 | 低情景 | 中情景 | 高情景 | 决策影响 |
|---|---|---|---|---|
| 每月新增收藏 | 少 | 中 | 多 | 少量时当前页保存可能更划算 |
| 复用率 | 低 | 中 | 高 | 复用率低则自动化价值下降 |
| 平台变更频率 | 低 | 中 | 高 | 高时批量 Adapter 维护可能超过收益 |
| 云模型使用 | 无 | 有限 | 大量 | 影响成本与隐私 |
| 分类稳定性 | 高 | 中 | 低 | 低时使用建议模式 |
| Owner 复核意愿 | 高 | 中 | 低 | 低时需更严格高精度阈值 |
| 目标 OS | 1 | 2 | 3 | 跨平台包装显著增加工作量 |
| 原始媒体保留 | 否 | 少量 | 大量 | 增加存储、隐私和治理成本 |

## 13.4 机会成本

优先开发本项目意味着暂缓：

- 通用研究爬虫增强；
- VPS 控制平面；
- Chrome Web Store；
- 六个平台之外的来源扩展；
- 媒体永久归档；
- 高级知识图谱；
- Notion 双向同步。

Alpha 只应验证个人收藏知识化闭环，不能因“未来可能需要”扩大范围。

---

# 14. 风险、反证和 Kill Criteria

| 风险 | 可能性 | 影响 | 预防/缓解 | Stop/Kill |
|---|---|---|---|---|
| 六平台 DOM/API/Policy/Scope 变化 | 高 | 高 | 独立 Capability Manifest、Adapter Contract、Fixture、当前页降级、Canary | 单平台两轮适配后仍 `<90%` 或授权未知，单平台停用 |
| 登录/验证码 | 中高 | 高 | 专用真实 Profile、人工登录、低频 | 需要绕过机制才可运行，停止 |
| Secret/私人内容进入 Public Repo | 中 | 极高 | 运行目录外置、Keychain、扫描、合成 Fixture | 任一泄露立即阻断、轮换、历史清理 |
| CDN URL 持久化 | 中 | 高 | Scrubber、Schema 禁止、扫描 | 任一 Release 命中阻断 |
| 媒体处理漏洞 | 中 | 高 | Allowlist、大小/时长、沙箱、超时 | 无法限制不可信媒体时关闭该处理器 |
| 分类错误 | 高 | 中 | Gold Set、精度 Gate、Suggestion-only | 高置信度精度 `<85%` 时禁用自动归档 |
| 模型 Prompt Injection | 中 | 高 | 数据/指令隔离、无工具权限、Red Team | 模型可修改配置/泄露 Secret 时阻断 |
| Notion 限流/变化 | 高 | 中 | Outbox、Retry-After、Schema Version | 无法最终一致时关闭 Notion Sink |
| 上游许可证不兼容 | 中 | 高 | Pin、NOTICE、Clean-room、外部进程 | 未核验 LICENSE 不得复制/分发 |
| MediaCrawler 用途越界 | 中 | 高 | 默认关闭、外部安装、非商业标记 | 商业化或大规模用途禁用 |
| 维护成本过高 | 中 | 高 | 记录事件、适配器隔离 | 连续 2 个月维护时间 > 节省时间 |
| 本地资源不足 | 中 | 中 | Provider 路由、并发 1、预算/限额 | 降级云端/元数据，不阻断核心 |
| 原始媒体删除后不可重处理 | 高 | 中 | Artifact 版本、逐条未来 Opt-in | 若知识质量不足，开放显式保留，不改默认 |
| 分类目录移动断链 | 中 | 中 | Canonical 固定路径、生成 Index | 禁止以标题/分类作为主文件路径 |
| 空响应误删 | 中 | 极高 | 双成功扫描＋人工确认 | 未有明确证据绝不删 |

## 14.1 Product Kill Criteria

- 当前页保存和批量同步都无法在不绕过平台控制的前提下稳定运行；
- 80 条验收中静默丢失无法归零；
- Public/Private 边界无法技术性强制；
- 核心依赖许可证不能合法使用且没有 Clean-room 替代；
- 连续两个月真实净收益不为正；
- Owner 不再需要跨平台知识治理。

## 14.2 Feature Kill Criteria

- 自动分类不达 Gate：只 Kill 自动归档，保留建议；
- Vision 无可测增益或成本过高：Kill Vision，保留 ASR/OCR；
- Notion 维护成本过高：Kill Notion，保留 Markdown；
- 批量 Adapter 太脆弱：Kill 批量，保留当前页；
- VPS 控制平面无明确价值：永不开发。

---

# 15. 人类输入一次性准备包

为避免开发中反复 Block，Stage 0 只需要 Owner 一次性完成：

| 输入 | 默认 | 不提供时的继续策略 |
|---|---|---|
| 主力桌面 OS | 自动探测 | 只保证检测到的 OS |
| 专用 Chrome Profile 登录 | 人工登录 | 使用合成 Fixture 开发，真实集成延后 |
| Notion 父页面和 Integration | Notion Sink 可关闭 | Canonical/Markdown 继续 |
| 一级分类 | 5–20 类＋定义＋正反例 | 全部进入“待分类” |
| Cloud Model 许可 | 默认关闭 | 使用本地或跳过对应模态 |
| 月预算 | 默认 0 云成本 | 达预算即降级 |
| Gold Set | 先 40 条 Smoke，再扩至 100 条 | 自动归档保持关闭 |
| 首次同步范围 | 20 条 Canary | 不直接全量 |
| 数据保留 | 媒体成功即删、失败 24h | 使用默认 |
| Notion 长文本策略 | 摘要在页、全文分块 | 使用默认 |

所有输入都可在安装向导导出为不含 Secret 的配置摘要；开发任务不得在上述可逆默认存在时暂停。

---

# 16. 依赖和技术默认

## 16.1 推荐技术栈

| 层 | 默认 |
|---|---|
| Extension | TypeScript、Manifest V3、Side Panel、严格 CSP |
| Local Companion | Python 3.12、FastAPI/Pydantic、后台 Worker |
| UI | TypeScript/React 或轻量等价方案；仅本地 |
| IPC | Chrome Native Messaging，版本化 JSON Schema |
| DB | SQLite WAL + SQLAlchemy/Alembic 或等价迁移层 |
| Browser | 用户真实 Chrome Profile + Playwright/CDP Adapter |
| Media | FFmpeg/FFprobe |
| ASR/OCR/Vision | Provider Interface；本地优先、云端 Opt-in |
| Markdown | 确定性模板、原子写入 |
| Notion | 官方 API/SDK，Outbox |
| Secrets | OS Keychain/Keyring |
| Packaging | `uv`/锁文件；Node 锁文件；OS 安装脚本 |
| Tests | Pytest、Vitest/Jest、Playwright E2E、Mock Servers |
| Security | Gitleaks、OSV/Dependabot、Semgrep/CodeQL、SBOM、License Scan |

技术栈可通过 ADR 替换，但不得破坏 Acceptance Contract。

## 16.2 预授权可逆决策

无需开发中再次征询：

- 使用宽松许可证的普通依赖；
- 增加单元/合同/E2E Fixture；
- 使用 SQLite WAL；
- 默认并发 1；
- 对外部 API 指数退避＋Jitter；
- 增加日志 Redaction；
- 增加 Feature Flag；
- 修复可回滚的 Schema/Adapter Bug；
- 对非核心能力自动降级；
- Pin 上游 Commit；
- 增加本地缓存和幂等键；
- 在不改变数据边界的前提下优化性能。

必须暂停的最小条件：

- 需要新的 Secret 或不可逆外部授权；
- 需要上传私人内容到新第三方；
- 需要违反平台控制或许可证；
- 需要破坏性数据迁移且无回滚；
- 超出 Alpha 范围；
- 发现已发生数据/Secret 泄露；
- Acceptance Contract 之间出现不可消解冲突。

---

# 17. 验收总门

只有同时满足以下条件，才可声明 `v0.0.0.1 Alpha`：

1. 需求→任务→测试→证据→制品 Traceability 无断链；
2. Task DAG 无循环、所有 P0 任务完成；
3. 软件正确性流水线通过；
4. 模型能力与安全流水线通过或明确降级；
5. 20 条 Canary 通过；
6. 每个启用平台/能力的独立 Owner Manifest 与 Canary/Alpha 通过；
7. Secret/CDN/私人数据扫描为 0；
8. 所有定义故障点可恢复；
9. Notion 429/529/断网测试通过；
10. DB 备份、迁移和回滚演练通过；
11. Owner 完成人工复核和 Sign-off；
12. Public Release Artifact 只包含允许内容。

详细 Oracle 见 `04_ACCEPTANCE_CONTRACT_TRACEABILITY.md`。

---

# 18. Canonical Facts

| Fact ID | 类型 | 内容 | 置信度 |
|---|---|---|---|
| FACT-X2N-001 | FACT | MetaDatabase 要求主树只读、开发使用独立 worktree，并由目标项目维护可验证的 Task/Acceptance 与证据边界 | 高 |
| FACT-X2N-002 | FACT | MetaDatabase 根 Contract 要求代码与数据专有，并只消费 `LinzeColin/Governance`，不得在项目中复制、分叉或 submodule 引入治理框架 | 高 |
| FACT-X2N-003 | FACT | `xiaohongshu-exporter` 是 MV3 扩展并有收藏页采集/导出 UX | 高 |
| FACT-X2N-004 | FACT | 其主 `background.js` 中 Notion 创建数据库/页面方法仍直接抛“开发中” | 高 |
| FACT-X2N-005 | FACT | 其独立 Notion exporter 使用 `2022-06-28` API 结构并把 `coverImage` 作为 external URL | 高 |
| FACT-X2N-006 | FACT | 其 TEST 文档的自动化测试仍为 TODO | 高 |
| FACT-X2N-007 | FACT | `douyin-downloader` 当前支持 likes/favorites、SQLite、重试、浏览器回退、REST 和可选转录 | 高 |
| FACT-X2N-008 | FACT | `douyin-downloader` LICENSE 为 MIT | 高 |
| FACT-X2N-009 | FACT | MediaCrawler LICENSE 仅授权非商业学习/研究并禁止大规模/扰乱性采集 | 高 |
| FACT-X2N-010 | FACT | Chrome MV3 Service Worker 通常约 30 秒空闲终止，单请求约 5 分钟限制 | 高 |
| FACT-X2N-011 | FACT | Chrome Native Messaging 支持扩展与本地应用通信，Host `allowed_origins` 不支持通配符 | 高 |
| FACT-X2N-012 | FACT | Chrome Side Panel 可在网页主内容旁承载扩展 UI | 高 |
| FACT-X2N-013 | FACT | Notion 每 Connection 平均约 3 请求/秒，并要求处理 429/529 与 Retry-After | 高 |
| FACT-X2N-014 | FACT | 当前 Notion API 支持创建和管理 View | 高 |
| FACT-X2N-015 | FACT | OpenAI 官方 API 提供 speech-to-text 和图像输入能力；本产品仍保持 Provider-neutral | 高 |
| FACT-X2N-016 | DECISION | 产品采用 Local-first Hybrid，不采用纯插件或 VPS-only | 已定版 |
| FACT-X2N-017 | DECISION | 媒体成功即删、失败不超过 24h，CDN URL 零持久化 | 已定版 |
| FACT-X2N-018 | DECISION | 一级分类由用户控制，AI 不得擅自新增 | 已定版 |
| FACT-X2N-019 | DECISION | Public Code + Private Runtime | 已定版 |
| FACT-X2N-020 | UNKNOWN | Owner 主 OS、收藏规模、Gold Set、预算和分类体系 | 由 Stage 0 获取 |

---

# 19. Evidence Registry

访问日期均为 `2026-07-19`，技术事实优先使用官方文档和项目一手仓库。

| Source ID | 来源 | URL | 支撑内容 |
|---|---|---|---|
| SRC-001 | LinzeColin/MetaDatabase | https://github.com/LinzeColin/MetaDatabase | 主仓治理、Canonical facts、证据边界 |
| SRC-002 | MetaDatabase AGENTS | https://raw.githubusercontent.com/LinzeColin/MetaDatabase/main/AGENTS.md | Task/Acceptance、范围、风险和 Stop Condition |
| SRC-003 | LinzeColin/Governance | https://github.com/LinzeColin/Governance | 共享治理框架；通过 CI checkout 或包消费，不在本项目复制 |
| SRC-004 | LinzeColin/MetaDatabase | https://github.com/LinzeColin/MetaDatabase/tree/main/xhs-douyin-2notion | 目标目录结构和 Public Repo 状态 |
| SRC-005 | MetaDatabase AGENTS | https://raw.githubusercontent.com/LinzeColin/MetaDatabase/main/xhs-douyin-2notion/AGENTS.md | Secret、Cookie、浏览器状态和数据边界 |
| SRC-006 | xiaohongshu-exporter | https://github.com/zhulin025/xiaohongshu-exporter | MV3、收藏导出和 UX |
| SRC-007 | xiaohongshu-exporter background | https://raw.githubusercontent.com/zhulin025/xiaohongshu-exporter/main/background/background.js | 主 Notion 方法未完成、Markdown 外链 |
| SRC-008 | xiaohongshu-exporter Notion module | https://raw.githubusercontent.com/zhulin025/xiaohongshu-exporter/main/exporters/notion.js | 旧 API 和外部封面 URL |
| SRC-009 | xiaohongshu-exporter TEST | https://raw.githubusercontent.com/zhulin025/xiaohongshu-exporter/main/TEST.md | 手工测试和自动化 TODO |
| SRC-010 | xiaohongshu-exporter manifest | https://raw.githubusercontent.com/zhulin025/xiaohongshu-exporter/main/manifest.json | Manifest V3、权限和 Host |
| SRC-011 | douyin-downloader | https://github.com/jiji262/douyin-downloader | likes/favorites、SQLite、重试、REST、转录 |
| SRC-012 | douyin-downloader LICENSE | https://raw.githubusercontent.com/jiji262/douyin-downloader/main/LICENSE | MIT 许可证 |
| SRC-013 | MediaCrawler | https://github.com/NanmiCoder/MediaCrawler | 公开采集、CDP、WebUI 和媒体能力 |
| SRC-014 | MediaCrawler LICENSE | https://raw.githubusercontent.com/NanmiCoder/MediaCrawler/main/LICENSE | 非商业学习/研究限制 |
| SRC-015 | Chrome Service Worker lifecycle | https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle | 空闲/单请求/Fetch 生命周期 |
| SRC-016 | Chrome Native Messaging | https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging | 本地 Host、权限、allowed_origins |
| SRC-017 | Chrome Side Panel | https://developer.chrome.com/docs/extensions/reference/api/sidePanel | Side Panel UI |
| SRC-018 | Notion Request Limits | https://developers.notion.com/reference/request-limits | 3 req/s、429/529、Retry-After |
| SRC-019 | Notion Files & Media | https://developers.notion.com/guides/data-apis/working-with-files-and-media | 文件接口；本产品默认不上传原始媒体 |
| SRC-020 | Notion Views | https://developers.notion.com/guides/data-apis/working-with-views | View 创建、过滤、排序和查询 |
| SRC-021 | OpenAI Speech to Text | https://developers.openai.com/api/docs/guides/speech-to-text | 可选云 ASR Provider 能力 |
| SRC-022 | OpenAI Images & Vision | https://developers.openai.com/api/docs/guides/images-vision | 可选 Vision Provider 能力 |
| SRC-023 | xhs-likes-manager | https://github.com/jinghan23/xhs-likes-manager | 点赞/收藏、标签、复核、Markdown |
| SRC-024 | xhs2obsidian | https://github.com/ytf606/xhs2obsidian | XHS 收藏/点赞、增量、分类和目录 |
| SRC-025 | xiaohongshu-importer | https://github.com/bnchiang96/xiaohongshu-importer | 当前页/分享链接和分类参考 |
| SRC-026 | OpenCLI | https://github.com/jackwener/opencli | 登录浏览器 Adapter/CLI 思路 |
| SRC-027 | SyncToNotion | https://github.com/openmood/SyncToNotion | 单条链接到 Notion 的交互参考 |

## 19.1 上游固定点

| 上游 | 调研时固定点 | 实施要求 |
|---|---|---|
| `zhulin025/xiaohongshu-exporter` | `130b3ceb156278597c16f7e7e98d93ff42acaadf` | 只参考行为；实现前复核 LICENSE，不复制未核验代码 |
| `jiji262/douyin-downloader` | `ef3ad18c2b50e38e534f72aabe2b3fbb0b3fadd7` | Adapter Pin、NOTICE、合同测试；升级须重新验收 |
| `NanmiCoder/MediaCrawler` | 调研时 main；实施启动时记录完整 SHA | 外部研究依赖、默认关闭、非商业限制 |
| Notion API | 文档示例版本含 `2026-03-11` | 实施时固定经合同测试的 `Notion-Version`，不得隐式漂移 |
| Chrome APIs | 2026-07-19 官方文档 | Manifest `minimum_chrome_version` 由实现能力测试确定 |

---

# 20. PRD 变更控制

任何以下变化必须提升任务包 Patch 版本并记录：

- 新平台、新关系类型或新数据 Sink；
- 媒体持久化策略；
- Public/Private 边界；
- 一级分类权限；
- VPS 数据平面；
- 上游许可证或集成方式；
- Canonical Schema 破坏性变更；
- Acceptance Threshold；
- 模型 Provider 默认值；
- 自动删除行为；
- Chrome 权限扩大；
- 新第三方数据上传。

变更最小记录：

```yaml
change_id:
date:
owner:
old_fact:
new_fact:
reason:
evidence:
affected_requirements:
affected_acceptances:
migration:
rollback:
risk:
```
