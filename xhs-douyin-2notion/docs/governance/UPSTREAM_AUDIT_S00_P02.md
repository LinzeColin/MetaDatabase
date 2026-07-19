# Upstream Audit — v0.0.0.1

审计时点：`2026-07-19T10:51:46Z`。证据来自官方 Git 仓库精确对象与一手平台文档；没有运行上游代码、安装依赖、登录账号或下载媒体。

## Commit 与 License 结论

| 候选 | 本轮 `main` / 选定 Commit | License 证据 | x2n 决策 |
|---|---|---|---|
| `zhulin025/xiaohongshu-exporter` | `130b3ceb156278597c16f7e7e98d93ff42acaadf` | README 声称 MIT，但该 tree 没有 LICENSE/COPYING/NOTICE | 仅 clean-room 行为/UX 参考；复制代码、库和 zip 数为 0 |
| `jiji262/douyin-downloader` | `ef3ad18c2b50e38e534f72aabe2b3fbb0b3fadd7` | tree 内 MIT LICENSE，Copyright 2026 jiji262 | 未来仅可经禁用默认的 wrapper；先补 exact lock、transitive license/SBOM 与 Adapter contract |
| `NanmiCoder/MediaCrawler` | `0625e01a6bc717a3fc9c96d3dac7fb8957043838` | NON-COMMERCIAL LEARNING LICENSE 1.1 | 外部、可选、非商业研究专用；不得成为核心依赖或发布制品 |

三个选定 Commit 在审计时均等于各自 `origin/main`。这只是本轮 ref 观测，不是永久 `latest`；机器登记同时保存 tree、关键 blob 与 SHA-256。

## Capability Matrix

| 能力/约束 | xhs exporter | douyin downloader | MediaCrawler | x2n 处理 |
|---|---|---|---|---|
| 当前内容 | 页面采集 | 单作品下载 | xhs/dy 等多平台 | 后续仅用户明确选择 |
| 点赞/收藏 | 收藏夹 | `like`、`collect`、`collectmix` mode | 搜索/详情/创作者等 crawler 流程 | 官方授权未知时关闭；不自动滚动 |
| 自动滚动 | 源码调用 `window.scrollTo` | 非 Chrome 页面实现 | crawler 自动化 | 全部禁止继承 |
| 账号状态 | 请求 cookies permission 并保存采集进度 | 支持 cookie 文件/自动 cookie | 保存登录态、浏览器 profile | x2n 不持久化凭据，不改变账号状态 |
| 默认下载根 | Chrome downloads | `./Downloaded/` | `data/<platform>/...` 或配置路径 | 未来必须强制 `${X2N_DATA_ROOT}` |
| 持久化 | `chrome.storage.local`、Markdown 外链封面 | SQLite full metadata/cover URLs/path、JSON/manifest | JSON/DB/媒体及 URL 字段 | 上游存储不得成为 Canonical；先净化再入 SQLite |
| Notion | background 路径抛出“开发中”；另一 exporter 使用 external image | 无 | 无 | 不复用；Stage 5 Outbox，禁止 CDN URL |
| Dependency lock | 无 manifest/lock，含 minified JS 与 zip | pyproject/requirements 多数是范围约束，无 lock | `uv.lock` 存在 | 当前实际 runtime dependency 均为 0 |
| 发布边界 | License 未核验 | MIT notice 可准备 | 非商业限制 | xhs/MediaCrawler 不 bundled；douyin 仍 disabled |

## 源码与 Schema 观察

### xiaohongshu-exporter

Manifest V3 v1.6.3 请求 `storage`、`cookies`、`activeTab`、`downloads`，host 还包含小红书、edith、飞书与 Notion。源码的收藏采集会自动滚动，并把进度放进 `chrome.storage.local`；本地 Markdown/HTML 和 Notion exporter 会引用外部封面 URL。background 的 Notion 创建函数实际抛出“开发中”，因此 README 能力不能当作完成证据。仓库还包含 minified library 与预打包 zip，均不得复制。

### douyin-downloader

项目版本 2.0.0、Python `>=3.9`、CLI `douyin-dl=cli.main:main`。核心依赖中仅 `imageio-ffmpeg==0.6.0` 精确固定，其余多为 `>=`；tree 没有 lock。因此精确 Git Commit 不能替代可复现 Python 环境。其数据库会保存 full metadata、cover URLs、file path 和 transcript path，metadata handler 还会写 JSON/JSONL manifest；未来 wrapper 必须关闭这些上游持久化，强制私有根，先验证版本与 Schema，再正规化到 x2n Canonical。

`like` 与 `collect` mode 在源码中存在，但这只证明上游实现形状，不证明平台授权、完整性、稳定性或 x2n 合规性。

### MediaCrawler

项目版本 0.1.0、Python `>=3.11`，依赖面大且包含 Playwright、Web/API、数据库和媒体处理。默认配置可保存登录态、开启 CDP、抓评论并写 JSONL/DB/媒体；xhs store 包含 `video_url`、`image_list`、`xsec_token` 等字段。即使有 `uv.lock`，许可证和产品边界仍决定它只能保持 external research、默认关闭且不进入发布物。

## 官方平台文档边界

抖音官方文档确认 OAuth/权限申请机制，并列出公开信息、作品数据、评论等 scope；更深用户侧数据需要用户主动授权和平台合作申请。本轮没有找到明确、默认可用且覆盖“个人已点赞视频列表 + 收藏视频/收藏夹列表”的官方接口，因此所需能力登记为 `UNKNOWN / DISABLED`，不得把上游能运行等同于平台授权。

针对小红书，本轮定向官方公开文档检索没有确认适用于该个人知识治理用例的点赞/收藏读取接口。缺失不能推导为许可或禁止；结论同样是 `UNKNOWN / DISABLED`，在 Phase 0.5 以当前条款和账号安全门禁复核。

Chrome Side Panel、Chrome Web Store 政策与 Notion 文件上传现行规则已登记为后续一手来源，但按 Task DAG 由 Phase 0.5/Stage 5 定版，本轮不越界宣告合规。

## 当前 Gate

- 允许继续 Stage 0 Phase 0.5：是。
- 允许启用任一上游：否。
- 允许复制 xhs exporter 或 MediaCrawler 代码：否。
- 允许打包 douyin-downloader：否；需要 exact integration lock、transitive license/SBOM、synthetic Adapter contract 全通过。
- 允许进入 Stage 1 或 push：否；Stage 0 Gate 尚未执行。
