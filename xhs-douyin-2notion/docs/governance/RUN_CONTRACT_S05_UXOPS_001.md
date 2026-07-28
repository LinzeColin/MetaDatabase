# Stage 5 Task001 Run Contract — Notion Projection Hardening

## Identity

- Task: `TSK.x2n.uxops.001`
- Phase: `PH.X2N.5.1`
- Run: `RUN-X2N-S05-U001`
- Acceptance: `ACC.x2n.notion.001`–`.004`

## Scope

本 Run 只加固可重建的 Notion 投影：版本化且只加法的 Items/Categories schema plan、严格长文本分块（首批创建、后续 append 都最多 100 block）、每秒最多两次的串行请求闸门、Outbox/Dead Letter/kill 后 reconcile，以及 14 个 x2n 自有的 Items/Categories View 定义。

View 定义遵循当前 Notion API `2026-03-11` 的 Database + Data Source 双身份模型，但本 Run 只使用不打开 socket 的进程内 Mock。真实 Notion transport、凭据、Workspace、Page、数据库身份、Owner Canary 与网络请求均为 `NOT_RUN`。真实 View API 不可用或无权限时返回 `FALLBACK_DOCUMENTED`，不会伪称创建成功；同名而配置不同的 x2n View 一律冲突停机，不覆盖 Owner 视图。

## Non-goals

- 不写真实 Notion，不读取或修改任何认证材料；
- 不执行 Markdown Task、Review/Diagnostics Task、Data Lifecycle Task、Stage 5 Gate、上传、部署或发布；
- 不持久化平台媒体 CDN URL、原始媒体、Cookie、Profile 或本机绝对路径；
- 不改变 Canonical 的 SQLite 事实地位，Notion 仍是可重建 Sink。

## Acceptance and stop conditions

- 同一 `content_key` 只保留一个 Page；schema 只允许加法，用户字段不删除或覆盖；
- 长文本每段不超过 2,000 字符、每请求最多 100 个 block，超出总量/字节上限 Fail Closed；
- 429/529 的 Retry-After、超时/重置、最大四次、Dead Letter、Outage、成功回包后 receipt 前 kill 均需通过；
- View 覆盖 Default Table、Category Gallery、Likes、Favorites、Review、Processing Failed、六个平台、Recent 与 Categories directory；共 14 个精确定义，重复执行无远端副作用；冲突时 Fail Closed、不可用时明确 fallback；
- 任一真实 transport、用户字段覆盖、重复 Page、无界 retry、媒体/CDN 持久化或证据不完整均停止，并以 `notion_sink=false` 保持回滚路径。

## Validation

```bash
.venv/bin/python -B scripts/verify_stage_4_review.py --verify-worktree --run-acceptance --require-evidence
.venv/bin/python -B scripts/run_uxops_001_acceptance.py
.venv/bin/python -B scripts/verify_uxops_001.py --verify-worktree --run-acceptance --require-evidence
PYTHONPATH=apps/companion/src:packages/contracts/src .venv/bin/python -B -m unittest apps.companion.tests.test_sinks
```

Task 完成只授权下一单本地 `TSK.x2n.uxops.002`；不授权 G5、真实 Notion、上传、部署或发布。
