# MooMooAU v1.0.13 — T0703 零新增写入 reconciliation

本包只推进 Stage 7 / T0703，不进入 T0704。

## 已知事实

- T0702/S7AC-002 protected Raw-only Beta 已通过。
- 五个 T0703 exact-main SHA 均只运行 attempt 1，且不得 rerun 或 redispatch。
- 第五次运行在 Raw、Processed 与远端恢复完成后公开
  `aggregate_failure_class=MUTATION_FAILED`。
- 独立只读检查观察到 encrypted `processed-current` 从零变一、Gmail Trash 聚合加一；
  这些聚合变化不单独证明二者属于同一 exact source，因此精确来源归因仍未声称。

## 本候选唯一授权

1. 在任何完整 Raw 读取前，只用 metadata、deterministic sender verification 与 opaque ID
   寻找同时满足以下条件的来源：
   - 已带 `TRASH`；
   - 对应 pre-existing encrypted `processed-current`；
   - 全部候选中恰好一个匹配。
2. 对该 exact source 重做 Canonical Raw、Processed 与 remote recovery。
3. 重做第二次 sender verification，并要求 `TRASH` 仍存在。
4. 输出累计 reconciliation evidence。

reconciliation 模式没有 Raw/Processed commit、GitHub Contents PUT 或 Gmail mutation 分支。
零个或多个匹配、状态漂移、恢复失败或第二次验证失败都必须 fail closed。

## 明确不授权

- 任何失败 SHA 的 rerun/redispatch；
- `users.messages.trash` 或其他 Gmail mutation；
- 新 Raw/Processed/private-repository 写入；
- Timeline、Blue-Green、T0704、04:30 schedule、GA、最终 Acceptance 或最终发布。
