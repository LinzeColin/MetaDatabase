# P5.5 / CB-540 Run Contract — 精确候选与 Subject 密封

## 目标

在不改变 CyberBoss `v0.0.0.5`、不创建平行事实源且不使用 macOS `launchd` 的前提下，
收敛最终可验证的开发候选并输出精确 Subject。CB-540 只判定开发候选
`MVP_LIVE`、`MVP_DEGRADED`、`ACTIVATION_PENDING` 或 `STOPPED`；它不自行声称外部
正式验收。

## 最小范围

- 既有 CB-530 immutable release、Cloudflare Access、Status、Private-Database 同步与
  R2/OCI receipt；不创建仓库、数据库或新的业务事实源。
- 新增一个只请求 `127.0.0.1:8780` 的 deterministic self-heal health wrapper；它仅把
  精确的 `channel,bridge` pending shape 归为受控 degraded，其他状态均 fail closed。
- Linux `systemd` 的现有 self-heal unit 通过最小 drop-in 使用该 wrapper；没有
  launchd、sleep、轮询等待、控制面/运维模型调用或第二模型。
- `docs/evidence/CB-540/`、`docs/evidence/PG-5/`、任务状态和本地 validator 只在全部
  subject inputs 已由真实命令回证后更新。

## 验收与停止条件

- 运行 TaskPack CB-540 Router；允许的 lightweight Skill body load 上限为 1，实际为 0。
- 通过 wrapper focused test、现有应用回归、release immutable/rollback pointer、loopback
  Timeline/Status、Cloudflare Access、Private-Database、R2/OCI 和 self-heal receipt。
- 任何 release hash、subject seal、secret/privacy scan、模型计数、当前/previous pointer
  或 non-loopback predicate 异常都 fail closed；回滚只原子恢复已接受 previous release，
  不删除 backup、数据、证据或 remote object。
- 外部正式验收缺乏独立权威时仅写 `FORMAL_FINAL_ACCEPTANCE=BLOCKED`；这不是开发 DAG
  的等待节点，也不阻塞真实 `MVP_DEGRADED` 或其他开发候选的输出。
