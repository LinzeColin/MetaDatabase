# MooMooAU Task Pack v1.0.12 — T0703 SAFE_DEFERRED 聚合恢复候选

本包直接继承不可变 `v1.0.11`，不改变 `v1.0.1` 的 34 RQ、34 AC、58 Task、DAG、Kill
Criteria 或零误伤边界。T0702/S7AC-002 的 protected PASS 回执保持不变。

T0703 已真实执行四个不同 exact-main SHA 的 attempt 1。四次 authority gate 与 identity cleanup
均通过，M3 job 均失败，且均未使用 GitHub rerun。后验只读核验观察到 private 仓新增 commit 0、
Processed write 0、Gmail Trash 新增消息 0、source/Timeline/schedule mutation 0。四个失败
head 均禁止 rerun 或 redispatch。

第四次失败只公开 `AGGREGATE_GATE`。该 aggregate-only 输出没有包含本版本新增的 aggregate failure
class，因此不声称精确线上根因。静态契约验证证明：当 protected classification/parser registry
为空且附件 extraction 被安全隔离时，旧顺序会先产生 `BLOCKED`，与本任务要求的显式
`SAFE_DEFERRED` Processed 冲突。

本 Run Contract 只授权一个新恢复候选：

1. 无 parser profile 时优先产生显式 `SAFE_DEFERRED`，即使 extraction 为 quarantined；
2. active parser profile 仍按原契约对 quarantined extraction hard fail；
3. aggregate failure 只输出封闭固定枚举，不接收异常、ID、邮箱字段、Secret 或 private locator；
4. 既有 metadata quarantine 与 App-token optional echo/probe/TTL 修复保持不变；
5. 受控交付一个全新 exact candidate 到 `main`，随后只 dispatch 该 SHA 的 attempt 1 一次；
6. 最多一个确定性验证候选；Raw 与 Processed 均须 age 加密并从唯一 private remote 恢复；
7. 远端恢复后再次验证同一来源，只允许一次精确 `users.messages.trash`；
8. 任一恢复、二次验证、mutation 确认或安全边界失败均整次 fail closed；
9. Timeline、T0704、Blue-Green、GA、schedule、最终验收和最终发布均不在本 Run Contract。

包构建时 T0703 protected Oracle 仍为 `FAILED`，新候选尚未运行。只有该新 exact candidate 的
aggregate-only protected receipt 可把 T0703/S7AC-003 提升为 PASS。
