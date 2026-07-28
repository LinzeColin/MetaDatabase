# Stage 6 Assurance001 Run Contract

## Identity

- Task: TSK.x2n.assurance.001
- Phase: PH.X2N.6.1
- Run: RUN-X2N-S06-A001
- Base: G5 final source 34fac27299e1b5599b78456ee825814f456f2df7

## Single-task scope

本 Run 只完成软件正确性 pipeline：当前源码 format/lint/type/unit/contract/migration/integration/browser
E2E、风险覆盖、关键不变量 mutation、fresh-copy Skill lifecycle，以及跨层 idempotency。

G5 的历史控制面只在固定 Base 的 disposable Git checkout 中重放。历史 verifier 不读取当前 Stage 6
树；当前源码也不以历史 Stage 5 的 current-tree 静态范围作为通过条件。

## Acceptance mapping

| Acceptance | 可复现的 CI-synth 证据 |
|---|---|
| ACC.x2n.rel.001 | format/lint/compile/TypeScript/Companion/Contract/browser E2E/coverage/source scan，blocking failure、skip、flaky 均为 0 |
| ACC.x2n.data.002 | 80 条输入连续两轮与 100 并发重复；Content、Relation、Artifact、Markdown、Notion Mock、Outbox/Receipt 的重复为 0 |
| ACC.x2n.data.004 | 10,000-item migration/backup/rollback、tombstone epoch 与 verified-backup guard；data loss、unreadable record、无备份 destructive migration 均为 0 |
| ACC.x2n.rel.008 | 隔离 fresh copy 的七个 source lifecycle rehearsal；install/Canary/upgrade/rollback/uninstall 均 Fail Closed，runtime write 为 0 |

两个独立 mutation 必须被对应回归测试杀死：Request Ledger replay disposition 与 migration
verified-backup guard。任一 mutant 存活即失败。

## Boundary and stop conditions

本 Run 不执行部署、运行、上线、真实 Canary、Owner Chrome/Profile、真实账号、平台、真实 Notion、
模型、真实媒体、Private-Database client、tmutil 或物理删除。外部网络和平台调用均为 0。

任一 blocking test skipped/flaky/failed、traceability gap、source/privacy scan finding、mutation survivor、
fresh-copy runtime write、历史 replay 非固定提交，或证据包含本机路径、凭据、平台媒体 CDN URL 时，
全部 Fail Closed。

不存在 Alpha、Beta、固定 30 日健康观察或 soak。实际 MVP deploy/run/online smoke 只属于最终
TSK.x2n.assurance.005；本 Task 完成后只授权下一独立 Task TSK.x2n.assurance.002。

## Rollback

revert 本 Task 的 source/evidence commits 即回到 G5 的冻结 Stage 6 entry state。当前 Run 不写真实
Runtime 或外部系统，因此没有外部状态需要回滚。
