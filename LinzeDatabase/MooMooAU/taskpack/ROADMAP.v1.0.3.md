# MooMooAU Archive Roadmap v1.0.3

本版本是 v1.0.2 的基线保真控制继任。v1.0.2 规范性并入的 Pursuing Goal、S0–S7 目标、交付、
Pass Gate、预计开发日、固定发布原则和十条不变量全部继续有效，语义不变。

## 不变的权威契约

| 契约 | 数量或身份 | SHA-256 |
|---|---:|---|
| Requirements | 34 | `ea1c5ec0371576b1852cc23d5836eaf21b044a577ee6c6c1a92dddc3923bea27` |
| Acceptance Contracts | 34 | `3115ea47f01549218c817845554dc32b019a894708c4ac311e99249bcabf95bb` |
| Traceability Matrix | 34 RQ ↔ 34 AC ↔ 58 tasks | `263250bceb42d623c4491b99665dff3d1ba08e78f4e43a4fde74380a5e28abf2` |
| Task DAG | 58 tasks | `72785605390a31c8dbb0a5d349cf81418b158f7714e46fe8e7f8e4b113f318d9` |
| Kill Criteria | 原样继承 | `2a0494577382d1529721b05c6b03f874787f8c8deb5dbd4a56895624573f25dc` |
| Canonical Facts | 十条不变量 | `27110e8e6d8d337474eefa29f51d5bf294061c90dfebac2e0d898268dce96bf2` |
| v1.0.2 Manifest | 不可变控制前序 | `6767cd11ac260b66df1dd2dec892b73e91a2a6928c4185b1c4ff6446daa6a9b3` |
| v1.0.1 Manifest | 不可变历史本体 | `c2783bd232062ca123a725a3db2cf26a36c4a99a9476c432c36c850f86675c7f` |

## v1.0.3 只解决的控制问题

`REV-P1-004`：S3–S6 的 GitHub Workflow 入口现在显式选择 `--cumulative-final`，允许已经由后续
stage validator 接管的实现路径存在；无参数历史模式仍保留原 scope gate 并确定性 fail closed。离线
Workflow command matrix 绑定四份 Workflow 字节哈希，回放四个累计 PASS 与四个历史负向控制，且要求
项目树字节不变、外部写入和受保护/生产运行计数均为零。

该修复不改变冻结 task graph 的 `7 completed / 51 planned`，不执行受保护 Oracle，不启用生产，不访问
真实 Gmail/私有仓/Secret，不写远端，不上传 GitHub；离线 PASS 也不冒充远端 Workflow run。

## 当前门状态

| 维度 | 当前值 | 是否允许提升 |
|---|---|---|
| Evidence 完整性 | 58/58 PASS | 只说明 record 与契约绑定有效 |
| 本地机制 | 58/58 有本地或合成证据 | 不可替代受保护观察 |
| 累计最终树入口 | S3–S6 4/4 本地 PASS；历史负向控制 4/4 | 远端 CI 仍 NOT_RUN |
| 正式任务 | 7 completed / 51 planned | 只有最终门满足后可改变 |
| 受保护 Oracle | 0/43 executed | 本轮禁止执行 |
| 最终 Acceptance | 0/34 PASS | 本轮保持 BLOCKED |
| 生产 | 0 runs；BLOCKED | 本轮禁止启用 |
| 发布 | LOCAL_ONLY_NOT_PUBLISHED | 最终干净快照前禁止上传 |

## 后续唯一顺序

RMD-03 完成后只按以下顺序逐 run 执行：RMD-04 生产 composition → RMD-05 assurance provenance →
RMD-06 protected 验收与观察 → RMD-07 最终复审、干净 snapshot 与一次性上传。每个 run 最多解决一个
task group；任何 Kill Criteria 或未知受保护结果立即停止，不得降低 Gate。
