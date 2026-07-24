# MooMooAU 当前交接

更新时间：2026-07-24（Australia/Sydney）

## 当前目标与状态

- 本轮只处理 Stage 7/T0703，不进入 T0704。
- T0702/S7AC-002 protected Raw-only Beta 已通过：Alpha PASS、Raw remote recovery 100%、
  Gmail mutation 0、identity cleanup PASS、GitHub rerun 0。
- 当前控制包为 `MMAU-ARCHIVE-TP-2026-07-24-V1.0.9`；不可变直接前序是
  `taskpack/PACKAGE_MANIFEST.v1.0.8.json`，SHA-256
  `b2f0f21001b10202ca476ef8f8a23acb55aa3c479a85aa31fbc962f020b2d0c7`。
- 唯一状态权威：`machine/status/latest.json` =
  `PROTECTED_M3_ATTEMPT_FAILED_REPAIR_AUTHORIZED`。Protected Oracles 3/43 executed，
  2 PASS、1 FAILED；final Acceptance 0/34；production workflow 0；final publication 0。
- Owner 已确认 MooMooAU GitHub App 安装并链接 private 数据仓。`moomooau-beta` 已验证为
  main-only、无 reviewer、wait timer 0、exact 八项 Environment Secret name。

## 已发生的受保护 T0703 尝试

- PR #101 已合入 `main`；merge SHA `f747ddcd2e5eab589802a0c545293cd6f275ca71`，精确 main
  CI 10/10 PASS。
- 唯一 dispatch：GitHub Actions run `30060804854`，attempt 1，rerun 0。
- authority gate PASS；M3 Budget-1 job FAILED；identity plaintext cleanup PASS。
- 公开失败仅为固定 aggregate payload，未声称精确根因。
- 后验只读核验：private repo new commits 0、Raw creations 0 observed、Processed writes 0
  observed、Gmail Trash messages after dispatch 0、source/Timeline/schedule mutations 0。
- 失败 head 不得 GitHub rerun 或 redispatch。精确账本：
  `machine/stages/S7/reviews/t0703/attempt-ledger.json`。

## 当前修复

- `M3CanaryRunner` 仅捕获逐消息 `MessageMetadataUnverifiable`，计入 metadata quarantine 后继续
  下一个候选；该行为与已在 T0702 证明的安全分支一致。
- authentication、authorization、transport、content-boundary、global discovery、Raw/Processed
  recovery、second verification 与 Trash 错误仍整次 fail closed。
- 新增 `protected_m3_diagnostics.py` 固定 phase taxonomy；失败输出不接收异常对象、动态值、邮箱
  字段、Secret 或 private repo locator。
- M3 gate 绑定 T0702 PASS、failed-attempt ledger/schema、repair Run Contract、实现与 task oracle。
- Repair Run Contract 只授权一个新 exact candidate main delivery 和一次新候选 attempt-1
  Budget-1 dispatch；T0704、Timeline、Blue-Green、GA、schedule、final Acceptance/publication
  均为未授权。

## 已验证

- T0703 target：15 passed。
- 修改源码 Ruff、mypy：PASS。
- Attempt ledger JSON Schema：PASS。
- Acceptance 34 records structurally valid，final PASS 0/34，external effects 0。
- Delivery status deterministic rebuild/schema：PASS。
- 后续仍须在候选最终字节固定后重跑 full tests、Ruff、mypy、package、publication、workflow、
  Stage 7、Governance、secret scan 与 dependency audit。

## Git 与下一步

- worktree：当前隔离开发 worktree（主工作树保持只读）
- branch：`codex/moomooau-t0703-metadata-remediation`
- base：`f747ddcd2e5eab589802a0c545293cd6f275ca71`
- 当前修复候选尚未 commit/push/PR/merge/dispatch。
- 下一步：完成 v1.0.9 package 与全量门禁；受控 PR 合入 main；等待 exact-main CI 全绿；核验
  Environment/App 绑定；仅 dispatch 新 main SHA attempt 1 一次。成功后只固化 T0703 receipt，
  不进入 T0704。
