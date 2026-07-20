# Run Contract — Stage 0 Review / Fix / Re-acceptance

## 1. 身份与目标

- Run ID：`RUN-X2N-S00-REVIEW`
- Review ID：`STG.X2N.0.REVIEW`
- 母仓库/子项目：`LinzeColin/MetaDatabase` / `xhs-douyin-2notion/`
- 目标：独立复核 Phase 0.1、0.2、0.5 的 requirement→output→evidence→verifier，修复 Stage 0 范围内缺陷，并对 `G0` 作 Fail-Closed 决定。

本 Run 是 Stage 完成后的专用 Review，不执行新的 DAG Task，不构成进入 Stage 1 的授权。

## 2. 最小范围

- 读取最新 `origin/main`，在独立 review worktree 中同步并处理仅与 x2n 有关的冲突。
- 复核 `TSK.x2n.discovery.001–005`、G0 五项 Pass Condition、四项 Stop Condition及已登记的安全事件。
- 复跑三个 Phase verifier、原始输入哈希、私有根边界、全量单测和负向门禁。
- 只修改 `xhs-douyin-2notion/**` 内 Stage 0 治理、验证、证据与状态文件；母仓库根 `README.md` 仅承接已完成的上游同步合并，不再修改。

## 3. 明确非目标

- 不进入 Stage 1，不创建产品 Scaffold、Extension、Companion、SQLite、Adapter、模型或 Sink 代码。
- 不访问真实账号，不调用六个平台、Notion 或模型，不下载/处理媒体。
- 不安装、运行、包装或读取 MediaCrawler/ShilongLee Crawler 输出。
- 不读取、恢复、stash、暂存或提交 MetaDatabase 其他长期开发的 diff；只记录外部 dirty path 聚合计数与 x2n overlap `0`。
- 不 push，不创建 PR，不把 `UNKNOWN/NOT_RUN` 包装成 PASS。

## 4. Review 前置事实

- Review 分支必须精确为 `codex/xhs-douyin-2notion-v0001-s00-review`。
- Review 开始/刷新时记录的 `origin/main` 明确 cutoff 必须是当前 Review `HEAD` 的祖先；同步冲突必须显式解决并保留双方有效事实。cutoff 后继续发生的长期并行提交仅在触及 x2n 时阻断，不能让无关开发迫使本 Run 永远追逐 moving main。
- 原始 roadmap/ZIP 只读核验，SHA-256 必须与 Source Manifest 一致；原始 taskpack 未指定本机下载绝对路径。
- `X2N_DATA_ROOT` 只允许解析为 Owner 下载目的地下的 `xhs-douyin-2notion` 隔离命名空间；Evidence 不记录绝对路径。

## 5. 已发现并纳入修复的事项

1. 旧 Phase verifier 的 worktree branch allowlist 不认识独立 Review 分支，导致全量复验失败。
2. Owner 的“每 Run 一个 Task”约束被项目文档放宽成“每 Run 一个 Phase”，可能让未来 Run 批量执行多个 Task。
3. 产品文档仍残留永久关闭的 `mediacrawler_adapter` 占位和“外部安装”措辞，与 P05 后确立的不可执行研究边界冲突。
4. `INC-X2N-S00-P05-001` 已本地隔离，但凭据生命周期仍无 Owner 轮换/重新认证或失效证明，必须阻断 `G0 PASS`。

## 6. 验证命令

```bash
python3 -B scripts/verify_stage_0_review.py --verify-worktree --allow-external-main-dirty --verify-local-root --source-roadmap "$X2N_SOURCE_ROADMAP" --source-taskpack "$X2N_SOURCE_TASKPACK" --require-evidence
python3 -B scripts/verify_phase_0_1.py --verify-worktree --allow-external-main-dirty --verify-local-root --source-roadmap "$X2N_SOURCE_ROADMAP" --source-taskpack "$X2N_SOURCE_TASKPACK"
python3 -B scripts/verify_phase_0_2.py --verify-worktree --allow-external-main-dirty --verify-temp-cleanup --require-evidence
python3 -B scripts/verify_phase_0_5.py --verify-worktree --allow-external-main-dirty --validate-owner-input "$X2N_DATA_ROOT" --verify-temp-cleanup --require-evidence
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

`--allow-external-main-dirty` 只适用于 Owner 已明确要求的长期并行情形，且必须证明 x2n overlap 为 `0`。正常环境仍默认要求 main clean。

## 7. G0 决策规则

- 五项 G0 Pass Condition、四项 Stop Condition、全部 Stage 0 任务证据和本 Review 验证都通过，且不存在未关闭的 `before_g0_pass` Follow-up，才可判 `G0 PASS`。
- 自动门禁全部通过但 Owner Recovery Action 未完成时，结论只能是 `REVIEW_COMPLETE / G0_BLOCKED_OWNER_ACTION`。
- 任一证据缺失、扫描不完整、策略未知、路径越界、受限上游进入 Runtime 或 Stop Condition 激活，立即 FAIL CLOSED。

## 8. 回滚与停止条件

- 回滚仅撤销本 review 分支的 Stage 0 修复和证据；不改主工作树、不删除私有 Runtime、不改历史 Phase 证据。
- 若 origin 同步出现无法保守解决的 x2n 语义冲突、外部主树与 x2n 路径重叠、真实凭据/私人内容/CDN 命中、或修复必须进入 Stage 1，立即停止。
- 本 Run 结束条件：Review 证据可复核、所有可本地修复项关闭、G0 给出真实决策；G0 被 Owner Action 阻断不等于 Review 未完成。
