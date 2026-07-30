---
name: xhs-douyin-2notion
description: >-
  Govern development and the public-source lifecycle rehearsal of the local-first
  x2n personal-content knowledge system. Use only for the current single DAG Task
  and its Acceptance while preserving Public Code / Private Runtime boundaries.
---

# xhs-douyin-2notion

Operate only inside `LinzeColin/MetaDatabase/xhs-douyin-2notion/`. This Skill
does not authorize a generic crawler, real-account access, platform calls,
Notion writes, model calls, media handling, deployment, or mutation of another
project.

## Permanent boundaries

- Treat local SQLite as the future canonical truth; Markdown and Notion remain
  rebuildable sinks.
- Keep `X2N_DATA_ROOT` outside Git. Never print or persist its resolved local
  path in public evidence.
- Never persist credentials, browser state, platform media CDN URLs, or raw
  media.
- Never auto-scroll, change account state, bypass platform controls, or let AI
  create a first-level category.
- Keep platform capability execution disabled until its own Policy/Auth/
  Technical/Canary gate passes.
- Execute at most one Task and its Acceptance per ordinary Run. Do not push an
  intermediate Stage branch before its Stage Review passes.

## Current capability: Stage 6 Assurance001 public-source rehearsal

The commands below are copyable in a clean source checkout. They validate the
current public source, frozen locks, minimal MV3 permission boundary, and
failure protocol. They do not install a released product, resolve an Owner
runtime path, create persistent data, invoke a real Canary, or contact a
platform.

Run from the project root with the project environment available:

```bash
PYTHONPATH=apps/companion/src:packages/contracts/src python3.12 -B -m x2n_companion.skill_lifecycle install
PYTHONPATH=apps/companion/src:packages/contracts/src python3.12 -B -m x2n_companion.skill_lifecycle self-test
PYTHONPATH=apps/companion/src:packages/contracts/src python3.12 -B -m x2n_companion.skill_lifecycle canary --synthetic
PYTHONPATH=apps/companion/src:packages/contracts/src python3.12 -B -m x2n_companion.skill_lifecycle upgrade --dry-run
PYTHONPATH=apps/companion/src:packages/contracts/src python3.12 -B -m x2n_companion.skill_lifecycle rollback --dry-run
PYTHONPATH=apps/companion/src:packages/contracts/src python3.12 -B -m x2n_companion.skill_lifecycle diagnose
PYTHONPATH=apps/companion/src:packages/contracts/src python3.12 -B -m x2n_companion.skill_lifecycle uninstall --dry-run --retain-data
```

The governed offline Assurance001 acceptance replays those commands from a
fresh temporary copy together with the current Companion, Contract, browser
E2E, migration, idempotency, coverage, and historical-evidence checks:

```bash
.venv/bin/python -B scripts/run_assurance_001_acceptance.py
.venv/bin/python -B scripts/verify_assurance_001.py --verify-worktree --allow-external-main-dirty --run-acceptance --require-evidence
```

`install` is a source-install rehearsal with zero writes. `canary` requires
`--synthetic`; `upgrade` and `rollback` require `--dry-run`; `uninstall`
requires both `--dry-run` and `--retain-data`. All failure output contains one
stable code, a safe message, and one minimum decision question. No command
requires undeclared authorization or secret input.

## Release boundary

There is no Alpha, Beta, fixed 30-day observation, or soak gate. Direct
MVP deploy/run/online smoke remains exclusively within
`TSK.x2n.assurance.005`; it is not authorized by this Skill or by
Assurance001. Until then, Owner Chrome/Profile, real platform behavior, real
Notion, Private-Database transfer, real media, model execution, deployment,
and release are all `NOT_RUN`.

## Failure protocol

Fail Closed on an unknown policy, safety, evidence, acceptance, recovery, or
rollback gate. Do not infer missing authorization from a tool being installed.
Do not disclose a local path, credential value, another project name, or private
content while diagnosing.
