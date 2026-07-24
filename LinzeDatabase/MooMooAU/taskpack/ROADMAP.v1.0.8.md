# MooMooAU Roadmap v1.0.8

## 当前节点

- Stage：S7
- 当前 Task：T0703 — M3 Mutation Budget 1 Canary
- 前序：T0702/S7AC-002 protected PASS
- 状态：唯一受保护 first attempt 已授权，尚未执行
- 固定日历等待：0 天
- 最终发布：未授权

## 本次确定性路径

1. 验证 `v1.0.7` manifest、T0702 PASS receipt、当前 T0703 Run Contract 和 exact main。
2. 对候选运行全部本地与 PR CI gate。
3. 受控 merge 后，现有 `moomooau-beta` Environment 必须为 main-only、无 reviewer、八项
   exact Secret name。
4. dispatch `moomooau-m3.yml` 的 exact main SHA，attempt 必须为 1，禁止 rerun。
5. 最多一个已验证候选依次执行：
   metadata verification → Raw fetch → age Raw commit/recovery → encrypted Processed
   COMPLETE 或 SAFE_DEFERRED commit/recovery → second verification → exact message Trash。
6. 只从 aggregate-only protected receipt 更新 T0703 evidence。
7. 不进入 T0704；下一 Run Contract 只能在 T0703 PASS 后按 DAG 单独建立。

## PASS 条件

- protected runs = 1；
- verified/full-Raw candidate ≤ 1；
- recovered Raw + Processed = 100%；
- Processed COMPLETE 或显式 SAFE_DEFERRED = 1；
- `users.messages.trash` confirmed = 1；
- collateral mutation = 0；
- Timeline/schedule/Blue-Green/GA = 0；
- public sensitive finding = 0；
- age identity plaintext cleanup = PASS。

任何条件不满足均 fail closed，保留 Gmail 原件和已恢复密文，不得 GitHub rerun。
