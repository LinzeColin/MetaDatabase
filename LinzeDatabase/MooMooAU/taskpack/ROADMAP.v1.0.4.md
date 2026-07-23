# MooMooAU Archive Roadmap v1.0.4

本版本是 v1.0.3 的基线保真控制继任。v1.0.1 冻结的 Pursuing Goal、S0–S7、34 RQ、34 AC、58-task
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
| v1.0.3 Manifest | 不可变直接前序 | `301fa1c6f5c46760c4aa3a7092bf0be77ca1a2e974e7b65e8b53dcf90db9925e` |
| v1.0.2 Manifest | 不可变控制前序 | `6767cd11ac260b66df1dd2dec892b73e91a2a6928c4185b1c4ff6446daa6a9b3` |
| v1.0.1 Manifest | 不可变历史本体 | `c2783bd232062ca123a725a3db2cf26a36c4a99a9476c432c36c850f86675c7f` |

## v1.0.4 只解决的控制问题

`REV-P0-002`：生产 Workflow 不再只生成 schedule plan 后停机；它绑定唯一 fail-closed composition root。
该 root 严格装配 Gmail OAuth、GitHub App Repository-ID guard、官方 age、加密 checkpoint、Raw、
Processed、远程恢复、exact message Trash、私有 Timeline snapshot 和单一 live Asset，并在结束时销毁全部
受保护内存/临时 identity。Sydney 成功日期进入加密远程 checkpoint，调度计划不依赖本地状态。

RMD-04 的验收证据来自合成 Gmail/GitHub HTTP 远端和真实官方 age 二进制，不访问真实账号或仓库，不读取
真实 Secret，不执行 Workflow。production config schema 可以承载未来受保护证据，但本地测试中的
`PROTECTED_GITHUB_ACTIONS` 字段只是合成输入，绝不计为受保护 Oracle。

## 当前门状态

| 维度 | 当前值 | 是否允许提升 |
|---|---|---|
| Evidence 完整性 | 58/58 PASS | 只说明 record 与契约绑定有效 |
| 本地机制 | 58/58 有本地或合成证据 | RMD-04 composition 本地合成 PASS |
| 正式任务 | 7 completed / 51 planned | 只有最终门满足后可改变 |
| 受保护 Oracle | 0/43 executed | 本轮未执行 |
| 最终 Acceptance | 0/34 PASS | 保持 BLOCKED |
| 生产 | 0 runs；Workflow 默认关闭 | 后续 RMD-06 前禁止启用 |
| 发布 | LOCAL_ONLY_NOT_PUBLISHED | 最终干净快照前禁止上传 |

## 后续唯一顺序

RMD-04 完成后只按以下顺序逐 run 执行：RMD-05 assurance provenance → RMD-06 protected 验收与观察 →
RMD-07 最终复审、干净 snapshot 与一次性上传。每个 run 最多解决一个 task group；任何 Kill Criteria、
未知受保护结果或组合漂移立即停止，不得降低 Gate。
