# MooMooAU 当前交接

更新时间：2026-07-24（Australia/Sydney）

## 当前目标与状态

- 本轮只处理 Stage 7/T0703，不进入 T0704。
- T0702/S7AC-002 protected Raw-only Beta 已通过：Alpha PASS、Raw remote recovery 100%、
  Gmail mutation 0、identity cleanup PASS、GitHub rerun 0。
- 当前控制包为 `MMAU-ARCHIVE-TP-2026-07-24-V1.0.12`；不可变直接前序是
  `taskpack/PACKAGE_MANIFEST.v1.0.11.json`，SHA-256
  `897cda5d6c6d77edd552abe9b2200a179b0b4aa0d11fa4733f45accd8c24aa34`。
- 唯一状态权威：`machine/status/latest.json` =
  `PROTECTED_M3_ATTEMPT_FAILED_REPAIR_AUTHORIZED`。Protected Oracles 3/43 executed，
  2 PASS、1 FAILED；final Acceptance 0/34；production workflow 0；final publication 0。
- Owner 已确认 MooMooAU GitHub App 安装并链接 private 数据仓。`moomooau-beta` 已验证为
  main-only、无 reviewer、wait timer 0、exact 八项 Environment Secret name。

## 已发生的受保护 T0703 尝试

- 四个不同 exact-main SHA 均为 workflow attempt 1：PR #101/run `30060804854`、PR #102/run
  `30063841144`、PR #103/run `30066295809`、PR #104/run `30068892160`。
- 四次 exact-main CI 均 10/10 PASS；authority gate 与 identity plaintext cleanup 均 PASS；
  M3 Budget-1 job 均 FAILED；GitHub rerun 均为 0。
- 第四次只公开 `AGGREGATE_GATE`；不声称 aggregate-only 输出未证明的精确线上根因。
- 每次后验只读核验均观察到 private repo new commits 0、Processed writes 0、Gmail Trash
  messages after dispatch 0、source/Timeline/schedule mutations 0。
- 四个失败 head 均不得 GitHub rerun 或 redispatch。精确账本：
  `machine/stages/S7/reviews/t0703/attempt-ledger.json`。

## 当前修复

- 静态契约验证证明：空 protected classification/parser registry 与安全隔离 attachment 组合下，
  旧 `StatementParser` 顺序会先产出 `BLOCKED`，与 protected Oracle 要求的显式
  `SAFE_DEFERRED` Processed 冲突。
- 无 parser profile 的 SAFE_DEFERRED 决策现位于 quarantined extraction 阻断之前；active parser
  profile 仍维持 hard quarantine。
- 新端到端 task oracle 验证 Raw=1、recoverable SAFE_DEFERRED Processed=1、exact Trash=1、
  processing_blocked=0 与 plaintext cleanup。
- `ProtectedM3AggregateFailureClass` 只保留固定枚举；公开失败 payload 不接收异常对象、动态值、
  邮箱字段、Secret、App、installation 或 private repo locator。
- M3 same-tree gate 与 GitHub Workflow 的 Ruff/mypy 范围均绑定 `document_parser.py`。
- 既有 metadata quarantine、App-token optional echo、bounded repository probe、GitHub Date TTL
  与所有 broader fail-closed 边界保持不变。
- Repair Run Contract 只授权一个新 exact candidate main delivery 和一次新候选 attempt-1
  Budget-1 dispatch；T0704、Timeline、Blue-Green、GA、schedule、final Acceptance/publication
  均为未授权。

## 已验证

- T0702 + T0703 protected-entrypoint task oracle：75 passed；Stage 7 CI 全量测试：343 passed。
- Attempt ledger JSON Schema：PASS。
- Acceptance 34 records 已按第四次失败 lineage 确定性重建；final PASS 0/34，external effects 0。
- Delivery status deterministic rebuild/schema：PASS。
- Governance facts deterministic rebuild/check：PASS。
- Stage 0–7 cumulative preflight：9/9 PASS；package manifest：627 files PASS。
- Ruff format/lint 与 scoped strict mypy：PASS。
- publication、SBOM、Secret scan、dependency audit 与云端 PR/main CI 尚待本候选最终执行。

## Git 与下一步

- worktree：当前隔离开发 worktree（主工作树保持只读）
- branch：`codex/moomooau-t0703-safe-deferred-aggregate`
- base：`b922219fa80fd0f55e8dd0d100a87ced2a77b2b8`
- 当前修复候选尚未 commit/push/PR/merge/dispatch。
- 下一步：完成 v1.0.12 package 与全量门禁；受控 PR 合入 main；核验 exact-main CI 与
  Environment；只 dispatch 新 main SHA attempt 1 一次。成功后只固化 T0703 receipt，不进入
  T0704；失败则禁止 rerun，并仅按新封闭 aggregate class 继续 T0703。
