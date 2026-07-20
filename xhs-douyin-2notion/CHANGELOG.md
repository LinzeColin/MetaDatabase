# Changelog

## v0.0.0.1 — Stage 0 Review Resume / G0 PASS

- 依据 `CE-X2N-20260720-S00-REVIEW-RESUME` 将共享认证材料限定为 x2n 外部、Owner 管理的并行基础设施；x2n 不读取、使用、改变或显示它，也不修改全局 Git 配置或 Credential Helper。
- 保留 Secret/CDN 不可 Owner waiver 的全局规则；新增匿名公开 GitHub Snapshot 工具与 11 项零接触控制。
- 用闭合 `0600` 私有回执记录 Owner 决策；公开证据不含回执 ID、时间、哈希、账号、URL、本机路径或材料值。
- 完整重跑当前树、项目历史、私有根、Local Remote、原始输入、Phase 0.1/0.2/0.5、历史证据与 G0；所有敏感形态扫描为 0，cutoff 后 x2n overlap 为 0。
- 首次 Review 的 `BLOCKED_OWNER_ACTION` 证据保持不变；新 `review_resume/` 证据签发 `G0 PASS`。
- Stage 0 整阶段上传与下一独立 Run 的 `TSK.x2n.foundation.001` 已授权；本 Resume Run 未执行产品代码、账号、平台、Notion、模型或媒体操作。

## v0.0.0.1 — Stage 0 Review

- 基于 `origin/main` 明确 cutoff 完成独立 Review/Fix/Re-acceptance；cutoff 后无关长期开发不吸收，触及 x2n 才阻断。
- 修复三个旧 Phase verifier 不接受独立 Review 分支的问题，并完整重跑 Phase 0.1/0.2/0.5。
- 将 Owner 执行约束从“每 Run 一个 Phase”收紧为“每普通 Run 一个 DAG Task 及其 Acceptance”；Stage Review 是不执行新 Task 的专用例外。
- 删除残留 `MediaCrawler` 产品 Adapter Feature Flag 和“外部安装”措辞；下载父目录名仍只代表存储路由，受限上游保持零安装、零执行、零输出接收。
- 复核原始 roadmap/ZIP 固定哈希；确认原输入没有指定 macOS 下载绝对路径。
- 重新核对 `ShilongLee/Crawler` 固定提交与 Chrome/Notion/六平台一手来源；竞品提交未漂移，六平台仍全部 `UNKNOWN_DISABLED`。
- 28 个单测通过（2 个私有可选输入测试按设计跳过），20 份历史 Phase receipt 保持未改，产品/账号/平台/Notion/模型/媒体均 `NOT_RUN`。
- 本地自动门禁通过，但 `INC-X2N-S00-P05-001` Owner Action 未完成；真实结论为 `G0_BLOCKED_OWNER_ACTION`，Stage 1 与远端上传继续禁止。
- Review Follow-up 修复了 Owner Recovery 仅有文字要求的盲点：新增闭合 Schema、合成 Fixture、不可覆盖的私有生成器和缺失/恶意/越权负向 verifier；没有生成真实回执，G0 状态不变。

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
