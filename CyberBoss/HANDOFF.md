# CyberBoss HANDOFF

- Updated: 2026-07-26
- Repository: `LinzeColin/MetaDatabase`
- Worktree:
  `/Users/linzezhang/Documents/Codex/GithubProject/_scratch/metadatabase-cyberboss`
- Local branch: `codex/cyberboss-prestage0`
- Base: `origin/main@4c207ad539754166fae6642ff4e6850438d3e2fc`
- Remote publication: none

## Current state

`PS0.1` and `P0.1 / CB-000` passed. `CB-000` is the only completed TaskPack
task; the other 29 tasks and PG-0–PG-5 remain `not_started`.

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

## Known unknowns

- No real authenticated Codex turn, WeChat account/API, OVH host, Status
  ingestion, Private-Database, R2, OCI, DNS/Access or deployment was tested or
  activated in CB-000.
- The protocol baseline proves schema compatibility and unit behavior, not a
  production Runtime activation.
- OVH capacity, current ports/processes/filesystems and existing Status
  contract remain unmeasured until CB-010 has authorized read-only access.

## Next Run

Execute exactly one phase: `P0.2 / CB-010`.

Required outcome: collect redacted read-only OVH resource/port/process/storage
evidence, inspect the existing Status contract, select a safe capacity profile
and prove proposed paths/ports do not conflict. Use three immediate snapshots
and one induced-load fixture; do not use a real-time waiting window.

Stop before mutating unrelated services, requiring unsafe cleanup, exposing
credentials/data, or choosing a profile that can harm an existing critical
service. If live access is unavailable, keep only that evidence
`activation_pending`; do not fabricate measurements. Do not start `P0.3`,
push, create a PR/tag or deploy in that Run.
