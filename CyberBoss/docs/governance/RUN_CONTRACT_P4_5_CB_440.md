# P4.5 / CB-440 Run Contract — Immutable candidate、slots、请求数 predicate 与回滚

## 目标与边界

在 Owner 锁定的产品版本 `v0.0.0.5`、设计基线 `v0.0.0.4` 与 TaskPack
`v0.0.0.7` 下，构建 CB-440 的本地 immutable release candidate contract。它复用既有
immutable release layout 和 `candidate/current/previous` 语义，不创建新仓库、远端制品、
数据库、Private-Database 写入或平行事实源。

本包 SHA-256：
`77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a`。

## Skill Router

- Router：`CB-440 -> output-skill`，模式 `NATIVE_IF_PRESENT_ELSE_EMBEDDED`
- 最大轻量 Skill body load：`1`；实际 Skill body load 为 `1`
- 未加载 Verifier、Teleiosis、Persona、SubAgent、第二模型或动态研究 Skill
- `output-skill` 只用于确保完整 release manifest、runbook、test 与 closure 输出

## 实现范围

- 绑定 CB-430 closure、lockfile 与 source-lock SHA-256；candidate identity 为稳定内容摘要。
- 固定 `candidate/current/previous` 三 slot，candidate immutable 且绝不切换 `current`；
  P0/P1 触发 `previous` 的 immediate pointer restore，无 fixed wait。
- 仅启用 frozen MVP flags；Claude、attachments、full content 与 autonomous mutation 全部为
  false。migration 仅为 additive/backward-read local fixture，绝不执行真实 migration。
- 固定 8 request-count predicates：5 个只读、1 个拒绝、1 个取消、1 个可逆 local mutation。
  任何 P0 failure 使 candidate `discard_candidate_keep_current`。
- operator runbook 是 contract-only；candidate install/current switch/live canary/rollback 都为
  `activation_pending`，不会安装服务、调用 provider、真实请求或模型。

## 验收与停止条件

- `FA-AC-019`：candidate manifest/content hash 固定、slots 不重叠、rollback pointer 有效，
  P0 fixture 立即要求 rollback。
- `FA-AC-024`：8 条 operator command contract 可解析；live command 都显式需要未来
  external authority。
- `FA-AC-029`：Task → tests → evidence → manifest → Subject 由 validator 闭环。

release identity 可变、rollback pointer 无效、manifest 不完整、out-of-scope flag、destructive
migration 或任何等待是停止条件；失败只丢弃未接受 candidate，保持 current 不变。下一原生节点
为 `PG-4`，且只运行该 gate 的 deterministic Router，不加载 Skill。
