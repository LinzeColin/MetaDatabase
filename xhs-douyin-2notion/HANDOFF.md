# HANDOFF

## 当前目标

按 v0.0.0.1 Task DAG Stage 0–6 构建 `LinzeColin/MetaDatabase` 下唯一子项目 `xhs-douyin-2notion/`。产品终态覆盖小红书、抖音、哔哩哔哩、快手、微博和淘宝，但始终限定为 Owner 明确选择内容的个人知识治理，不是通用爬虫。

## 当前状态

- `Stage 0 / Phase 0.1`：PASS；`TSK.x2n.discovery.001–003` 完成。
- `Stage 0 / Phase 0.2`：PASS；`TSK.x2n.discovery.004` 完成，历史上游审计证据保持不变。
- `Stage 0 / Phase 0.5`：PASS；`TSK.x2n.discovery.005` 完成，仅治理设计与合成验证。
- Task Pack：32 Requirements、43 Tasks、61 Acceptances、7 个 Stage Gates；DAG cycle `0`。
- 六个平台当前均为 `UNKNOWN_DISABLED`；产品代码、真实账号、平台/Notion/模型调用、媒体下载均为 `NOT_RUN`。
- Stage 0 Gate `G0`：`NOT_RUN`。下一 Run 只能是独立 `STG.X2N.0.REVIEW`；远端上传仍禁止。
- Owner 已要求与 MetaDatabase 内长期外部开发并行隔离；本 Run 仅在显式 flag 下接受外部主树非 x2n dirty path，机器门禁要求 x2n overlap 为 `0`，不读取或复制外部 diff。
- 本轮临时源码 remote 曾出现凭据形态 URL；临时副本已删除，项目与私有根文件级扫描为 0 命中，但凭据是否已失效未知。`INC-X2N-S00-P05-001` 要求在 `G0 PASS` 前轮换/重新认证或提供过期证明。

## 关键决策

- 唯一母仓库/子项目：`LinzeColin/MetaDatabase` / `xhs-douyin-2notion/`；旧仓库命名不是输入或回退目标。
- 原始 taskpack 未指定本机绝对下载路径。Owner 指定 `X2N_DOWNLOAD_DESTINATION`，`X2N_DATA_ROOT` 是其下 `xhs-douyin-2notion/` 隔离命名空间；Runtime 与全部未来下载共用该根。目的地已有同级条目只做不回显名称的聚合数量/元数据指纹审计，不读取内容、不导入、不链接、不修改、不删除；父目录与上游软件同名不构成安装、运行或 Adapter 授权。
- Public Code / Private Runtime；SQLite Canonical Store 是唯一真相源；Markdown/Notion 是可重建 Sink。
- 不持久化平台媒体 CDN URL、凭据或原始媒体；媒体成功立即删除、失败租约最长 24 小时；AI 不得创建一级分类。
- 六平台各自具 Policy/Auth/Technical/Canary Gate、Capability Manifest、Feature Flag 和 Kill Switch；未知一律禁用，不允许以一平台结果外推其他平台。
- 禁止自动滚动/翻页、账号状态变化、访问控制/CAPTCHA 绕过、代理轮换、地域/频率规避、设备/鼠标指纹模拟、Cookie 导出、未文档化签名复制和任意 URL 代理。
- `ShilongLee/Crawler` 与 MediaCrawler 仅作不可执行的固定 Commit 审计/竞品研究参考：不复制、不 Vendor、不安装、不运行、不接收输出、不作 Runtime Dependency。旧 Phase 0.2 登记是历史审计证据，不构成未来 Adapter 授权。

## Phase 0.5 产出

- Run/Change/Owner/Policy：`docs/governance/RUN_CONTRACT_S00_P05.md`、`CHANGE_EVENT_S00_P05.md`、`OWNER_INPUT_CONTRACT.md`、`PLATFORM_POLICY_REGISTER_S00_P05.md`、`PARALLEL_WORKTREE_ISOLATION.md`
- 架构/安全：`docs/architecture/ARCHITECTURE_DECISIONS_S00_P05.md`、`docs/security/THREAT_MODEL_S00_P05.md`、`STOP_KILL_INCIDENT_REGISTER.md`
- 竞品研究：`docs/research/COMPETITOR_ANALYSIS_SHILONLEE_CRAWLER.md`
- 机器契约：`machine/facts/{architecture_decisions,competitor_registry,platform_scope_registry}.json`、`machine/policy/{platform_policy_registry,stop_kill_registry,worktree_isolation_policy}.json`
- Owner/Fixture：`machine/schemas/owner_input_contract.schema.json`、`machine/fixtures/stage_0_governance_cases.json`
- 验收器：`scripts/verify_phase_0_5.py`、`tests/test_phase_0_5.py`
- 私有 Owner defaults：只在 `X2N_DATA_ROOT`，权限 `0600`；六平台真实执行、Notion、云模型均关闭。

## 验证命令

```bash
python3 -B scripts/verify_phase_0_1.py --verify-worktree --allow-external-main-dirty --verify-local-root
python3 -B scripts/verify_phase_0_2.py --verify-worktree --allow-external-main-dirty --verify-temp-cleanup --require-evidence
python3 -B scripts/verify_phase_0_5.py --verify-worktree --allow-external-main-dirty --validate-owner-input "$X2N_DATA_ROOT" --verify-temp-cleanup --require-evidence
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

Phase 0.5 核心指标：10 个 ADR、10 个 Trust Boundaries、20 个 Stop/Kill Rules、50 个纯合成治理/攻击用例；ShilongLee/Crawler 研究对象固定到 Commit `765207310a90a81c615c0ba2df124543b424af89`，观察 177 个非 Git 文件、61 个 Route、46 行依赖 Pin，代码复制与 Runtime Dependency 均为 `0`。

## 未解决风险

- “六平台终态范围”不等于当前运行支持；每个平台开始实施前都必须重新核验当时有效的一手政策、Scope、授权、技术路径和 Canary 门禁。
- Owner 尚未提供真实分类、数据规模、登录态、Notion 父级/凭据或云模型预算；当前 Fail-Closed defaults 足以继续合成开发，但不能启动真实同步。
- 抖音旧候选 Wrapper、所有平台 Adapter、Canonical/媒体/模型/Sink/恢复/发布的下游 Acceptance 均未运行。
- Stage 0 尚未进行全阶段 Review/Fix/Re-acceptance，`G0` 不能判 PASS，也不能 push。
- 临时研究 remote 的凭据生命周期未获证明；本地合成工作可继续，但在 Owner 完成轮换/重新认证或确认已失效前不得通过 `G0`。
- MetaDatabase 外部主树可能持续变化；本 Run 不触碰它。下一 `STG.X2N.0.REVIEW` 必须基于当时的 `origin/main` 做独立同步/冲突核验，不能沿用本轮零重叠结论。

## 下一步

新 Run 仅执行 `STG.X2N.0.REVIEW`：对 Phase 0.1/0.2/0.5 做整阶段独立审查、修复、重新验收并决定 `G0`。只有 `G0` 有可复核 PASS 证据后，才可整 Stage 上传并另行授权 Stage 1；不得在本 Run 直接开发产品代码。
