# MooMooAU 当前交接

更新时间：2026-07-26（Australia/Sydney）

## 当前目标与状态

- 本轮只处理 Stage 7/T0705，必须停在 T0706 前。
- 当前候选包：`MMAU-ARCHIVE-TP-2026-07-26-V1.0.19`。
- 不可变直接前序：`taskpack/PACKAGE_MANIFEST.v1.0.18.json`，SHA-256
  `957ce9a5455d85927080e913ac364c2dfdd9a019b8d0426fa07b39fd965cf25e`。
- 唯一状态权威：`machine/status/latest.json` =
  `PROTECTED_BLUE_GREEN_PASS_T0705_AUTHORIZED_PENDING`。
- Protected Oracles 4/43 executed、4 PASS、0 FAILED；final Acceptance 0/34；
  T0705 production workflow 0；final publication 0。

## 已冻结前序

- T0702、T0703、T0704 protected PASS receipts 及全部 failed-attempt ledgers 不可变。
- T0704 成功 run `30178201201` 绑定 main `65cef099…`，attempt 1、rerun 0；一个可恢复
  age-encrypted latest Timeline 已验证。
- 任何历史失败或成功 head 均不得 rerun/redispatch。

## T0705 候选

- `protected_ga_entrypoint.py` 绑定 owner、exact main、固定 workflow ref、attempt 1、
  one-shot exact-head authority、T0702–T0704 receipts 与当前 Run Contract。
- 复用现有 `moomooau-beta` 八个精确 Secret 名称，值不复制、不写盘、不公开。
- 已安装 GitHub App 必须在 Gmail exchange 前刷新唯一私有仓实时容量。
- 只完整读取确定性 `VERIFIED` 来源；Raw/Processed 恢复及二次验证后才允许最多一次精确
  `users.messages.trash`。
- Timeline snapshot、唯一 latest age Asset 与最后一步 encrypted checkpoint CAS 均需恢复。
- workflow_dispatch 如实称为 `SCHEDULE_REHEARSAL`，只调用与生产一致的 SCHEDULE planner；
  rehearsal 的 platform schedule event 必须为 0。

## 当前安全边界与下一步

- 允许 launch delivery 1、protected rehearsal dispatch 1、rerun 0、closure delivery 1。
- protected PASS receipt 绑定前，`MOOMOOAU_PRODUCTION_ENABLED` 不得为 true。
- 合入 exact-main candidate 后只设置一个 exact-head authority，运行一次；无论结果如何立即删除。
- PASS 后才固化 receipt、关闭 rehearsal 入口并启用已提交 04:30 Australia/Sydney schedule。
- 不进入 T0706，不创建 Codex Automation，不运行 Recovery Drill/Patch Lifecycle，不做最终发布。
