# Run Contract — RUN-X2N-S00-REVIEW-RESUME

## 目标

执行唯一 `STG.X2N.0.REVIEW.RESUME`，验证 Owner 对外部共享认证材料的保留决定与 x2n 零接触补偿控制，重新运行 Stage 0 的私有根、仓库、历史证据、原始输入、Phase 0.1/0.2/0.5 与 G0 门禁。

## 最小范围

- 不执行新 DAG Task；不进入 `TSK.x2n.foundation.001`。
- 只修改 `xhs-douyin-2notion/**` 的治理状态、审计器、测试、报告和脱敏证据，以及私有根中的一份闭合 `0600` Owner 回执。
- 不读取、请求、显示、使用、删除、轮换、撤销或修改共享认证材料；不读取或修改全局 Git 配置与 Credential Helper。
- 不吸收 cutoff 后与 x2n 零重叠的 `origin/main` 变化，不读取其他长期开发线的内容。

## 验收

1. Owner 回执只包含闭合枚举和布尔边界，Secret、账号、URL、自由文本为 0。
2. 当前树、项目历史、私有根与 x2n 本地 Remote 的认证材料形态命中均为 0。
3. 历史 20 份 Phase 证据与原 Review 的 Blocked 证据保持原样。
4. 原始 roadmap/ZIP 固定哈希、Phase 0.1/0.2/0.5 完整复验和全量单测通过。
5. G0 五项 Pass Condition 全部 PASS，四项 Stop Condition 全部 INACTIVE。
6. 公开 Resume 证据不包含私有回执元数据、本机绝对路径、Secret 或 CDN URL。

## 风险、回滚与停止条件

- 任一命中非 0、未知、证据缺失、状态不一致、外部 overlap 或测试失败：保持/恢复 `G0_BLOCKED`，不得上传。
- 状态切换失败时只回滚本 Run 未提交的 Gate、Task、Project、Taskpack、报告与 Resume 证据；不得触碰共享认证材料或历史证据。
- 通过后只授权上传整个 Stage 0，并把下一独立 Run 路由到 `TSK.x2n.foundation.001`；本 Run 不执行 Stage 1。

## 验证命令

```bash
python3 -B scripts/verify_stage_0_review_resume.py --expect-g0 pass --verify-worktree --allow-external-main-dirty --source-roadmap "$X2N_SOURCE_ROADMAP" --source-taskpack "$X2N_SOURCE_TASKPACK" --require-evidence
python3 -B scripts/verify_stage_0_review.py --verify-worktree --allow-external-main-dirty --verify-local-root --source-roadmap "$X2N_SOURCE_ROADMAP" --source-taskpack "$X2N_SOURCE_TASKPACK" --require-evidence
python3 -B -m unittest discover -s tests -p 'test_*.py'
```
