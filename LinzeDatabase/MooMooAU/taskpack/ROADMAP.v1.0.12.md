# MooMooAU Roadmap v1.0.12

## 当前节点

- Stage：S7
- 当前 Task：T0703 — M3 Mutation Budget 1 Canary
- 前序：T0702/S7AC-002 protected PASS
- 已执行：T0703 四个不同 exact-main SHA 的 attempt 1，均零观察副作用失败
- 当前状态：第四次只公开 `AGGREGATE_GATE`；SAFE_DEFERRED 聚合恢复候选已授权，尚未执行
- 固定日历等待：0 天
- 最终发布：未授权

## 本次确定性路径

1. 验证不可变 `v1.0.11` manifest、T0702 PASS receipt、四次 T0703 failed-attempt ledger、当前
   Run Contract 和 exact candidate。
2. 验证空 protected registry 且 attachment quarantined 时产生显式可恢复 `SAFE_DEFERRED`。
3. 验证 active parser profile 的 hard quarantine 未被放宽。
4. 验证 aggregate failure 只输出封闭固定枚举且不含动态受保护值。
5. 运行全部本地、PR 与 exact-main CI gate。
6. 受控 merge 一个全新恢复候选；禁止 GitHub rerun 或四个失败 head redispatch。
7. 验证 `moomooau-beta` 为 main-only、无 reviewer、wait timer 0、exact 八项 Secret name。
8. 只 dispatch 新 main SHA 的 `moomooau-m3.yml` attempt 1。
9. 对一个确定性验证候选依次执行：Raw fetch → age Raw commit/recovery → encrypted Processed
   COMPLETE 或 SAFE_DEFERRED commit/recovery → second verification → exact message Trash。
10. 只从 aggregate-only receipt 更新 T0703 evidence，不进入 T0704。

## PASS 条件

- 新候选 protected run = 1，四个 failed-head rerun/redispatch = 0；
- verified/full-Raw candidate ≤ 1；
- recovered Raw + Processed = 100%；
- Processed COMPLETE 或显式 SAFE_DEFERRED = 1；
- `users.messages.trash` confirmed = 1；
- collateral mutation = 0；
- Timeline/schedule/Blue-Green/GA = 0；
- public sensitive finding = 0；
- age identity plaintext cleanup = PASS。

任何条件不满足均 fail closed，保留 Gmail 原件和已恢复密文；不得重跑既有 head。
