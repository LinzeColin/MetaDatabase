# MooMooAU v1.0.20 — T0705 Protected GA SAFE_DEFERRED 修复候选

本包只处理 Stage 7 / T0705 与 S7AC-005。它冻结首次 protected GA 失败 head，仅修复
T0704 已证明的 paired-empty registry 与 GA runtime/bootstrap 不兼容，不重跑失败 head，
不等待墙钟 04:30，也不把手动触发伪称为平台 schedule event。

## 已证明的失败边界

- PR #115 合入的 exact-main head `eb7ad073…` 只执行 attempt 1、rerun 0；authority 与
  identity cleanup PASS，protected GA FAILED，live schedule hold SKIPPED。
- 独立后验聚合核验确认该运行新增 private commit 0，Raw、Processed、State 与其他路径变化均为
  0；Gmail mutation API 未到达，checkpoint 未创建，唯一 live Timeline Asset 仍为 1。
- protected 输出没有公开 exact runtime exception，因此账本只声明可证的 failure boundary，
  不伪造更细线上异常。
- 失败 head、账本与 schema 均由摘要绑定；该 head 永久禁止 rerun 与 redispatch。

## 唯一修复

- `ACTIVE` classification/parser registries 保持原行为。
- 仅当两份 registry 同为 `EMPTY_PROTECTED_EVIDENCE_REQUIRED` 且 rules/profiles 都为空时，
  GA bootstrap/runtime 才进入显式 SAFE_DEFERRED-only 模式。
- SAFE_DEFERRED 解析使用已提交的 protected fallback parser version；不得把空证据提升为
  ACTIVE，不得绕过 quarantine、remote recovery、二次验证或 mutation gate。
- 新入口继续要求 owner、exact main、固定 workflow ref、attempt 1、rerun 0 与 one-shot
  exact-head authority；失败 head 会在 Secret 前被拒绝。

## 剩余效果预算

- 总 controlled main delivery 最多 3；失败 launch 已消耗 1，只剩 repair 1 与
  receipt/schedule closure 1。
- 总 protected rehearsal dispatch 最多 2；失败 attempt 已消耗 1，只剩一个新 repair
  dispatch；所有 rerun 均为 0。
- repair GA pipeline run 最多 1，exact-message Trash 最多 1，live Timeline Asset 恰好 1。
- rehearsal 期间 platform schedule event 0；T0706、Recovery Drill、Patch Lifecycle
  protected run、最终 Acceptance 与最终发布均为 0。

## 停止边界

当前包只证明本地修复候选与不可变失败谱系，尚未证明 T0705/S7AC-005 PASS。唯一新 protected
repair rehearsal 的精确回执绑定前，04:30 live schedule 保持关闭；PASS 后才允许一次 closure
delivery 固化回执并启用已提交 schedule，随后停在 T0706 前。
