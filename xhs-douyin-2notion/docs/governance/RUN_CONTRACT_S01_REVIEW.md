# Run Contract — Stage 1 Review / Fix / Re-acceptance

## 1. 身份与目标

- Run ID：`RUN-X2N-S01-REVIEW`
- Review ID：`STG.X2N.1.REVIEW`
- Review base：`5f770b6daf63d57ec4698dc7fbc95a9dfeab2669`
- `origin/main` cutoff：`3e7094774158ead8751a7189041d8d1eeff2b50c`
- 唯一目标：独立复核 `TSK.x2n.foundation.001–005`，修复 Stage 1 范围内 finding，完整重验并对 `G1` 作 Fail-Closed 决定。

本 Run 是 Stage Review，不执行新的 DAG Task；不进入 Stage 2，也不实现任何平台 Adapter。

## 2. 最小范围

- 复核五个 Foundation Task 的 Task Contract、不可变历史证据与固定提交。
- 复核 Contract round-trip、SQLite migration/rollback、Extension/Native Host restart safety、synthetic CI 与扫描。
- 对 Stage 1 每个提交版本及当前树执行 Secret/Private/CDN/禁止制品扫描。
- 只修改 Review 治理/证据、状态事实，以及 Review 发现所必需的 Stage 1 CI 证据实现。

## 3. 明确非目标

- 不实现 `TSK.x2n.skeleton.001` 或任何 Stage 2+ Task。
- 不访问 Owner Chrome、真实账号、六平台、Notion、模型、媒体或私有 Runtime。
- 不读取、显示、使用、修改、删除或轮换任何共享认证材料。
- 不合并、rebase 或复制 `origin/main` 的无关长期开发；cutoff 后只判断 x2n 路径重叠。
- 不把本地 G1 解释为远端 GitHub Actions 已运行或公开产品 Release 已完成。

## 4. Review findings

1. `F-X2N-S01-R01`：Task DAG 顶层状态停在 Foundation004，Foundation005 仍为 `planned`。
2. `F-X2N-S01-R02`：full lane 只有阻断执行总数，没有逐项 execution identity。
3. `F-X2N-S01-R03`：当前树和制品扫描已存在，但缺少 Stage 1 提交逐版本历史扫描。
4. `F-X2N-S01-R04`：`task_state.json` 存在重复 Acceptance 键，普通 JSON 解析会静默覆盖前值。
5. `F-X2N-S01-R05`：当前 Runtime CLI 硬编码输出历史 `G1_NOT_RUN`，会让 Review 后诊断状态失真。
6. `F-X2N-S01-R06`：零接触源码扫描把依赖与 Build 生成树纳入源码扫描，导致干净重建环境出现环境依赖型误报。
7. `F-X2N-S01-R07`：Review verifier 声称未新增 DAG Task，但没有与 Foundation005 固定 Task Pack 做完整结构差分。
8. `F-X2N-S01-R08`：PR 合成 merge commit 的 scope/history 校验错误包含 `main` 父分支的并行项目改动。

八个 finding 必须全部修复并由负向测试覆盖；任何 open blocker 均禁止 `G1 PASS`。

## 5. 验证命令

```bash
npm ci --ignore-scripts
uv sync --frozen --all-packages --group ci
PLAYWRIGHT_BROWSERS_PATH=build/playwright-browsers npx --no-install playwright install chromium
.venv/bin/python -B scripts/ci/run_lane.py --lane full --repetitions 2 --reports-dir build/g1-review
.venv/bin/python -B scripts/verify_stage_1_review.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/g1-review/software-lane.json --write-evidence
.venv/bin/python -B scripts/verify_stage_1_review.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/g1-review/software-lane.json --require-evidence
.venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'
```

## 6. G1 决策与交付门

- 四项 G1 Pass Condition、五个 Task、八个 Review finding、历史扫描和完整 lane 全部通过，才能签发 `G1 PASS`。
- G1 PASS 只授权 Stage 1 整体上传和 Stage 2 的下一个独立单 Task Run。
- 上传前不得使用远端状态补写本地证据；上传后 PR 的最后提交必须由远端 x2n CI 通过，才允许 merge。
- `remote_ci_execution` 在上传前保持 `pending_post_g1_upload`；不得伪造为 PASS。

## 7. 风险、回滚与停止条件

- 风险：远端主线漂移、历史中存在已删除敏感值、报告聚合掩盖漏跑、远端 runner 与本机差异。
- 回滚：revert 本 Review commit；Foundation001–005 的五个提交与历史证据保持不变。
- 任一 x2n overlap、Secret/Private/CDN、未登记阻断 skip、Migration 无回滚、任意 Origin/Command、Stage 2 越界或证据不完整，立即 Fail Closed。
