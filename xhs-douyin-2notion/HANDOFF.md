# HANDOFF

## 当前目标

按 v0.0.0.1 Task DAG Stage 0–6 构建 `LinzeColin/MetaDatabase` 下唯一子项目 `xhs-douyin-2notion/`。产品终态覆盖小红书、抖音、哔哩哔哩、快手、微博和淘宝，但始终限定为 Owner 明确选择内容的个人知识治理，不是通用爬虫。

## 当前状态

- `Stage 0 / Phase 0.1、0.2、0.5`：历史 Task/receipt 复验 PASS；`TSK.x2n.discovery.001–005` 全部完成。
- `STG.X2N.0.REVIEW`：本地 Review/Fix/Re-acceptance 完成；5 个可本地修复 Finding 已关闭。
- `RUN-X2N-S00-REVIEW-RESUME-PREP`：已补齐非秘密 Owner 恢复回执的闭合 Schema、私有逻辑路径、生成器、fail-closed verifier 与负向测试；没有创建真实回执。
- `G0`：`BLOCKED_OWNER_ACTION`，不是 PASS。`INC-X2N-S00-P05-001` 要求 Owner 在 G0 前轮换/重新认证或提供旧凭据失效证明。
- Stage 1、产品代码、真实账号、平台/Notion/模型调用、媒体下载与远端上传：全部未授权/`NOT_RUN`。
- 六个平台：全部 `UNKNOWN_DISABLED`；任何平台须在对应 Task 开始时重新通过独立 Policy/Auth/Technical/Canary Gate。
- Task Pack：32 Requirements、43 Tasks、61 Acceptances、7 个 Stage Gates；普通 Run 最多执行一个 DAG Task 及其 Acceptance；Stage Review 不执行新 Task。

## Review 关键修复

1. 三个 Phase verifier 精确支持独立 `s00-review` 分支，完整复验不再被旧 branch allowlist 阻断。
2. 执行粒度从“每 Run 一个 Phase”收紧为 Owner 要求的“每 Run 一个 DAG Task”；历史 P01 的三 Task 同 Run 已登记为流程不符合项并逐 Task 重验，未来不能批量带做同 Phase Task。
3. 删除 `MediaCrawler` 产品 Adapter Feature Flag 与外部安装残留语义；下载父目录名只代表存储位置，不是上游授权。
4. 将长期并行的 moving `origin/main` 固定为明确 Review cutoff；cutoff 后无关提交不吸收，触及 x2n 才 Fail Closed。
5. 将凭据恢复从文字要求收紧为闭合 Owner Attestation：禁止自由文本/Secret/账号/URL，缺失或非法均保持阻断，合法也只允许 Review Resume。

## 不变边界

- 唯一母仓库/子项目：`LinzeColin/MetaDatabase` / `xhs-douyin-2notion/`。
- 原始 taskpack 未指定本机绝对下载路径。Owner 指定的 `X2N_DATA_ROOT` 是 `X2N_DOWNLOAD_DESTINATION` 下 `xhs-douyin-2notion/` 隔离命名空间；Runtime 与全部下载共用该根。
- 目的地已有同级条目只允许不回显名称的聚合元数据审计；不读取内容、不导入、不链接、不修改、不删除。
- Public Code / Private Runtime；代码和数据均专有。SQLite Canonical Store 是唯一真相源；Markdown/Notion 是可重建 Sink。
- 不持久化平台媒体 CDN URL、凭据、Cookie、浏览器状态或原始媒体；AI 不得创建一级分类；不自动滚动、不改变账号状态、不绕过平台控制。
- `ShilongLee/Crawler` 与 MediaCrawler 仅为固定 Commit 的不可执行研究证据：不复制、不 Vendor、不安装、不运行、不接收输出、不作 Runtime Dependency。

## Review 证据与验证

- 人类报告：`docs/governance/STAGE_0_REVIEW.md`
- 机器状态：`machine/facts/stage_gate_state.json`
- 机器证据：`machine/evidence/stage_0/review/{verification,G0,external_revalidation}.json`
- Review cutoff：`origin/main@9f68c69becc31b0626b387eb36711235cf48af6f`
- 历史 Phase receipt：20 个 JSON，Review 未重写；下游产品/Release Oracle 保持 `NOT_RUN`。
- 复验：Review verifier 10 项 PASS；Phase 0.1/0.2/0.5 完整 verifier PASS；28 tests PASS、2 个仅私有可选输入测试按设计 skip。

```bash
python3 -B scripts/verify_stage_0_review.py --verify-worktree --allow-external-main-dirty --verify-local-root --source-roadmap "$X2N_SOURCE_ROADMAP" --source-taskpack "$X2N_SOURCE_TASKPACK" --require-evidence
python3 -B scripts/verify_phase_0_1.py --verify-worktree --allow-external-main-dirty --verify-local-root --source-roadmap "$X2N_SOURCE_ROADMAP" --source-taskpack "$X2N_SOURCE_TASKPACK"
python3 -B scripts/verify_phase_0_2.py --verify-worktree --allow-external-main-dirty --verify-temp-cleanup --require-evidence
python3 -B scripts/verify_phase_0_5.py --verify-worktree --allow-external-main-dirty --validate-owner-input "$X2N_DATA_ROOT" --verify-temp-cleanup --require-evidence
python3 -B scripts/verify_owner_recovery_attestation.py  # 当前预期 exit 2 / BLOCKED_OWNER_ACTION
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

## 未解决风险

- 唯一 G0 阻断项是 `INC-X2N-S00-P05-001` 的凭据生命周期证明。不得把本地扫描 0 命中解释为旧凭据已失效。
- 当前政策复核不构成法律或平台授权；每个平台启动实现时必须查当时有效的一手条款、Scope、成本和技术路径。
- Owner 尚未提供真实分类、规模、登录态、Notion 父级/凭据或云模型预算；保守默认足以继续未来合成开发，但不授权真实同步。
- 所有 Canonical/Adapter/媒体/模型/Sink/恢复/发布 Acceptance 仍按 DAG 未运行，不能从 Stage 0 设计证据外推。

## 唯一下一步

Owner 直接确认已经完成以下一项：轮换并撤销旧材料、重新认证并撤销旧材料、或在 Provider 侧确认旧材料已失效；不得提供凭据值。之后才可用 `record_owner_recovery.py` 生成私有闭合回执，并新开 `STG.X2N.0.REVIEW.RESUME` 重跑事件恢复、扫描和 G0 判定。合法回执本身不等于 G0 PASS；只有 Resume 的机器 G0 PASS 后才可上传整个 Stage 0，并另行开始 Stage 1 的首个单 Task Run。
