# MooMooAU v1.0.21 — T0705 Protected GA metadata quarantine 修复候选

本包只处理 Stage 7 / T0705 与 S7AC-005。它冻结两次 protected GA 失败 head，仅修复
GA pre-Raw candidate loop 缺少的 `MessageMetadataUnverifiable` 逐消息隔离，不重跑失败
head，不等待墙钟 04:30，也不把手动触发伪称为平台 schedule event。

## 已证明的失败边界

- PR #115 与 PR #116 合入的两个 exact-main head 分别只执行 attempt 1、rerun 0；两个 head
  永久禁止 rerun 与 redispatch。
- 第二次 run `30184702520` 的 authority 与 identity cleanup PASS，protected GA FAILED，
  live schedule hold SKIPPED。
- 独立后验聚合核验确认第二次运行新增 private commit 0、checkpoint 未创建、唯一 latest
  Timeline 仍为 1；一次性 authority 和 production enablement 均已清除。
- protected 输出只公开 `PROTECTED_GA_FAILED`，没有公开 exact runtime exception。本包只记录
  可证 failure boundary，并把同邮箱不可变前序回执与静态路径共同支持的缺口标为
  high-confidence diagnosis，不把它伪装成线上精确异常。

## 唯一修复

- GA 首次 metadata read 若抛出 typed `MessageMetadataUnverifiable`，只把该 candidate 计入
  quarantine 并跳过；不得 Full Fetch、写 Raw/Processed、Trash 或推进其状态。
- 既有 pending verified source 不得因本轮 metadata 不可验证而从 checkpoint replay 集合消失。
- Raw/Processed 远端恢复后的第二次 metadata verification 继续 fail closed；不得被隔离逻辑吞掉。
- `ACTIVE` registry 与 paired-empty `SAFE_DEFERRED` 行为保持不变。
- 新入口继续要求 owner、exact main、固定 workflow ref、attempt 1、rerun 0 与 one-shot
  exact-head authority，并在 Secret 前拒绝两个冻结 head。

## 剩余效果预算

- 总 controlled main delivery 最多 4；两次 launch 已消耗 2，只剩 metadata repair 1 与
  receipt/schedule closure 1。
- 总 protected rehearsal dispatch 最多 3；两次失败 attempt 已消耗 2，只剩一个新 repair
  dispatch；所有 rerun 均为 0。
- repair GA pipeline run 最多 1，exact-message Trash 最多 1，live Timeline Asset 最多且健康
  稳态恰好 1。
- rehearsal 期间 platform schedule event 0；T0706、Recovery Drill、Patch Lifecycle
  protected run、最终 Acceptance 与最终发布均为 0。

## 停止边界

当前包只证明本地修复候选与两份不可变失败谱系，尚未证明 T0705/S7AC-005 PASS。唯一新
protected repair rehearsal 的精确回执绑定前，04:30 live schedule 保持关闭；PASS 后才允许
一次 closure delivery 固化回执并启用已提交 schedule，随后停止在 T0706 前。
