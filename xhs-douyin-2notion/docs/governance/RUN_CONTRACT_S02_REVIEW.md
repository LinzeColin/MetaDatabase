# Run Contract — Stage 2 Review / Fix / Re-acceptance

## 1. 身份与目标

- Run ID：`RUN-X2N-S02-REVIEW`
- Review ID：`STG.X2N.2.REVIEW`
- Review base：`c133e1d4c1cbc17a3165e19fa5dbb2368da6b32b`
- Stage base：`6777c8fcce75a36741b70c2858c8bc5fff17d440`
- `origin/main` cutoff：`6777c8fcce75a36741b70c2858c8bc5fff17d440`
- Review branch：`codex/xhs-douyin-2notion-v0001-s02-review`
- 唯一目标：独立复核 `TSK.x2n.skeleton.001–009`，修复 Stage 2 范围内 finding，完整重验并对 `G2` 作 Fail-Closed 决定。

本 Run 是 Stage Review，不执行新的 DAG Task；不进入 Stage 3，也不实现真实平台 Adapter、列表遍历、下载或自动分类。

## 2. 最小范围

- 复核九个 Skeleton Task 的 Task Contract、Acceptance、固定提交与不可变历史 evidence。
- 复核六平台 current-page 合成路径、canonical 幂等、媒体临时租约清理、Markdown 与进程内 Notion Mock 降级独立性。
- 对 Stage 2 每个提交版本及当前源码执行 Secret/Private/CDN/禁止制品扫描。
- 只修改 Review 治理、验证器、负向测试、机器事实、证据和发现所必需的现有 CI 证据实现；不修改平台产品能力。

## 3. 明确非目标与隔离边界

- 不执行 `TSK.x2n.adapters.001` 或任何 Stage 3+ Task。
- 不访问 Owner Chrome、真实账号、平台、真实 Notion、模型、媒体网络或私有 Runtime。
- 不读取、显示、使用、修改、删除或轮换任何共享认证材料。
- 不访问或修改其他仓库/项目；不合并、rebase 或复制 `origin/main` 的并行开发。
- 不把本地 `G2 PASS` 解释为远端 GitHub Actions、正式 Verifier release-candidate、公开产品 Release 或真实平台验收已通过。

## 4. Review findings

1. `F-X2N-S02-R01`：Skeleton005 verifier 绑定历史任务分支且读取当前文件，无法在后代 Review 分支冻结重放。
2. `F-X2N-S02-R02`：当前文档仍记录 75 个 Companion tests / 76.86% coverage，与最终 76 / 76.93% 不一致。
3. `F-X2N-S02-R03`：软件 lane 把动态阶段状态硬编码为 `g1=NOT_RUN`，在 G1 已通过后生成失真报告。
4. `F-X2N-S02-R04`：软件 lane 未验证或记录实际工具链；Python 3.13 可在要求 Python 3.12 的政策下产生 PASS 报告。
5. `F-X2N-S02-R05`：缺少将五项 G2 Pass Condition 聚合为精确、可拒绝缺项/重复/改名的机器 Oracle。
6. `F-X2N-S02-R06`：缺少对九份 Skeleton evidence 与各自固定提交逐字节一致性的 Review 门禁。
7. `F-X2N-S02-R07`：缺少 Stage 2 提交逐版本的 commit message、变更 blob、当前源码与 workflow 隐私扫描。
8. `F-X2N-S02-R08`：缺少 Stage 2 Review 的精确 Task Pack 状态差分、PR synthetic merge 逻辑父提交、后续阶段 PR 对历史 Review evidence 的固定提交重放和 G2 事实负向门禁。

八个 finding 必须全部修复并由负向测试覆盖；任一 open blocker 均禁止 `G2 PASS`。

## 5. 验证命令

```bash
npm ci --ignore-scripts
uv sync --python 3.12 --frozen --all-packages --group ci
PLAYWRIGHT_BROWSERS_PATH=build/playwright-browsers npx --no-install playwright install chromium
.venv/bin/python -B scripts/ci/run_lane.py --lane full --repetitions 2 --reports-dir build/g2-review-a
.venv/bin/python -B scripts/ci/run_lane.py --lane full --repetitions 2 --reports-dir build/g2-review-b
.venv/bin/python -B scripts/verify_stage_2_review.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/g2-review-b/software-lane.json --run-g2-acceptance --write-evidence
.venv/bin/python -B scripts/verify_stage_2_review.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/g2-review-b/software-lane.json --require-evidence
.venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'
```

## 6. G2 决策与交付门

- 六平台独立 current-page 路径、零重复、零 CDN 持久化、媒体清理、Notion outage 不阻断 canonical/Markdown，连同九个 Task、八个 finding、历史扫描、工具链身份和完整 lane 全部通过，才能签发 `G2 PASS`。
- G2 PASS 只授权 Stage 2 整体上传；远端 x2n CI 未通过且未 merge 前，不授权 Stage 3 产品 Task。
- `remote_ci_execution` 在上传前保持 `pending_post_g2_upload`；不得伪造为 PASS。
- 正式 Verifier v2.1 输入因上游任务包没有 canonical `MANIFEST` role 而保持 `BLOCKED_REQUIREMENT_GAP`；项目原生 G2 不得冒充正式 release-candidate verdict。

## 7. 风险、回滚与停止条件

- 风险：远端主线漂移、历史中存在已删除敏感值、聚合报告漏跑、工具链与政策不一致、合成路径被误述为真实平台能力。
- 回滚：revert 本 Review commit；九个 Skeleton 固定提交及其历史 evidence 保持不变。
- 任一 x2n overlap、Secret/Private/CDN、历史 evidence 改写、未登记阻断 skip、工具链漂移、真实外部调用、Stage 3 越界或证据不完整，立即 Fail Closed。
