# MooMooAU v1.0.22 — T0705 Protected GA persisted-label replay 修复候选

本包只处理 Stage 7 / T0705 与 S7AC-005。它冻结三次 protected GA 失败 head，仅修复 GA 在
重建既有 Processed 来源 envelope 时没有重放持久化 first-import label state 的缺口；不重跑
失败 head，不等待墙钟 04:30，也不把 `workflow_dispatch` 伪称为平台 schedule event。

## 已证明的失败边界

- PR #115、#116 与 #117 合入的三个 exact-main head 均只执行 attempt 1、rerun 0；三个 head
  永久禁止 rerun 与 redispatch。
- 第三次 run `30187132406` 的 authority 与 identity cleanup PASS，protected GA FAILED，
  live schedule hold SKIPPED。
- 独立后验确认第三次运行新增 private commit 0、checkpoint 未创建、active Moomoo candidate
  仍在 Trash 外、加密 Timeline state 存在；一次性 authority 和 production enablement 均已清除。
- protected 输出只公开 `PROTECTED_GA_FAILED`，没有公开 exact runtime exception。本包只记录
  可证 failure boundary，并把 T0704 已验证的历史 label replay 与静态 root 构造共同支持的缺口
  标为 high-confidence diagnosis，不把它伪装成线上精确异常。
- 未独立重测的 release asset 状态与 Gmail mutation API trace 明确不声明。

## 唯一修复

- GA 继续从远端 Processed lineage 解析 first-import timestamp，并同时调用
  `resolve_label_state()` 解析 first-import label state。
- `DocumentEnvelopeFactory.issue()` 只对既有来源使用该历史 label override，避免 Gmail 当前
  `TRASH` label 改变同 parser version 的不可变 Processed roots。
- pre-Raw `MessageMetadataUnverifiable` quarantine、既有 pending replay、Raw/Processed 远端
  恢复、second verification fail closed、`ACTIVE` 与 paired-empty `SAFE_DEFERRED` 均保持不变。
- 新入口继续要求 owner、exact main、固定 workflow ref、attempt 1、rerun 0 与 one-shot
  exact-head authority，并在 Secret 前拒绝三个冻结 head。

## 剩余效果预算

- 总 controlled main delivery 最多 5；三次 launch 已消耗 3，只剩 label-replay repair 1 与
  receipt/schedule closure 1。
- 总 protected rehearsal dispatch 最多 4；三次失败 attempt 已消耗 3，只剩一个新 repair
  dispatch；所有 rerun 均为 0。
- repair GA pipeline run 最多 1，exact-message Trash 最多 1，live Timeline Asset 最多且健康
  稳态恰好 1。
- rehearsal 期间 platform schedule event 0；T0706、Recovery Drill、Patch Lifecycle
  protected run、最终 Acceptance 与最终发布均为 0。

## 停止边界

当前包只证明本地修复候选与三份不可变失败谱系，尚未证明 T0705/S7AC-005 PASS。唯一新
protected repair rehearsal 的精确回执绑定前，04:30 live schedule 保持关闭；PASS 后才允许
一次 closure delivery 固化回执并启用已提交 schedule，随后停止在 T0706 前。
