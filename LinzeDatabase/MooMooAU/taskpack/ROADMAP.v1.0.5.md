# MooMooAU Archive Roadmap v1.0.5

本版本是 v1.0.4 的基线保真控制继任。v1.0.1 冻结的 Pursuing Goal、S0–S7、34 RQ、34 AC、58-task
DAG、Kill Criteria、固定发布原则和十条不变量全部继续有效，语义不变。

## 不变的权威契约

| 契约 | 数量或身份 | SHA-256 |
|---|---:|---|
| Requirements | 34 | `ea1c5ec0371576b1852cc23d5836eaf21b044a577ee6c6c1a92dddc3923bea27` |
| Acceptance Contracts | 34 | `3115ea47f01549218c817845554dc32b019a894708c4ac311e99249bcabf95bb` |
| Traceability Matrix | 34 RQ ↔ 34 AC ↔ 58 tasks | `263250bceb42d623c4491b99665dff3d1ba08e78f4e43a4fde74380a5e28abf2` |
| Task DAG | 58 tasks | `72785605390a31c8dbb0a5d349cf81418b158f7714e46fe8e7f8e4b113f318d9` |
| Kill Criteria | 原样继承 | `2a0494577382d1529721b05c6b03f874787f8c8deb5dbd4a56895624573f25dc` |
| Canonical Facts | 十条不变量 | `27110e8e6d8d337474eefa29f51d5bf294061c90dfebac2e0d898268dce96bf2` |
| v1.0.4 Manifest | 不可变直接前序 | `24b24ce8bd25b85f6c4dce3f7fbf6c8770b24e88be13f52be1d8d6a87b0c6e15` |
| v1.0.3 Manifest | 不可变控制前序 | `301fa1c6f5c46760c4aa3a7092bf0be77ca1a2e974e7b65e8b53dcf90db9925e` |
| v1.0.2 Manifest | 不可变基础前序 | `6767cd11ac260b66df1dd2dec892b73e91a2a6928c4185b1c4ff6446daa6a9b3` |
| v1.0.1 Manifest | 不可变历史本体 | `c2783bd232062ca123a725a3db2cf26a36c4a99a9476c432c36c850f86675c7f` |

## v1.0.5 只解决的控制问题

`REV-P1-006`：RMD-05 assurance provenance 由 candidate-bound receipt、immutable same-tree Git anchor、
两个模型家族各 18 次有序独立复审、完整 finding 闭包与确定性 post-review authority 共同证明。
Receipt17 的 19 个本地 gate 均为零退出且无外部写；最终回复只授权 RMD-05 本地物化，不授予受保护、
生产、部署或发布权限。

RMD-05 的验证范围只包括本地不可变 Git 对象、local synthetic gates、Stage 6 v2、冻结 Acceptance
materialization、唯一 delivery status 与 pinned Governance。平台 task identity 仍依赖保留的 Codex task
audit log；repository hash 不是第三方签名。

## 当前门状态

| 维度 | 当前值 | 是否允许提升 |
|---|---|---|
| Evidence 完整性 | 58/58 PASS | record、契约与 RMD-05 来源绑定有效 |
| 本地机制 | 58/58 有本地或合成证据 | 不替代受保护 Oracle |
| 正式任务 | 7 completed / 51 planned | 只有最终门满足后可改变 |
| 受保护 Oracle | 0/43 executed | 本轮未执行 |
| 最终 Acceptance | 0/34 PASS | 保持 BLOCKED |
| 生产 | 0 runs；Workflow 默认关闭 | RMD-06 也不自动授予生产权限 |
| 发布 | LOCAL_ONLY_NOT_PUBLISHED | RMD-07 最终干净快照前禁止上传 |

## 后续唯一顺序

RMD-05 完成后只按以下顺序逐 run 执行：RMD-06 protected 验收与观察 → RMD-07 最终复审、干净
snapshot 与一次性上传。每个 run 最多解决一个 task group；任何 Kill Criteria、未知受保护结果、证据漂移
或 secret finding 立即停止，不得降低 Gate。
