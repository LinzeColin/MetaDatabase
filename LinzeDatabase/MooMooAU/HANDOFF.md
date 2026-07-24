# MooMooAU 当前交接

更新时间：2026-07-24（Australia/Sydney）

## 当前目标与状态

- 本轮只处理 Stage 7/T0703，不进入 T0704。
- T0702/S7AC-002 protected Raw-only Beta 已通过：Alpha PASS、Raw remote recovery 100%、
  Gmail mutation 0、identity cleanup PASS、GitHub rerun 0。
- 当前控制包为 `MMAU-ARCHIVE-TP-2026-07-24-V1.0.14`；不可变直接前序是
  `taskpack/PACKAGE_MANIFEST.v1.0.13.json`，SHA-256
  `63a9d3f90fd420c8b661e7617793df0c748eece68c9363a11115d4b0d264fa1e`。
- 唯一状态权威：`machine/status/latest.json` =
  `PROTECTED_M3_ATTEMPT_FAILED_REPAIR_AUTHORIZED`。Protected Oracles 3/43 executed，
  2 PASS、1 FAILED；final Acceptance 0/34；production workflow 0；final publication 0。
- Owner 已确认 MooMooAU GitHub App 安装、private 数据仓已连接。`moomooau-beta` 已验证为
  main-only、无 reviewer、wait timer 0、exact 八项 Environment Secret name。

## 已冻结的受保护 T0703 尝试

- 六个不同 exact-main SHA 均为 workflow attempt 1：run `30060804854`、`30063841144`、
  `30066295809`、`30068892160`、`30072484529`、`30077550182`。
- 六次 exact-main CI 均 10/10 PASS；authority gate 与 identity plaintext cleanup 均 PASS；
  M3 job 均 FAILED；GitHub rerun 均为 0。所有失败 head 均禁止 rerun 或 redispatch。
- 第五次公开关闭于 `AGGREGATE_GATE / MUTATION_FAILED`。后验聚合核验观察到 private head
  改变、一个可恢复 Processed lineage、processed-current 从 ZERO 到 ONE，以及 Gmail Trash
  aggregate 增加 1；这些聚合不证明 exact-source attribution，也不证明更细 mutation subreason。
- 第六次以 `PROCESSED_PLAN / PROTECTED_M3_PROCESSED_PLAN_FAILED` 关闭。独立核验确认 private
  head/tree/path counts、Raw、Processed、processed-current、Timeline 与 Gmail Trash aggregate
  均完全不变，新增 effect 为 0。
- 精确事实账本：`machine/stages/S7/reviews/t0703/attempt-ledger.json`。

## 当前修复

- reconciliation 只在全邮箱 metadata 扫描得到唯一 verified、已在 Trash、且 opaque source ID
  存在预先加密 processed-current pointer 的候选时继续；零或多个匹配均 fail closed。
- `RemoteFirstImportTimestampSource` 在恢复 first-import timestamp 的同时，解密既有 current
  pointer、manifest 与 document envelope，恢复并校验导入时的 canonical Gmail label state。
- Processed snapshot 规划使用已加密的历史 label state，而不是 Trash 后 Raw fetch 的现态；
  从而与第五次已经远端恢复的 immutable Processed lineage 精确一致。
- Stage 7 synthetic Gmail transport 已模拟真实 Trash 语义：移除 `INBOX` 并加入 `TRASH`；
  POST/minimal/metadata/raw 响应保持一致。
- reconciliation 仍只执行 Raw fetch、Raw/Processed remote recovery 与第二次身份验证；
  不包含 Gmail mutation transport 或 private repository write path。
- Run Contract 只授权一个新 exact candidate main delivery 和一次新候选 attempt-1 zero-write
  dispatch；T0704、Timeline、Blue-Green、GA、schedule、final Acceptance/publication 均未授权。

## 已验证

- T0703 core：21 passed。
- T0703 + T0708 + RMD-04 targeted：59 passed。
- tasks/remediation 全集：340 passed。
- scoped Ruff：PASS；完整 `mypy src`：62 source files PASS。
- Acceptance 34 records 已按第六次失败与第五次可恢复 lineage 确定性重建；
  final PASS 0/34，external effects 0。
- Delivery status、Governance facts、共享文档渲染、Stage 7 preflight 与 package
  deterministic rebuild/validation 均已通过；最终 HANDOFF 变更后需再执行一次 manifest check。

## Git 与下一步

- worktree：当前隔离开发 worktree（主工作树保持只读）
- branch：`codex/moomooau-t0703-historical-label-reconcile`
- exact base：`9ca3b47eaaa75ef2f6e6650b41960d11545ed04e`
- MooMooAU Acceptance remediation lineage 仍精确绑定第五次 attempt 的 `c860f388…`。
- 下一步：完成最终确定性校验，commit/push 并建立受控 PR；全绿后合入 main、核验新
  exact-main CI 与 Environment，只 dispatch 新 main SHA attempt 1 一次。成功后独立证明 Gmail
  Trash aggregate 与 private head/tree 均无新增，并只固化 T0703 receipt，不进入 T0704；
  失败则冻结该 head 且禁止 rerun。
