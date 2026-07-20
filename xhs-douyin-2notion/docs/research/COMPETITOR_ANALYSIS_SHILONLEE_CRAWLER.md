# 竞品深审：ShilongLee/Crawler

## 结论先行

`ShilongLee/Crawler` 是一个多平台 FastAPI 聚合服务，覆盖小红书、抖音、哔哩哔哩、快手、微博、淘宝和京东的搜索、详情、评论、回复、用户等能力。它证明了“平台隔离适配器＋统一能力词汇”能快速扩平台，但其许可证、安全、隐私、账号安全、测试和知识治理模型都不能直接进入 x2n。

决策是：**0 行复制、0 Vendor、0 Runtime Dependency；仅 clean-room 蒸馏架构思想。** x2n 要超越的不是端点数量，而是合规授权、用户意图边界、Canonical Truth、证据、幂等恢复、临时媒体生命周期、多模态治理和可验证发布。

## 固定研究对象与可复现证据

- Repository：<https://github.com/ShilongLee/Crawler>
- 精确 Commit：[`765207310a90a81c615c0ba2df124543b424af89`](https://github.com/ShilongLee/Crawler/commit/765207310a90a81c615c0ba2df124543b424af89)
- Tree：`3fe084d7e3835669ccdb4193312b065a48eeb5d7`
- Commit 时间：`2026-06-09T11:22:55+08:00`
- `readme.md` SHA-256：`84594484e8627f9e3ffc137b3512a22f6294e4b444a4d20feafa2a036ce7e7e0`
- `LICENSE` SHA-256：`3f24dc89c6bd61714b4dc583b8c8ccb4a54e5190b6efc3135e540d59e4599b58`
- `requirements.txt` SHA-256：`f588c18cdad6b247ee17bd8fd0bb4f7b4f2c5f0226f162696784d731487c9971`
- 规模快照：177 个非 Git 文件；7 个内容/电商平台模块＋1 个代理模块；56 个账号/内容 Route＋5 个代理 Route；`requirements.txt` 有 46 行精确版本 Pin。
- 历史判断：2025–2026 的提交主要是 README 赞助/折扣内容；最后可见的依赖代码变更在 2024-10，且 Starlette 升级随后被回退。此结论只针对固定 Commit，不推断未来版本。

临时源码只用于本地只读核查，并在本 Run 结束前删除；仓库只保留本摘要、Hash 和机器登记。

## 可 clean-room 蒸馏的思想

| 竞品做法 | x2n 蒸馏结果 | 超越点 |
|---|---|---|
| 每个平台分 `logic/models/urls/views` | 每平台独立 Adapter Package | 统一 versioned contract、Capability Manifest、Feature Flag、Kill Switch |
| 统一 detail/search/comments/replies/user 词汇 | 统一 `current_page/selected_collection/preview/ephemeral_download/classify` | 只保留个人知识治理所需最小能力，不做全网搜索/评论网络 |
| offset/limit 参数 | 有界 Batch Contract | 最大条数、Deadline、Checkpoint、取消、完整性 Receipt |
| 集中 Route 注册 | Adapter Registry | 无能力即 `UNKNOWN_DISABLED`，不可假成功 |
| 平台签名逻辑隔离 | 平台授权策略隔离 | 官方 API/OAuth 优先；未文档化签名默认禁止 |
| 视频 preview Route | 本地临时媒体 Lease | Host/IP/Redirect/MIME/Size/Timeout 防火墙；不做任意 URL 代理 |
| 账号表/过期状态 | Session Health 抽象 | Owner 管理 Chrome Profile；不接收/存储/返回/记录 Cookie |

## 不可整合的许可证边界

固定 Commit 的 `LICENSE` 是自定义“非商业使用许可证 1.0”：仅授予非商业使用、复制、修改、合并权利，要求保留声明，并禁止商业用途和商业竞争。x2n 的专有分发用途与未来商业性质尚未获得兼容授权，因此：

- 禁止复制、修改、合并、翻译、Vendor、容器化打包或作为 Runtime Dependency；
- 禁止把其生成/混淆签名 JavaScript、平台 URL、Header/参数模板或测试数据移植到 x2n；
- 允许阅读公开行为并从零实现通用架构思想，但实现者不得边看源码边逐行重写；
- 未来若要使用任何代码，必须取得权利人书面商业授权并新开 License/Provenance Run。

## 安全与隐私差距

| 严重度 | 固定 Commit 观察 | x2n 门禁 |
|---|---|---|
| Critical | SQLite 账号表明文保存 Cookie；`add_account` 接收并记录 Cookie；账号列表可返回整行 | Cookie/凭据绝不进入 API、SQLite、日志或 Git；专用 Profile＋Keychain 引用 |
| Critical | FastAPI 默认绑定 `0.0.0.0:8080`，未见服务级鉴权 | Local Companion 仅 loopback/Native Messaging；每请求 origin、schema、nonce、size 校验 |
| Critical | 微博 preview 接受任意 URL 并由服务器请求，未见 Host/私网/Redirect/Size/Timeout 策略 | 默认拒绝；解析后逐跳验证 allowlist、DNS/IP、Scheme、Port、MIME、长度与预算 |
| High | 代理 Route 接收、保存、轮换任意代理；README 宣称绕过地域和频率限制 | 代理轮换、地域/频率规避永久禁止；触发限流即退避/停止 |
| High | 通用请求日志可写 Header、请求参数、完整响应 | 结构化 Allowlist 日志；Cookie、Token、平台 URL Query、正文默认不记录 |
| High | B站下载脚本接收 Host/URL/输出目录，整响应进内存并落原始 m4s/mp4 | 下载目标与路径不可由远端输入；Stream＋硬上限＋Lease；成功立即清除原始媒体 |
| High | 抖音/小红书签名脚本与 B站设备/鼠标参数模拟 | 不复制、不伪装设备/用户行为；未知授权策略即禁用 |
| Medium | 搜索、评论、回复、用户等广域采集能力 | 只处理用户明确选择的内容/个人列表；无通用爬虫 Route |

## 可靠性、测试与供应链差距

- 账号数据库不是内容 Canonical Store；没有 Content/Relation 唯一键、Observation、Checkpoint、Outbox、Artifact Version、Evidence Receipt 或 Tombstone 两阶段保护。
- 测试脚本依赖真实 Cookie、已运行 Server、当时有效的平台 ID 和 sleep；不是隔离的 Unit/Contract/Chaos 测试。
- CI 只构建并推送 Docker；未见测试、Lint、Secret/CDN、License、SBOM 或 Release Gate。Action 使用 mutable major tags。
- 依赖文件无 Hash Lock，且固定 Commit 的主要代码依赖基线陈旧；启用前需要独立当前漏洞/兼容性评估。
- 不提供 Markdown/Notion 幂等投影、ASR/OCR/关键帧证据、分类治理、删除/导出/恢复闭环。

## x2n 的“超越”验收定义

1. 六平台都有独立 Capability Matrix，任何策略/Scope/技术未知时单平台禁用，不拖垮其余平台。
2. 用户手势和明确批次是每次采集的授权边界；无自动滚动、无账号状态变化、无反自动化规避。
3. SQLite 是唯一真相源；相同输入重跑、崩溃恢复、Sink 重建均零重复副作用。
4. 预览/下载只用短生命周期 Lease；所有持久层平台 CDN URL、凭据和原始媒体命中为 0。
5. 每条知识资产可追溯到 Observation、ASR/OCR/关键帧、分类决策和 Sink Receipt；AI 不能创建一级分类。
6. 公开仓库只有专有代码、Schema、合成 Fixture 和脱敏证据；真实 Runtime 永不进入 Git/CI Artifact。
7. 40+ 合成治理/攻击用例、Stage Gate、回滚演练和独立 Owner Alpha 共同定义“支持”，而不是 Route 存在或请求返回 200。

## 本轮限制

本分析不运行竞品、不连接平台、不验证真实 Cookie/端点、不下载媒体，也不对竞品作者或未来版本作安全结论。平台政策和公开接口可能变化，正式实现前必须重新查一手来源。
