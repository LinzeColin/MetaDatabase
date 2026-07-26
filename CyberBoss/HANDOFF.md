# CyberBoss HANDOFF

- Updated: 2026-07-26
- Repository: `LinzeColin/MetaDatabase`
- Worktree:
  `/Users/linzezhang/Documents/Codex/GithubProject/_scratch/metadatabase-cyberboss`
- Local branch: `codex/cyberboss-prestage0`
- Base: `origin/main@4c207ad539754166fae6642ff4e6850438d3e2fc`
- Remote publication: none

## Current state

`PS0.1` and `P0.1 / CB-000` passed. `P0.2 / CB-010` has completed all
repository-local and public read-only work but is `activation_pending` because
no explicitly authorized OVH target was discoverable. The later 28 tasks and
PG-0–PG-5 remain `not_started`.

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
- Resource profile tests: 6/6 passed; safe outputs are sourceable/mode-bounded
  and unsafe writer fails closed.
- Clean-shell preflight contract: three immediate snapshots, no live command,
  no persistent host write and no real-time wait.
- Bounded local-container pressure ladder: recover → warn/protect → recover,
  finite cgroup limit and zero observed OOM-kill delta. It is explicitly not
  live OVH evidence.
- Existing public Status contract: both read-only endpoints returned 200;
  current `projects[]` has 11 required fields, 8 rows and zero CyberBoss rows.
  Status adapter contract tests: 7/7 passed, including hostile-field
  sanitization.
- `validate_cb010.py`: repository-local result passes with
  `task_state=activation_pending` after the final validation run.

## Known unknowns

- No real authenticated Codex turn, WeChat account/API, OVH host, Status
  ingestion, Private-Database, R2, OCI, DNS/Access or deployment was tested or
  activated in CB-000.
- The protocol baseline proves schema compatibility and unit behavior, not a
  production Runtime activation.
- The public Status row contract is measured, but OVH total/available memory,
  swap, ports, processes, units, containers, filesystems/inodes, canonical-path
  conflicts and ingestion location remain unmeasured.
- A live `constrained`, `tiny` or `standard` choice must not be asserted until
  the same authorized host supplies its redacted preflight and bounded
  induced-load/cgroup snapshot.

## Next Run

Resume exactly one phase: `P0.2 / CB-010`.

Required inputs:

1. one explicitly authorized OVH SSH host alias; do not send or inspect
   secret/key contents, and do not infer the target from a public address;
2. a separate explicit decision on whether the bounded live fixture may allocate
   at most 16 MiB RAM and write/clean 8 MiB temporary disk after the read-only
   baseline proves it safe. The existing “read-only preparation” instruction
   does not grant that permission.

Required outcome: collect redacted read-only OVH resource/port/process/storage
evidence, select a safe capacity profile and prove proposed paths/ports do not
conflict. Use three immediate snapshots and one bounded induced-load/cgroup
snapshot; do not use a real-time waiting window.

Stop before mutating unrelated services, requiring unsafe cleanup, exposing
credentials/data, or choosing a profile that can harm an existing critical
service. If live access remains unavailable, keep CB-010
`activation_pending`; do not fabricate measurements. Do not start `P0.3`,
push, create a PR/tag or deploy.
