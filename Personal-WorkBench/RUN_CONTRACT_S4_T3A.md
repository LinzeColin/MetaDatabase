# Run Contract — S4-T3A 独立候选就绪审查

## 定位

这是 [PWB-S4-S5-SEQUENCE-001](./ACCEPTANCE_SEQUENCE_ADDENDUM.md) 定义的新增子阶段。它修复原 `S4-T3 → S5-T1` 的证据循环，但不替代冻结任务包的最终 15/15 验收。其结果只能是 `READINESS_PASS` 或 `BLOCKED`。

## 目标

由与 Builder 分离的独立 context 对精确、干净的 source commit 做候选就绪审查，确认不存在已知未关闭 P0/P1、顺序增补未漂移、本地证据身份可追溯，并仅在通过后允许创建一个私有且可丢弃的 Sites Saved Version 采集真实证据。

## 输入与最小范围

- 精确 source commit、tree、工作树干净状态与受控 build identity；
- 冻结任务包与 `ACCEPTANCE_SEQUENCE_ADDENDUM.json` 的只读校验结果；
- Builder 本地预检及整改记录，作为无裁决权观察；
- 代码、合同和本地证据的只读审查。

不创建 Sites Version、不改访问策略、不配置 Secret、不部署、不访问真实用户数据、不写 `r-001` 至 `r-015` 的产品通过证据。

## 必须验证

1. `TASKPACK_ROOT=… npm run validate:acceptance-sequence` 返回 `PASS_SEQUENCE_ADDENDUM_INTEGRITY_ONLY` 和 `NOT_PRODUCT_ACCEPTANCE`。
2. HEAD、tree、工作树、依赖锁定与 Builder 观察都绑定到同一精确 Subject。
3. 本地 P0/P1 整改已被独立复核；若发现新的 P0/P1，返回 `BLOCKED` 并只给出最小 remediation。
4. 明确记录仍待 S5 真实采证的 Requirement；这些项不得被记为 PASS。
5. 审查者不能修改产品、合同或证据；其结论独立于 Builder。

## 通过后的唯一授权

`READINESS_PASS` 仅可解锁 `S5-T1` 的**私有** Saved Version。该 Version 只能用于真实采证，保持私有 audience，可随时丢弃；它不是公开发布，也不是 S4/S6 的最终通过。

## 停止与回滚

- 任一身份不一致、任务包/增补漂移、P0/P1、或无法区分本地观察与最终验收：`BLOCKED`。
- 保持现有 Sites 状态，不创建或丢弃未完成 Candidate；不改公开 audience。
- 不得把 `READINESS_PASS` 用于 S6-T2 或 GitHub 上传。
