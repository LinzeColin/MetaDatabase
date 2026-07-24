# MooMooAU Roadmap v1.0.9

## 当前节点

- Stage：S7
- 当前 Task：T0703 — M3 Mutation Budget 1 Canary
- 前序：T0702/S7AC-002 protected PASS
- 已执行：T0703 attempt 1，零观察副作用失败
- 当前状态：metadata remediation 新候选已授权，尚未交付/执行
- 固定日历等待：0 天
- 最终发布：未授权

## 本次确定性路径

1. 验证不可变 `v1.0.8` manifest、T0702 PASS receipt、T0703 failed-attempt ledger、repair Run
   Contract 和 exact candidate。
2. 运行全部本地、PR 与 exact-main CI gate。
3. 受控 merge 一个新修复候选；禁止 GitHub rerun 或失败 head redispatch。
4. 验证既有 `moomooau-beta` 为 main-only、无 reviewer、exact 八项 Secret name，GitHub App
   仍关联唯一 private 数据仓。
5. 只 dispatch 新 main SHA 的 `moomooau-m3.yml` attempt 1。
6. 逐消息 metadata 不可验证只 quarantine；下一确定性验证候选依次执行：
   Raw fetch → age Raw commit/recovery → encrypted Processed COMPLETE 或 SAFE_DEFERRED
   commit/recovery → second verification → exact message Trash。
7. 只从 aggregate-only receipt 更新 T0703 evidence，不进入 T0704。

## PASS 条件

- 新候选 protected run = 1，failed-head rerun/redispatch = 0；
- verified/full-Raw candidate ≤ 1；
- recovered Raw + Processed = 100%；
- Processed COMPLETE 或显式 SAFE_DEFERRED = 1；
- `users.messages.trash` confirmed = 1；
- collateral mutation = 0；
- Timeline/schedule/Blue-Green/GA = 0；
- public sensitive finding = 0；
- age identity plaintext cleanup = PASS。

任何条件不满足均 fail closed，保留 Gmail 原件和已恢复密文；后续只能建立新的精确候选合同，不能
重跑既有 head。
