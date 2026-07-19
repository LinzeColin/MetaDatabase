# Changelog

## v0.0.0.1 — Stage 0 / Phase 0.5

- 通过 Owner Change Event 将终态范围扩为六平台，保留稳定项目名；DAG 从 35 增至 43 Task、需求从 28 增至 32、Acceptance 从 49 增至 61。
- 按 Owner 指令把子项目统一为 `xhs-douyin-2notion/`；记录原始 taskpack 未指定本机绝对下载路径，并将私有根固定为 Owner 下载目的地下同名隔离命名空间，既有同级条目触碰数为 0。
- 固化六平台 Capability/Policy/Auth 独立门禁、Feature Flag、Kill Switch 与所有下载统一 `X2N_DATA_ROOT` 契约。
- 完成 Chrome/CWS、Notion 和六平台一手政策快照、ADR-001–010、DFD/STRIDE、20 条 Stop/Kill 与 50 条合成治理用例。
- 深审 `ShilongLee/Crawler` 固定 Commit；因自定义非商业 License 与安全/隐私差距，限定为 clean-room ideas only，0 copy/vendor/runtime dependency。
- 收紧受限上游边界：ShilongLee/Crawler 与 MediaCrawler 仅为不可执行审计参考，不安装、不运行、不接收输出，也不是产品 Adapter。
- Owner 未提供值全部采用可逆保守默认；六平台、Notion、云模型、真实同步均保持关闭。
- 临时研究 remote 的凭据形态 URL 已按 `INC-X2N-S00-P05-001` 隔离：临时副本删除、项目/私有根文件扫描 0 命中；G0 前仍需轮换/重新认证或过期证明。
- 新增 Owner 指定的长期并行 worktree 隔离：默认仍要求 clean main，显式 override 仅在外部 dirty paths 与 x2n 零重叠时通过，公开证据只记录计数。
- 未进入产品代码、真实账号、平台/Notion/模型请求、Stage Gate 或远端上传。

## v0.0.0.1 — Stage 0 / Phase 0.2

- 精确登记 xiaohongshu-exporter、douyin-downloader 与 MediaCrawler 的 Commit/tree/关键文件哈希。
- 建立 Dependency Registry、Capability Matrix、License/NOTICE、SBOM dry run 与 Shadow-upgrade Plan。
- 将 xhs exporter 限定为 clean-room reference，将 MediaCrawler 限定为 external non-commercial research；douyin wrapper 保持关闭并等待 exact lock 与 Adapter contract。
- 平台个人点赞/收藏官方能力未确认时保持 `UNKNOWN / DISABLED`。
- 未运行上游或产品代码，未访问真实账号，未进入 Phase 0.5、Stage Gate 或远端上传。

## v0.0.0.1 — Stage 0 / Phase 0.1

- 注册唯一母仓库、子项目和 Stage 0–6 Task DAG。
- 将 Runtime 与全部 Adapter 下载统一到私有逻辑根 `X2N_DATA_ROOT`。
- 建立 Public Artifact / Private Runtime 路径契约、合成 Fixture 清单和机器验证入口。
- 保存原始输入 SHA-256，并以 Owner Change Event 记录路由与路径修正。
- 未进入产品代码、真实账号、浏览器、Notion、模型或媒体执行。
