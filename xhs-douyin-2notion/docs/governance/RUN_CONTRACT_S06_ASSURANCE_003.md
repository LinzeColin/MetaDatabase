# Stage 6 Assurance003 Run Contract

## Identity

- Task: `TSK.x2n.assurance.003`
- Phase: `PH.X2N.6.3`
- Run: `RUN-X2N-S06-A003`
- Base: `28499818c2f99a2046a386d88c2ed0c85004bc56`

## Single-task scope

本 Run 只完成公共源码、候选发布制品与本地 Git 历史的安全、隐私、许可证和供应链验收。它复验
source/private/CDN scanner、SAST、SBOM、license、匿名 OSV、CSP、SSRF、临时媒体边界、release allowlist、
以及 active `owner-mvp-plan` 命名面。

历史检查只检测凭据形状或带认证的 Git remote，并只发布规则类别与聚合计数；当前源码和候选制品仍执行
完整 private/CDN 扫描。这样既不把历史合成负例误报为泄漏，也不读取、显示、传递或修改任何共享认证材料。

## Acceptance mapping

| Acceptance | 本 Run 的可复验证据 |
|---|---|
| `ACC.x2n.gov.002` | 最小环境、认证控制零接触、当前源码与历史凭据扫描均为零 |
| `ACC.x2n.gov.003` | SBOM 33 components、许可证 unknown=0、候选制品 allowlist/private/CDN 均为零 |
| `ACC.x2n.media.001` | 五 scope 持久化边界与公共扫描零命中 |
| `ACC.x2n.media.003` | 512 URL fuzz、32 SSRF 禁止目标、local-file read 均为零 |
| `ACC.x2n.media.004` | FFmpeg/FFprobe 派生产物保持 lease-bounded、temporary-only |
| `ACC.x2n.rel.003` | SAST、匿名 OSV、SBOM、license、artifact 与历史凭据检查全部通过 |

## Stop conditions

任一当前源码或候选制品的 Secret/private/CDN 命中，任一历史凭据或认证 remote 命中，任一 unresolved
critical/high vulnerability、unknown runtime license、allowlist/CSP/SSRF/media 边界失败，全部 Fail Closed。

## Boundary and rollback

本 Run 的平台调用、模型调用、私有 Gold 读取、Secret 读取、外部 release upload 均为 0；运行时部署和真实账号
执行均为 `NOT_RUN`。匿名 OSV 仅查询公开依赖版本，不使用共享认证材料。不存在 Alpha、Beta、固定 30 日健康观察
或 soak；直接 MVP deploy/run/online smoke 只属于 `TSK.x2n.assurance.005`。

回滚只需 revert 本 Task 的 source/evidence commits；本 Run 不创建真实 Runtime、平台或 Owner 数据状态。
