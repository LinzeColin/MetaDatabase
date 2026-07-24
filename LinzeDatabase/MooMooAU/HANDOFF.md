# MooMooAU 当前交接

更新时间：2026-07-24（Australia/Sydney）

## 当前目标与状态

- 本轮只处理 Stage 7/T0703，不进入 T0704。
- T0702/S7AC-002 protected Raw-only Beta 已通过：Alpha PASS、Raw remote recovery 100%、
  Gmail mutation 0、identity cleanup PASS、GitHub rerun 0。
- 当前控制包为 `MMAU-ARCHIVE-TP-2026-07-24-V1.0.13`；不可变直接前序是
  `taskpack/PACKAGE_MANIFEST.v1.0.12.json`，SHA-256
  `7231b1453f64899b8b481c024c3ae437c4412a82a652c9457bccd08e5f8fc48d`。
- 唯一状态权威：`machine/status/latest.json` =
  `PROTECTED_M3_ATTEMPT_FAILED_REPAIR_AUTHORIZED`。Protected Oracles 3/43 executed，
  2 PASS、1 FAILED；final Acceptance 0/34；production workflow 0；final publication 0。
- Owner 已确认 MooMooAU GitHub App 安装并链接 private 数据仓。`moomooau-beta` 已验证为
  main-only、无 reviewer、wait timer 0、exact 八项 Environment Secret name。

## 已发生的受保护 T0703 尝试

- 五个不同 exact-main SHA 均为 workflow attempt 1：PR #101/run `30060804854`、PR #102/run
  `30063841144`、PR #103/run `30066295809`、PR #104/run `30068892160`、PR #106/run
  `30072484529`。
- 五次 exact-main CI 均 10/10 PASS；authority gate 与 identity plaintext cleanup 均 PASS；
  M3 job 均 FAILED；GitHub rerun 均为 0。
- 前四次后验只读核验均观察到 private repo new commits 0、Processed writes 0、Gmail Trash
  messages after dispatch 0、source/Timeline/schedule mutations 0。
- 第五次公开关闭于 `AGGREGATE_GATE / MUTATION_FAILED`。后验聚合核验观察到 private head
  改变、一个可恢复 Processed lineage、processed-current 从 ZERO 到 ONE，以及 Gmail Trash
  aggregate 增加 1；这些聚合不证明 exact-source attribution，也不证明更细 mutation subreason。
- 五个失败 head 均不得 GitHub rerun 或 redispatch。精确账本：
  `machine/stages/S7/reviews/t0703/attempt-ledger.json`。

## 当前修复

- 零新增写入 reconciliation 只在全邮箱 metadata 扫描得到唯一 verified、已在 Trash、且 opaque
  source ID 存在预先加密 processed-current pointer 的候选时继续；零或多个匹配均 fail closed。
- 对该唯一候选执行一次 full Raw fetch、Canonical Raw/Processed 规划、Raw 与 Processed remote
  recovery 和第二次身份验证，但完全跳过 Raw/Processed commit saga。
- reconciliation 只接受已在 Trash 的二次 metadata 证明，调用不含 Gmail transport，因此本次
  Gmail mutation budget、Raw creation budget 与 Processed write budget均为 0。
- 既有 metadata quarantine、App-token optional echo、bounded repository probe、GitHub Date TTL、
  封闭失败分类与所有 broader fail-closed 边界保持不变。
- Run Contract 只授权一个新 exact candidate main delivery 和一次新候选 attempt-1 zero-write
  dispatch；T0704、Timeline、Blue-Green、GA、schedule、final Acceptance/publication 均未授权。

## 已验证

- reconciliation 单元与端到端 task oracle：26 passed；scoped Ruff 与 strict mypy：PASS。
- clean/shallow checkout 已独立复现并修复：Acceptance remediation base 仅在
  `SOURCE_PROVENANCE.v1.0.13.json` 的 exact 双 pin 与 `EXACT_PIN_ONLY` 约束完全匹配时允许
  portable fallback；完整 Git 仓库仍强制 ordinary ancestor gate。
- 当前 task/remediation 全集 340 passed；Acceptance portable-pin 定向测试、Delivery status
  deterministic rebuild/schema 与 package manifest 631-file check 均 PASS。
- Attempt ledger JSON Schema：PASS。
- Acceptance 34 records 已按第五次失败 lineage 确定性重建；final PASS 0/34，external effects 0。
- Delivery status deterministic rebuild/schema：PASS。
- Governance facts deterministic rebuild/check：PASS。
- publication、SBOM、Secret scan、dependency audit 已 PASS；新候选云端 PR/main CI 与
  protected reconciliation 尚待执行。

## Git 与下一步

- worktree：当前隔离开发 worktree（主工作树保持只读）
- branch：`codex/moomooau-t0703-unknown-mutation-reconcile`
- base：`589cebacce6aea0d6b0c34780fc4e8f23bbc4b9d`（仅新增 EEI PR #107；
  MooMooAU acceptance remediation lineage 仍绑定第五次 attempt 的 `c860f388…`）
- v1.0.13 首个候选 `e643d032…` 已 push 并建立 PR #108；其 cloud shallow checkout 暴露
  Acceptance portable pin 仍停在旧 RMD-06 常量，当前最小修复正在同一 PR 上完成。
- 下一步：以新 commit 触发 PR #108 全新 CI（不 rerun 旧 run）；全绿后受控合入 main并核验
  exact-main CI 与 Environment；只 dispatch 新 main SHA attempt 1 一次。成功后独立证明 Gmail
  Trash aggregate 与 private head/tree 均无新增，并只固化 T0703 receipt，不进入 T0704；
  失败则禁止 rerun。
