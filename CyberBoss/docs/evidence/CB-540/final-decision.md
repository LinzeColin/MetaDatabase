# CB-540 最终开发候选

开发候选为 `MVP_DEGRADED`，不是 `MVP_LIVE`。产品版本仍为 `v0.0.0.5`，当前 immutable
release 为 `fd3cd1e19d70caa148c3785288aaabfb909fed85`，previous 为
`25670bf32c6d27e3668fcf59bc9ab754035e161d`。

已绑定到该 release 的真实回证包括：loopback health/Timeline、匿名 Status 拒绝、Cloudflare
Access challenge、Tunnel、全局 Status 刷新、Private-Database daily/material sync、R2 isolated
restore 既有回证、OCI write-only PAR 的明确 pending、self-heal 的精确 channel-pending journal
marker，以及一次 `current → previous → current` 有限回滚闭环。所有控制面与运维模型调用均为
0；没有 macOS launchd、Private-Database clone、模拟器、真实时间等待或新增事实源。

降级项保持可见：真实 WeChat credential 未授权，因此 `/readyz=503` 且 `channel,bridge` 未 ready；
Access service-token 最小 scope、Cloudflare Web Analytics 与 OCI daily PAR readback 仍是明确
pending。self-heal 将这一精确 `channel_pending` 状态记录为 degraded 且不重启活跃 cloud process，其他
readiness shape 均 fail closed。

`FORMAL_FINAL_ACCEPTANCE` 保持 `BLOCKED`，原因是外部独立验收 contexts 不在开发 DAG 内，
不是产品停止条件；下一原生节点为 `PG-5`。
