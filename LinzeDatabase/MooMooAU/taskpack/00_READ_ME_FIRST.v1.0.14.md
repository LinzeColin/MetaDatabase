# MooMooAU v1.0.14 — T0703 历史 label 零写入 reconciliation

本包只推进 Stage 7 / T0703，不进入 T0704。

## 已知事实

- T0702/S7AC-002 protected Raw-only Beta 已通过。
- 六个 T0703 exact-main SHA 均只运行 attempt 1，rerun 为 0，且不得重新 dispatch。
- 第五次运行留下一个可恢复的加密 Processed lineage；精确 Gmail 来源归因仍未从聚合变化中声称。
- 第六次零写入 reconciliation 完成 Raw recovery 后停止于 `PROCESSED_PLAN`。
- 独立只读核验确认第六次前后 private repository head/tree、Raw、Processed、
  processed-current 与 Gmail Trash 均未变化。

## 修复边界

既有 Processed snapshot 在首次归档时绑定 pre-Trash Gmail label state；reconciliation 的实时
Raw fetch 正确观察到 post-Trash label state。v1.0.14 只从现有 age-encrypted Processed document
envelope 恢复历史 label state，并在重建同一 deterministic Processed bundle 时使用它。

历史 label 必须：

- 是已加密 current pointer → manifest → document envelope 绑定链的一部分；
- 是排序、唯一、符合 Gmail label token 约束的字符串序列；
- 不含 `SENT` 或 `DRAFT`；
- 对应的 first-import timestamp 不晚于本次 observation。

缺失、损坏、不规范或无法恢复时全部 fail closed，不回退到猜测值。

## 唯一授权

1. 只用 metadata 和 opaque pointer 绑定选择唯一 verified Trash source；
2. 完整 Raw 读取后验证既有 Raw recovery；
3. 从加密 Processed lineage 恢复历史 label state，重建并验证既有 Processed recovery；
4. 第二次验证 source 仍为同一消息且仍有 `TRASH`；
5. 输出累计 aggregate-only evidence。

本模式没有 Raw/Processed commit、GitHub Contents PUT 或 Gmail mutation 分支。

## 明确不授权

- 任一失败 SHA 的 rerun 或 redispatch；
- `users.messages.trash` 或其他 Gmail mutation；
- 新 Raw、Processed、Timeline 或 private-repository 写入；
- Blue-Green、T0704、GA、04:30 schedule、最终 Acceptance 或最终发布。
