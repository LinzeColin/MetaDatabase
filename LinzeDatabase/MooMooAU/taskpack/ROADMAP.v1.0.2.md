# MooMooAU Archive Roadmap v1.0.2

本版本是 v1.0.1 的基线保真继任控制包。`ROADMAP.v1.0.1.md` 中的 Pursuing Goal、S0–S7 目标、交付、
Pass Gate、预计开发日、固定发布原则和十条产品不变量全部规范性并入本版本，语义不变。

## 不变的权威契约

| 契约 | 数量或身份 | SHA-256 |
|---|---:|---|
| Requirements | 34 | `ea1c5ec0371576b1852cc23d5836eaf21b044a577ee6c6c1a92dddc3923bea27` |
| Acceptance Contracts | 34 | `3115ea47f01549218c817845554dc32b019a894708c4ac311e99249bcabf95bb` |
| Traceability Matrix | 34 RQ ↔ 34 AC ↔ 58 tasks | `263250bceb42d623c4491b99665dff3d1ba08e78f4e43a4fde74380a5e28abf2` |
| Task DAG | 58 tasks | `72785605390a31c8dbb0a5d349cf81418b158f7714e46fe8e7f8e4b113f318d9` |
| Kill Criteria | 原样继承 | `2a0494577382d1529721b05c6b03f874787f8c8deb5dbd4a56895624573f25dc` |
| Canonical Facts | 十条不变量 | `27110e8e6d8d337474eefa29f51d5bf294061c90dfebac2e0d898268dce96bf2` |
| v1.0.1 Manifest | 不可变历史本体 | `c2783bd232062ca123a725a3db2cf26a36c4a99a9476c432c36c850f86675c7f` |

## v1.0.2 只解决的两个控制问题

1. `REV-P0-003`：权威 evidence validator 现在按 task 的真实 stage 选择 S0 既有规则或 S1–S7 对应
   schema、stage-local acceptance contract 与 final AC 绑定；58 个冻结 verification 路径无需改变。
2. `REV-P2-007`：`machine/status/latest.json` 成为唯一当前跨维度状态，明确区分 evidence 完整性、
   本地机制证据、正式任务完成度、受保护 Oracle、最终验收、生产就绪与发布。

这两个修复不改变冻结 task graph 中 `7 completed / 51 planned` 的正式状态，也不执行受保护 Oracle，
不启用生产，不运行真实 Gmail/私有仓/Secret，不写远端，不上传 GitHub。

## 当前门状态

| 维度 | 当前值 | 是否允许提升 |
|---|---|---|
| Evidence 完整性 | 58/58 PASS | 只说明 record 与契约绑定有效 |
| 本地机制 | 58/58 有本地或合成证据 | 不可替代受保护观察 |
| 正式任务 | 7 completed / 51 planned | 只有最终门满足后可改变 |
| 受保护 Oracle | 0/43 executed | 本轮禁止执行 |
| 最终 Acceptance | 0/34 PASS | 本轮保持 BLOCKED |
| 生产 | 0 runs；BLOCKED | 本轮禁止启用 |
| 发布 | LOCAL_ONLY_NOT_PUBLISHED | 最终干净快照前禁止上传 |

## 后续唯一顺序

RMD-02 完成后，后续仍按整体复审确定的顺序逐 run 执行：RMD-03 累计 CI → RMD-04 生产
composition → RMD-05 assurance provenance → RMD-06 protected 验收与观察 → RMD-07 最终复审、
干净 snapshot 与一次性上传。每个 run 最多解决一个 task group；任何 Kill Criteria 或未知受保护结果
立即停止，不得降低 Gate。
