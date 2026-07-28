# Stage 6 Assurance004 Run Contract

## Identity

- Task: `TSK.x2n.assurance.004`
- Phase: `PH.X2N.6.4`
- Run: `RUN-X2N-S06-A004`
- Base: `f69dd7a4f2fbc0a0d50063e3d2f2a2e64ec58f7e`

## Single-task scope

本 Run 只完成隔离的性能、压力、混沌与恢复 Campaign。它提供两个等价 Oracle：

```bash
.venv/bin/python -B scripts/run_assurance_004_acceptance.py chaos run --suite mvp
.venv/bin/python -B scripts/run_assurance_004_acceptance.py benchmark --suite mvp
```

两者只创建临时 `MediaCrawler/xhs-douyin-2notion` 根。浏览器 E2E 使用全新临时 HOME/Profile；如本机已有
Playwright 浏览器二进制缓存，只以显式只读依赖路径提供给 E2E，绝不复用 Owner Chrome Profile、Cookie 或
Runtime。命令结束后临时根被删除，公共回执不包含其路径、截图、trace、数据库或内容。

## Acceptance mapping

| Acceptance | 本 Run 的可复验证据 |
|---|---|
| `ACC.x2n.ext.002` | 隔离 Chromium 100 次 Service Worker 重启，lost/duplicate/wrong state/console error=0 |
| `ACC.x2n.xhs.003` | 100 条合成 XHS 点赞、50 次真实子进程 Kill、durable checkpoint、auto-scroll=0 |
| `ACC.x2n.media.002` | success/failure/kill/lock/permission/cleaner race cleanup，active misdelete=0；50 candidate cap、120-minute cap |
| `ACC.x2n.notion.002` | 进程内 Mock 429/529、Retry-After、2 req/s、retry storm=0 |
| `ACC.x2n.notion.003` | outage/receipt-before-kill/schema failures，Canonical/Markdown 存活且 duplicate Page=0 |
| `ACC.x2n.ops.001` | 十阶段 kill/recovery、control comparison、loss/duplicate/stuck=0 |
| `ACC.x2n.rel.004` | 20/80/1k/10k SQLite→Markdown rebuild、100 message burst、相对增长与 tracemalloc memory ceiling |
| `ACC.x2n.rel.005` | 六个核心破坏边界各 10 个独立 Seed；loss/duplicate/unauthorized delete/secret-or-CDN persistence=0 |

## Capacity rule

性能只报告本次本机的运行时测量，不能形成跨设备的统一耗时 SLO。10k/1k 相对增长超过 40 或 tracemalloc
峰值超过 512 MiB 即 Fail Closed；此上限只界定本 Campaign 的合成容量主张。`fsync` 由独立原子耐久性测试
覆盖，重建 benchmark 明确排除每文件设备 flush 延迟，避免把存储设备抖动伪装成算法复杂度。

## Stop conditions and rollback

无法隔离 Owner 数据、任何数据丢失/重复副作用/未授权删除、Secret/CDN 持久化、超出资源预算或恢复无法判定时，
本 Task 立即 Fail Closed。回滚为 revert 本 Task source/evidence commits；不修改真实 Runtime、Profile、平台、
Notion 或发布状态。

本 Run 不进行 Alpha、Beta、固定健康观察或 soak，也不部署、运行或上线。直接 MVP deploy/run/online smoke 仍只属于
下一独立 Task `TSK.x2n.assurance.005`。
