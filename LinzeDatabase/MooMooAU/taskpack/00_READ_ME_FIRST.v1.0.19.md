# MooMooAU v1.0.19 — T0705 Protected GA 候选

本包只处理 Stage 7 / T0705 与 S7AC-005 的受保护候选。它不重跑任何历史 head，不等待墙钟
04:30，也不把手动触发伪称为平台 schedule event。

## 已证明的候选事实

- T0702、T0703、T0704 精确 protected PASS 回执及失败账本保持不可变并由摘要绑定。
- 新入口只接受 owner、exact main、固定 workflow ref、attempt 1、rerun 0 和 one-shot exact-head
  authority；任一不符都在 Secret 前失败关闭。
- 复用现有 `moomooau-beta` Environment 的八个精确 Secret 名称，配置只在内存中派生，不复制值。
- GitHub App 必须先只读刷新唯一私有仓的实时容量，之后才允许交换 Gmail credential。
- 只有确定性 `VERIFIED` 候选可完整读取；Raw 与 Processed 必须远端恢复并二次验证，之后才可
  对精确 source message 使用最多一次 `users.messages.trash`。
- Timeline snapshot、唯一 latest age Asset 与最后一步加密 checkpoint CAS 都必须远端恢复。
- `workflow_dispatch` 调用生产 `RunTrigger.SCHEDULE` 路径，目标为
  `04:30 Australia/Sydney`，公开模式固定为 `SCHEDULE_REHEARSAL`，
  `platform_schedule_event_observed=false`。

## 当前效果预算

- controlled main delivery 最多 2：launch 1、receipt/authority closure 1；
- protected rehearsal dispatch 1、rerun 0、GA pipeline run 1；
- exact-message Trash 最多 1，Timeline latest live Asset 恰好 1；
- rehearsal 期间 platform schedule event 0；
- T0706、Recovery Drill、Patch Lifecycle protected run、最终 Acceptance 与最终发布均为 0。

## 停止边界

当前包只证明候选可运行，尚未证明 T0705/S7AC-005 PASS。唯一 protected rehearsal 的精确回执
绑定前，04:30 live schedule 保持关闭；PASS 后才允许一次 closure delivery 启用已提交 schedule，
随后停在 T0706 前。
