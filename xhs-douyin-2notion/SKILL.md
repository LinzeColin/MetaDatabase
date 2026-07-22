---
name: xhs-douyin-2notion
description: >-
  Govern development and operation of the local-first x2n personal-content
  knowledge system. Use for x2n scaffold checks, later installation,
  diagnostics, Canary, upgrade, rollback, and removal while preserving the
  Public Code / Private Runtime and one-DAG-Task-per-run gates.
---

# xhs-douyin-2notion

Operate only inside `LinzeColin/MetaDatabase/xhs-douyin-2notion/`. This Skill
does not authorize a generic crawler, real-account access, platform calls,
Notion writes, model calls, media handling, or mutation of another project.

## Permanent boundaries

- Treat local SQLite as the future canonical truth; Markdown and Notion remain
  rebuildable sinks.
- Keep `X2N_DATA_ROOT` outside Git. Never print or persist its resolved local
  path in public evidence.
- Never persist credentials, browser state, platform media CDN URLs, or raw
  media.
- Never auto-scroll, change account state, bypass platform controls, or let AI
  create a first-level category.
- Keep all six platform capabilities disabled until their independent gates
  pass.
- Execute at most one Task and its Acceptance per ordinary Run. Do not push an
  intermediate Stage branch before its Stage Review passes.

## Current capability: Stage 1 foundation + Stage 2 Canonical and sink skeleton

Run these commands from the project root. They perform deterministic,
network-free scaffold rehearsals; they do not install a released product or
touch Private Runtime.

```bash
PYTHONPATH=apps/companion/src python3.12 -B -m x2n_companion.scaffold install
PYTHONPATH=apps/companion/src python3.12 -B -m x2n_companion.scaffold self-test
PYTHONPATH=apps/companion/src python3.12 -B -m x2n_companion.scaffold canary --synthetic
PYTHONPATH=apps/companion/src python3.12 -B -m x2n_companion.scaffold upgrade --dry-run
PYTHONPATH=apps/companion/src python3.12 -B -m x2n_companion.scaffold rollback --dry-run
PYTHONPATH=apps/companion/src python3.12 -B -m x2n_companion.scaffold diagnose
PYTHONPATH=apps/companion/src python3.12 -B -m x2n_companion.scaffold uninstall --dry-run --retain-data
```

Verify frozen workspaces and the governed fresh-copy transcript with:

```bash
python3.12 -B scripts/verify_foundation_001.py --verify-worktree --allow-external-main-dirty
python3.12 -B scripts/verify_foundation_002.py --verify-worktree --allow-external-main-dirty
python3.12 -B scripts/verify_foundation_003.py --verify-worktree --allow-external-main-dirty
python3 -B scripts/verify_foundation_004.py --verify-worktree --allow-external-main-dirty --require-evidence
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

Foundation.002 的历史范围仍只证明 `1.0` Contract。Foundation.003 已新增仓库外
Private Runtime、SQLite Schema v2、Migration、Request Ledger、Outbox/Lease 与本地
Backup/Restore。Foundation.004 已实现固定开发 ID 的 MV3 Side Panel、短进程 Native
Host 与 SQLite 状态重连；六平台已在公共合成当前页中通过。`capture_current` 现在只把
净化事实送入 Schema v2 两事务 Canonical walking path，形成 Run、Observation、Content、
Owner-confirmed `saved_current` Relation、Checkpoint 与无私有 payload 的 placeholder Artifact。
80×2、100 并发重复和 4 个 kill point 可重放；仍不连接平台。Skeleton005 进一步把 Canonical
snapshot 投影为固定 `platform/content_id` 路径的原子 Markdown，并通过 SQLite Outbox 驱动
进程内 Notion Mock 的加法式 Schema、upsert、限速、重试、Dead Letter 与 kill-reconcile。
`Unclassified` 只创建派生 Index，不创建 Taxonomy row；真实 Notion transport 与凭据访问不存在。

Skeleton005 验证只使用仓库内公共合成输入、临时 Runtime 与进程内 Mock：

```bash
.venv/bin/python -B scripts/run_skeleton_005_acceptance.py
.venv/bin/python -B scripts/verify_skeleton_005.py --verify-worktree --allow-external-main-dirty --skip-external
```

不要把 placeholder Artifact 当成真实 ASR/OCR/摘要，也不要把 Notion Mock 当成真实集成；分类、
真实多模态处理、真实 Notion、Owner Canary 与分类视图都是后续独立 Task/Gate。

Native Host installer 默认仅计划，输出不含路径：

```bash
X2N_DOWNLOAD_DESTINATION="$X2N_DOWNLOAD_DESTINATION" \
X2N_DATA_ROOT="$X2N_DATA_ROOT" \
PYTHONPATH=apps/companion/src:packages/contracts/src \
python3.12 -B -m x2n_companion.native_host_installer plan --browser chrome
```

Owner Chrome 安装和 Canary 尚未运行。不要把 E2E 的临时注册解释为 Owner 安装授权，
也不要在普通运维中执行 `install` 或 `uninstall --confirm`。

Store 命令只从显式环境变量解析唯一私有根，没有路径参数或默认目录：

```bash
export X2N_DOWNLOAD_DESTINATION="<owner-private-download-destination>"
export X2N_DATA_ROOT="${X2N_DOWNLOAD_DESTINATION}/xhs-douyin-2notion"
export PYTHONPATH="apps/companion/src:packages/contracts/src"

python3.12 -B -m x2n_companion.runtime_cli init
python3.12 -B -m x2n_companion.runtime_cli health
python3.12 -B -m x2n_companion.runtime_cli backup --label manual
python3.12 -B -m x2n_companion.runtime_cli recover
```

降级、恢复和 Recovery apply 都要求命令定义的显式确认值；Backup ID/Hash 来自私有
命令回执，不得复制到公共证据。当前同盘备份只证明本地恢复，不能称为异地灾备。

## Failure protocol

Every scaffold command uses Fail Closed behavior with a stable code, a safe message, and
one minimum decision question. Do not infer missing authorization from a tool
being installed. Do not disclose a local path, credential value, other project
name, or private content while diagnosing.

## Lifecycle semantics

- `install`: validates the source scaffold and required local tools; writes
  nothing.
- `canary --synthetic`: validates only the registered synthetic fixture.
- `upgrade --dry-run` and scaffold `rollback --dry-run`: still rehearse source layout only.
- Store migration/downgrade/restore: real Private Runtime operations with verified local backup,
  explicit confirmation, integrity checks, and no public path output.
- `diagnose`: reports capability booleans and stable codes, never paths or
  secrets.
- `uninstall --dry-run --retain-data`: documents the future safe default. It
  removes nothing and preserves all data.

Owner Native Host install/uninstall, real platform Canary, diagnostics bundle,
Markdown/Notion reconciliation and full data-retention behavior remain
`DOWNSTREAM_NOT_RUN` and must not be reported as PASS until their own Tasks run.
