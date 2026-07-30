# Stage 5 Task004 Run Contract — Observability, Diagnostics and Recovery

## Identity

- Task: `TSK.x2n.uxops.004`
- Phase: `PH.X2N.5.4`
- Run: `RUN-X2N-S05-U004`
- Acceptance: `ACC.x2n.ops.001`, `ACC.x2n.ops.002`, `ACC.x2n.ops.004`

## Scope

本 Run 为 Local Companion 建立唯一的运行诊断和恢复面：SQLite Canonical Store 仍是唯一真相源，
metrics 只能从其当前快照派生，不能另行持久化或成为第二真相源。`operations-v1.json` 只允许
opaque `run_id`、稳定 ErrorCode、固定 stage/component、状态、时间和 attempt；没有正文、URL、
Cookie、凭据、Query、Profile 路径、本地用户名、模型输出或任意 free-form message 的位置。

`x2n operations diagnostics|doctor|recovery-plan` 是只读；`x2n operations startup-recovery` 必须提供
精确确认字面量，且一次运行只做有界的 SQLite lease recovery、当前页 finalize、确定性 Markdown rebuild。
默认没有 Notion Worker，因此不会自行创建真实 Notion transport；只有已有、显式注入的 Worker 才能执行
reconcile，CI 仅使用进程内 `NotionMockServer`。任何 Canonical identity 行减少、SQLite 健康失败、遗留
current-page running Job 或诊断 allowlist 违规都 Fail Closed。

Task003 的 Local WebUI diagnostics export 改为消费同一脱敏 bundle；它仍只绑定 `127.0.0.1`，不新增
写接口、CORS、LAN listener、外部脚本或网络调用。Task003 receipt 和固定提交
`7f78c3074880d887a683fa9cb2ed8b0477dc414c` 通过 disposable alternate-object-store replay 验证；当前
Task004 tree 不会被该 replay 审计。

直接 MVP 策略保持有效：没有 Alpha、Beta、固定 30 日观察或 soak。它们也不会在本 Task 中提前执行；
真实账号/平台/Profile/媒体/模型/Notion、耐久 Private-MetaDatabase 生命周期、Task005、G5、Stage6
部署、运行、online smoke 均不属于本 Run。

## Acceptance and stop conditions

- Source、Media、ASR、OCR、Vision、Fusion、Classification、DB Commit、Markdown、Notion 十个
  kill stage 均有稳定、内容无关的终态记录；已持久的 Canonical identity 不丢失，恢复没有重复 sink 副作用；
- diagnostics 的 schema 和 pattern canary 对正文、Token、Cookie、query、本地用户名、Profile 路径、模型
  内容均命中 `0`；每个已知失败含稳定 ErrorCode 和 opaque `run_id`；
- Doctor 的八个组件必须分别返回 `ok`、`degraded` 或 `blocked`，提供最小操作建议，不显示 Secret，且缺少
  FFmpeg/Provider/Notion 不得将 Canonical 核心误报为整体不可用；
- Markdown 从单一 Canonical snapshot 可重建且第二次无重复写；Notion Mock reconcile 在重复恢复后 Page=1；
- 若任何诊断必须保存原文，恢复导致 identity 行减少、重复 Page 或未终结 Job，立即停止；回滚为停用
  `operations` export/recovery 命令并恢复已知良好版本，Canonical 数据保持不删除。

## Validation

```bash
.venv/bin/python -B scripts/replay_uxops_003_historical.py
.venv/bin/python -B scripts/run_uxops_004_acceptance.py
.venv/bin/python -B scripts/verify_uxops_004.py --verify-worktree --allow-external-main-dirty --run-acceptance --require-evidence
PYTHONPATH=apps/companion/src:packages/contracts/src .venv/bin/python -B -m unittest apps.companion.tests.test_operations
```

完成只授权下一单本地 `TSK.x2n.uxops.005`；不会自动进入 Stage 5 Review 或 Stage6。
