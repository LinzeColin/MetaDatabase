# MooMooAU 当前交接

更新时间：2026-07-24（Australia/Sydney）

## 当前目标与状态

- 本轮只处理 Stage 7/T0703，不进入 T0704。
- T0702/S7AC-002 protected Raw-only Beta 已通过：Alpha PASS、Raw remote recovery 100%、
  Gmail mutation 0、identity cleanup PASS、GitHub rerun 0。
- 当前控制包为 `MMAU-ARCHIVE-TP-2026-07-24-V1.0.11`；不可变直接前序是
  `taskpack/PACKAGE_MANIFEST.v1.0.10.json`，SHA-256
  `d61c805507bbd891e875ae20c1e80804564db3767997c4441a19a0e3eb6593bf`。
- 唯一状态权威：`machine/status/latest.json` =
  `PROTECTED_M3_ATTEMPT_FAILED_REPAIR_AUTHORIZED`。Protected Oracles 3/43 executed，
  2 PASS、1 FAILED；final Acceptance 0/34；production workflow 0；final publication 0。
- Owner 已确认 MooMooAU GitHub App 安装并链接 private 数据仓。`moomooau-beta` 已验证为
  main-only、无 reviewer、wait timer 0、exact 八项 Environment Secret name。

## 已发生的受保护 T0703 尝试

- PR #101/main `f747ddcd…`/run `30060804854`、PR #102/main `9b15c4d5…`/run
  `30063841144` 与 PR #103/main `bc0bfb3b…`/run `30066295809` 均为不同 exact-main attempt 1；
  main CI 均 10/10 PASS，rerun 均 0。
- 三次 authority gate 与 identity plaintext cleanup 均 PASS；三次 M3 Budget-1 job 均 FAILED。
- 第三次公开失败边界为 `GITHUB_APP_TOKEN/RESPONSE_SCOPE_REJECTED`；不声称封闭输出未证明的
  精确远端根因。
- 后验只读核验：private repo new commits 0、MooMooAU path writes 0、Processed writes 0
  observed、Gmail Trash messages after dispatch 0、source/Timeline/schedule mutations 0。
- 三个失败 head 均不得 GitHub rerun 或 redispatch。精确账本：
  `machine/stages/S7/reviews/t0703/attempt-ledger.json`。

## 当前修复

- `GitHubEndpointGuard` 对 installation-token 响应只强制官方必填的 `token` 与 `expires_at`；
  scope 回显存在时精确验证，repository 回显缺失时执行有界精确 installation repository probe。
- token 一小时 TTL 以有界 GitHub `Date` 为参考；不可信 Date、scope 漂移或 probe 失败均销毁
  token 并 fail closed。
- authentication、authorization、transport、content-boundary、global discovery、Raw/Processed
  recovery、second verification 与 Trash 错误仍整次 fail closed。
- `protected_m3_diagnostics.py` 固定 phase taxonomy，并与 T0702 对齐封闭
  `InstallationTokenFailureClass`；失败输出不接收异常对象、动态值、邮箱字段、Secret、App、
  installation 或 private repo locator。
- M3 gate 绑定 T0702 PASS、failed-attempt ledger/schema、repair Run Contract、实现与 task oracle。
- Repair Run Contract 只授权一个新 exact candidate main delivery 和一次新候选 attempt-1
  Budget-1 dispatch；T0704、Timeline、Blue-Green、GA、schedule、final Acceptance/publication
  均为未授权。

## 已验证

- optional-token-echo target：72 passed。
- Stage 7 CI 等价累计测试：341 passed；Ruff format/lint 与 strict mypy 64 source files：PASS。
- Stage 0–7 cumulative preflight：9/9 PASS；Workflow command matrix：8/8 PASS。
- Attempt ledger JSON Schema：PASS。
- Acceptance 34 records structurally valid，final PASS 0/34，external effects 0。
- Delivery status deterministic rebuild/schema：PASS。
- Package Manifest：623 files PASS；publication、Governance、SBOM byte reproducibility、
  Stage 6/7 Secret scan 与 dependency audit：PASS/0 findings/0 known vulnerabilities。

## Git 与下一步

- worktree：当前隔离开发 worktree（主工作树保持只读）
- branch：`codex/moomooau-t0703-optional-token-echo`
- base：`bc0bfb3bc60a5ad769b286bb7b4bcdfc1ac195e6`
- 当前修复候选尚未 commit/push/PR/merge/dispatch。
- 下一步：完成 v1.0.11 package 与全量门禁；受控 PR 合入 main；等待 exact-main CI 全绿；核验
  Environment；仅 dispatch 新 main SHA attempt 1 一次。成功后只固化 T0703 receipt，
  不进入 T0704。
