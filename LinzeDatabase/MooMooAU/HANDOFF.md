# MooMooAU 当前交接

更新时间：2026-07-26（Australia/Sydney）

## 当前目标与状态

- 本轮只处理 Stage 7/T0705，必须停在 T0706 前。
- 当前候选包：`MMAU-ARCHIVE-TP-2026-07-26-V1.0.20`。
- 不可变直接前序：`taskpack/PACKAGE_MANIFEST.v1.0.19.json`，SHA-256
  `eb32ab3ef990a5273978ab548fe063d6ba954c7fff8c2a416830b2ee94cfaf61`。
- 唯一状态权威：`machine/status/latest.json` =
  `PROTECTED_GA_ATTEMPT_FAILED_REPAIR_AUTHORIZED`。
- Protected Oracles 5/43 executed、4 PASS、1 FAILED；final Acceptance 0/34；
  T0705 production workflow 1；final publication 0。

## 已冻结前序

- T0702、T0703、T0704 protected PASS receipts 及全部 failed-attempt ledgers 不可变。
- T0704 成功 run `30178201201` 绑定 main `65cef099…`，attempt 1、rerun 0；一个可恢复
  age-encrypted latest Timeline 已验证。
- T0705 首次 run `30182491342` 绑定 PR #115/main `eb7ad073…`；authority 与 cleanup PASS，
  protected GA FAILED，live schedule hold SKIPPED，attempt 1、rerun 0。
- T0705 独立后验确认 private commit 与 Raw/Processed/State/other path change 均为 0，
  Gmail mutation endpoint 未到达，checkpoint 未创建，唯一 latest Timeline 仍为 1。
- 任何历史失败或成功 head 均不得 rerun/redispatch；尤其不得重新触发 `eb7ad073…`。

## T0705 repair 候选

- `protected_ga_entrypoint.py` 绑定 owner、exact main、固定 workflow ref、attempt 1、
  one-shot exact-head authority、T0702–T0704 receipts 与当前 Run Contract。
- 复用现有 `moomooau-beta` 八个精确 Secret 名称，值不复制、不写盘、不公开。
- 已安装 GitHub App 必须在 Gmail exchange 前刷新唯一私有仓实时容量。
- 只完整读取确定性 `VERIFIED` 来源；Raw/Processed 恢复及二次验证后才允许最多一次精确
  `users.messages.trash`。
- Timeline snapshot、唯一 latest age Asset 与最后一步 encrypted checkpoint CAS 均需恢复。
- workflow_dispatch 如实称为 `SCHEDULE_REHEARSAL`，只调用与生产一致的 SCHEDULE planner；
  rehearsal 的 platform schedule event 必须为 0。
- 仅当 classification/parser registries 同为 `EMPTY_PROTECTED_EVIDENCE_REQUIRED` 且内容为空，
  才允许显式 SAFE_DEFERRED fallback；ACTIVE registry 行为保持不变。
- authority job 把已验证的新 exact head 作为 job output 传入 protected job；删除一次性仓库变量
  不会令 job 回退到未绑定 head。

## 当前安全边界与下一步

- 总 delivery 最多 3，失败 launch 已消耗 1；只剩 repair delivery 1 与 closure delivery 1。
- 总 rehearsal dispatch 最多 2，失败 attempt 已消耗 1；只剩一个新 repair dispatch，rerun 0。
- protected PASS receipt 绑定前，`MOOMOOAU_PRODUCTION_ENABLED` 不得为 true。
- 合入新 exact-main repair candidate 后只设置一个 exact-head authority，运行一次；无论结果
  如何立即删除；绝不 rerun 或 redispatch 失败 head。
- PASS 后才固化 receipt、关闭 rehearsal 入口并启用已提交 04:30 Australia/Sydney schedule。
- 不进入 T0706，不创建 Codex Automation，不运行 Recovery Drill/Patch Lifecycle，不做最终发布。
