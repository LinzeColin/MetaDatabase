# P4.4 / CB-430 Run Contract — 确定性故障、crash-cut、恢复与 restore 核心集

## 目标与边界

在 Owner 锁定的产品版本 `v0.0.0.5`、设计基线 `v0.0.0.4` 与 TaskPack
`v0.0.0.7` 下，完成 `CB-430` 的本地确定性故障恢复核心集。该 Run 只消费既有
fake clock、durable inbox/outbox、scheduler、canonical sync、cloud supervisor、
backup/restore 与 resource policy；不新建仓库、数据库或事实源。

本包 SHA-256：
`77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a`。

## Skill Router

- Router：`CB-430 -> output-skill`，模式 `NATIVE_IF_PRESENT_ELSE_EMBEDDED`
- 最大轻量 Skill body load：`1`；实际 Skill body load 为 `1`
- 未加载 Verifier、Teleiosis、Persona、SubAgent、第二模型或动态研究 Skill
- `output-skill` 仅用于完整性约束；不产生模型、网络或控制面调用

## 实现范围

- 新增固定 14-case matrix：fake-clock 日频/重大事件、历史回放、inbox
  persist-before-cursor、lease、outbox/canonical unknown outcome、service/runtime/channel、
  isolated restore 与有限自愈。
- 任何消息丢失、重复执行、重复副作用、无限重试、真实等待、provider 操作、模型调用或
  macOS `launchd` 依赖均 fail closed。
- post-deploy 全矩阵仅定义为 `manual_or_ci_nonblocking`；timer 安装与真实外部恢复为
  `activation_pending`，不安装 timer、不执行真实服务、数据或云端操作。

## 验收与验证

- `FA-AC-018`：核心 local matrix 与既有真实组件单元测试均为 `passed`，
  `loss=0`、`duplicate execution=0`、`duplicate side effects=0`。
- `FA-AC-019`：local rollback/restore 仅允许 `accepted_baseline_only` 指针；真实
  immutable candidate/current/previous 激活留给 `CB-440`。
- `FA-AC-027`：`blocking_wait_nodes=0`、`real_time_waits=0`；没有固定 sleep、
  观察等待或无限重试。

验证命令由 `scripts/validate_cb430.py` 在 credential-scrubbed 临时环境执行；它重跑
focused component suite、matrix CLI、App check/regression、TaskPack/DAG/traceability/no-wait，
并锚定 CB-420、CB-410、CB-400 的已封口证据。

## 风险、回滚与停止条件

本 Run 的唯一可变对象是本仓 `CyberBoss/**` 的实现与证据。若任一 matrix 输入不满足，
候选判为失败，保留既有接受基线；isolated restore 不 promote。消息丢失、重复副作用、
same-ID different-hash 覆盖、restore 不可读或无限重试为停止条件。

真实 Private-Database、R2、OCI、Cloudflare、service/runtime/channel 操作均为 `0`，
不折算为真实激活。下一原生节点为 `CB-440`，必须重新运行该节点的 Skill Router。
