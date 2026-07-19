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

## Current capability: Stage 1 scaffold only

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
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

## Failure protocol

Every scaffold command uses Fail Closed behavior with a stable code, a safe message, and
one minimum decision question. Do not infer missing authorization from a tool
being installed. Do not disclose a local path, credential value, other project
name, or private content while diagnosing.

## Lifecycle semantics

- `install`: validates the source scaffold and required local tools; writes
  nothing.
- `canary --synthetic`: validates only the registered synthetic fixture.
- `upgrade --dry-run` and `rollback --dry-run`: rehearse source-layout checks;
  no version or data changes occur.
- `diagnose`: reports capability booleans and stable codes, never paths or
  secrets.
- `uninstall --dry-run --retain-data`: documents the future safe default. It
  removes nothing and preserves all data.

Real install, real Canary, migration, rollback, diagnostics bundle, uninstall,
and data-retention behavior remain `DOWNSTREAM_NOT_RUN` and must not be
reported as PASS until their own Tasks and Acceptance run.
