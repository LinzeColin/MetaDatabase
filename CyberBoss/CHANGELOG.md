# Changelog

## P0.3 / CB-020 — 2026-07-26

- Locked the only code identity to `LinzeColin/MetaDatabase/CyberBoss`,
  workspace alias `cyberboss` and `CyberBoss/**`; no repository was created.
- Added a fail-closed wrapper around the shared no-clone
  `private_db_client.py`, allowing only `Private-MetaDatabase`,
  `domain=CyberBoss` and `ingest/get/list/verify`.
- Added value-free credential slots and exact-scope attestations for separate
  Cloudflare Access, DNS, R2 and OCI capabilities.
- Prepared idempotent Access-first/DNS-last Cloudflare activation and
  prefix-locked immutable OCI adapters, plus deterministic provider mocks.
- Verified anonymous/unauthorized Access denial, exact fixture allow,
  hostile-policy rejection and out-of-scope repo/path/area/domain/bucket/prefix
  rejection.
- Audited protected local Cloudflare/OCI records read-only. Real reads are
  proven, but exact least-privilege write scopes are not; no external mutation
  was made and those activations remain pending/hazard-blocked.
- Scanned the complete CyberBoss tree against seven protected known-secret
  values without emitting them; known/pattern hits and P0/P1 findings are zero.
- Revalidated Corresponding Source, original licenses/notices, 129 dependency
  entries and the unresolved strict GPLv3+AGPLv3 conflict record.
- Marked CB-020 `passed`; CB-030 and every later task/gate remain unstarted.

## P0.2 / CB-010 — 2026-07-26

- Added a fail-closed `constrained`/`tiny`/`standard` resource calculator with
  dynamic memory reserve, disk caps and protect/recover predicates.
- Rebuilt the read-only preflight around three immediate redacted snapshots and
  added a deterministic clean-shell `--check`.
- Added a bounded memory/disk/queue pressure fixture and captured local
  finite-cgroup evidence with zero observed OOM-kill delta; it is explicitly
  not claimed as OVH evidence.
- Observed the public Status page/snapshot read-only and aligned the adapter
  fixture to its current 11-field `projects[]` contract.
- Added executable Python/Node contract suites and CB-010 validation.
- Made live measurement cgroup-v2-aware so a finite container/service memory
  ceiling cannot be mistaken for larger host `/proc` capacity; verified the
  default Linux collector in a no-network, read-only local container.
- Resolved the authorized primary OVH asset from protected local deployment
  records under the Owner's explicit instruction, using strict known-host and
  key-only SSH without persisting its address or credential material.
- Captured three same-host immediate snapshots and selected the safe
  `constrained` profile; verified 8765/8780, four proposed paths, existing
  Status ingestion and Traefik integration without online mutation.
- Ran the exact 16 MiB memory / 8 MiB temporary disk / 100-item pressure
  fixture in an ephemeral no-network, read-only 128 MiB cgroup; all guard
  transitions passed and OOM-kill delta was zero.
- Marked CB-010 `passed`; CB-020 and every later task/gate remain unstarted.

## P0.1 / CB-000 — 2026-07-26

- Imported exact ordinary-file source bundles for CyberBoss,
  timeline-for-agent and whereabouts-mcp with deterministic manifests.
- Replaced moving Git dependencies with reproducible local `file:` packages.
- Recorded the whereabouts AGPL/GPL conflict and Owner-approved strict
  dual-obligation treatment without claiming upstream clarification.
- Added the complete dependency/license inventory and Corresponding Source map.
- Verified the existing Timeline CLI/tools; no second Timeline kernel was added.
- Aligned stale Codex RPC fields with CLI `0.146.0-alpha.3.1` generated schemas.
- Removed author-machine absolute paths from sticker test fixtures.
- Corrected AC-032 evidence wording to Private-MetaDatabase manifest semantics
  without changing any Requirement, Oracle, Task or Stage.

## v0.0.0.4 — 2026-07-26

- Registered CyberBoss as an AGPL-3.0-only subtree of
  `LinzeColin/MetaDatabase`.
- Replaced the forbidden independent repository model with the B1 monorepo
  workspace boundary.
- Replaced the source pack's `Private-AgentDatabase/...` path and
  Private-Database clone semantics with
  `Private-MetaDatabase`, `domain=CyberBoss`, and the no-clone client protocol.
- Defined fixed-source import with no continuing upstream technical relation.
- Added one-phase-per-Run and final-only GitHub publication rules.
- Corrected invalid Task/Pass-Gate references and added stronger validators.

The product scope, Stage 0–5 DAG cardinality, acceptance IDs and no-real-time-
soak policy remain unchanged from the supplied v0.0.0.3 baseline.
