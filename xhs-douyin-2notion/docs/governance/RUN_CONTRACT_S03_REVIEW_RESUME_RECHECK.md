# Stage 3 G3 Resume Recheck Run Contract

## Identity

- Review: `STG.X2N.3.REVIEW.RESUME.RECHECK`
- Run: `RUN-X2N-S03-REVIEW-RESUME-RECHECK`
- Base: `TSK.x2n.adapters.010@c528ff14836f116f624fa8b1ea63472a7f4b678f`
- Gate: `G3`

## Single-phase scope

本 Run 只独立复验 G3；它不是新的 DAG Task，不实现 `PH.X2N.4.1`，不上传 Stage 3，
不部署、不发布、不使用真实账号、Chrome Profile、平台、Notion、模型或媒体。验证只能在隔离
`HOME`、临时 SQLite 与公开合成 Fixture 中执行。

## Required decision

仅当下列六项均由本 Run 新鲜复跑的 CI-synth 证据满足时，签发 `G3=PASS_CI_SYNTH`：

1. 八个严格 scope 经 Extension → Native → Adapter；
2. 完整 snapshot 恰有八行 `capability_gate_outcome`，技术 veto 不得结算为终态；
3. checkpoint/resume 及 Companion/Service Worker restart reconciliation 通过；
4. 空响应不删除内容；
5. Adapter 失败持久化 failed `run_record` 与一条脱敏 `run_failure`，Side Panel 不新增 run state 即得 fallback；
6. 当前页 fallback 必须由第二次 Owner action 触发，自动 fallback 为零。

任一未知、失败、输出缺失、平台调用非零或证据含敏感值时一律 `FAIL_CLOSED`。

## Transition and release boundary

G3 PASS 只允许本地开始下一单 `TSK.x2n.multimodal.001 / PH.X2N.4.1`，不授权远端上传、部署或发布。
最终 `assurance.005` 仍在同一正式 MVP 任务内完成 deploy/run/online smoke；不引入 Alpha、Beta、固定
30 日观察或 soak。上线后监控是非阻断的修复、降级或回滚触发器。
