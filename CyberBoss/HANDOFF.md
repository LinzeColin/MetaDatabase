# CyberBoss HANDOFF

- Updated: 2026-07-26
- Repository: `LinzeColin/MetaDatabase`
- Worktree:
  `/Users/linzezhang/Documents/Codex/GithubProject/_scratch/metadatabase-cyberboss`
- Local branch: `codex/cyberboss-prestage0`
- Base: `origin/main@4c207ad539754166fae6642ff4e6850438d3e2fc`
- Remote publication: none

## Current state

`PS0.1`, `P0.1 / CB-000` and `P0.2 / CB-010` passed. The Owner directed
CB-010 to resolve OVH access from existing local deployment records. A unique
primary asset, strict known-host identity and key-only deployment identity were
verified without persisting its address or credential material.

Three same-host immediate snapshots selected `constrained`, guard=`recover`,
activation-safe=`true`; 8765/8780 and all four proposed CyberBoss paths are
free. Existing Status ingestion/Traefik integration was confirmed read-only.
The authorized-host 16 MiB/8 MiB/100 fixture passed in a finite 128 MiB
ephemeral container with zero OOM-kill delta and complete cleanup. The later
28 tasks and PG-0–PG-5 remain `not_started`.

The exact CyberBoss, timeline-for-agent and whereabouts-mcp sources are frozen
as ordinary-file bundles under `app/` and `vendor/`. Both moving Git
dependencies are local `file:` packages. There is no upstream remote,
submodule, branch dependency, automatic sync, periodic rebase or runtime
source fetch.

The whereabouts package metadata says AGPL-3.0-only while its included LICENSE
is GPL-3.0-only. Owner decision is strict
`GPL-3.0-only AND AGPL-3.0-only` compliance: preserve the original source,
license and conflict record. No upstream clarification was requested or
received, and none may be claimed.

## Canonical inputs and decisions

- Product design:
  `docs/product_design/v0.0.0.4/`
- Execution DAG:
  `docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml`
- Owner decisions:
  `machine/facts/owner_decisions.json`
- Task state:
  `machine/facts/task_state.json`
- Fixed-source lock:
  `machine/source-lock.json`
- CB-000 evidence:
  `docs/evidence/CB-000/`
- CB-010 evidence:
  `docs/evidence/CB-010/`
- Current Run Contract:
  `docs/governance/RUN_CONTRACT_P0_2_CB_010.md`
- Provenance:
  `UPSTREAM_PROVENANCE.md` and `THIRD_PARTY_NOTICES.md`
- PS0.1 evidence:
  `docs/product_design/v0.0.0.4/implementation-kit/VALIDATION_REPORT.md`

## Validation result

- Three source commit/tree identities, source manifests and current bundle
  manifests: passed.
- Dependency closure: 129 lockfile entries, zero unresolved licenses, no Git
  URL/branch dependency, `npm ci --ignore-scripts` passed.
- Application syntax and tests: 155/155 passed.
- timeline-for-agent syntax/tests: 5/5; `help`, `categories`, `read` callable.
- whereabouts-mcp syntax/tests: 19/19 passed.
- Codex App Server generated protocol schemas: 347 files, every required
  method present; exact/minimum verified CLI `0.146.0-alpha.3.1`.
- TaskPack/DAG/traceability/no-wait/config and accelerated
  1,000/100/100/20 reliability checks: passed.
- `validate_cb000.py`, `validate_prestage0.py`, manifests, final Git scope and
  publication checks: passed.
- Resource profile tests: 7/7 passed; finite cgroup ceilings override misleading
  host `/proc` values, safe outputs are sourceable/mode-bounded and unsafe
  writer fails closed.
- Clean-shell preflight contract: three immediate snapshots, no live command,
  no persistent host write and no real-time wait.
- Default Linux collector path: passed in an existing local image with
  `--pull=never`, no network, read-only root, all capabilities dropped and
  no-new-privileges. A finite 512 MiB cgroup correctly yields
  `constrained`/`protect`/`HAZARD_BLOCKED`; raw output is not persisted and the
  result is explicitly not OVH evidence.
- Bounded local-container pressure ladder: recover → warn/protect → recover,
  finite cgroup limit and zero observed OOM-kill delta. It is explicitly not
  live OVH evidence.
- Existing public Status contract: both read-only endpoints returned 200;
  current `projects[]` has 11 required fields, 8 rows and zero CyberBoss rows.
  Status adapter contract tests: 7/7 passed, including hostile-field
  sanitization.
- Authorized OVH preflight: strict known-host/key-only authentication; three
  snapshots in under one second; 3819 MiB total and 1948–1955 MiB available
  memory, 1095 MiB swap free, 15,558 MiB root free, low inode use.
- Live selection: `constrained`, MemoryHigh 768 MiB, MemoryMax 1152 MiB,
  TasksMax 256, memory reserve 512 MiB, disk reserve 4 GiB, guard recover.
- Conflict/integration inventory: 8765/8780 free, four proposed paths absent,
  21 existing containers; Status compose/collector/data/web, mounts, cron,
  fresh snapshot and Traefik route counts confirmed without raw-row retention.
- Authorized bounded pressure: existing image, no pull/network, read-only
  rootfs, non-root, 128 MiB memory/swap, 32 PID, 0.25 CPU; exact
  16 MiB/8 MiB/100 fixture, full guard ladder, zero OOM-kill delta, cleanup.
- `validate_cb010.py`: strengthened to validate live evidence semantics rather
  than file presence; final result passes with `task_state=passed`.

## Known unknowns

- No real authenticated Codex turn, WeChat account/API, Private-MetaDatabase
  data operation, R2, OCI, DNS/Access route or CyberBoss deployment has been
  tested or activated.
- The protocol baseline proves schema compatibility and unit behavior, not a
  production Runtime activation.
- The measured `constrained` baseline is point-in-time. Activation must rerun
  preflight and fail closed if guard/reserve changes.
- Node, Codex, rclone and sqlite3 are not currently available on the target;
  these are later deployment prerequisites, not CB-010 capacity failures.
- The online Status surface still has no CyberBoss row; CB-010 made no online
  mutation.

## Next Run

Start exactly one phase: `P0.3 / CB-020`.

Before modifying files, create
`docs/governance/RUN_CONTRACT_P0_3_CB_020.md` from the canonical DAG and read
AC-043/AC-065. Keep P0.2 evidence immutable.

Required outcome:

1. lock `LinzeColin/MetaDatabase` + `CyberBoss/` + workspace alias
   `cyberboss`, with no new/forked repository;
2. enforce `Private-MetaDatabase`, `domain=CyberBoss`, no-clone access through
   `private_db_client.py`, including negative scope tests;
3. add least-privilege credential *slots* and a secret inventory without real
   values in the repository;
4. prepare idempotent DNS/Access/Analytics/R2 and OCI activation adapters plus
   mock endpoints;
5. prove anonymous/unauthorized Access denial and out-of-scope
   repo/path/domain/bucket rejection;
6. run secret scanning and keep unavailable external activations precisely
   `activation_pending` without blocking dependency-independent work.

Stop on broad account-level write credentials, anonymous management exposure,
secret leakage or any attempt to clone Private-Database/create another repo.
Do not execute P0.4, push, create a PR/tag/release or deploy a CyberBoss
Runtime in the P0.3 Run.
