# Changelog

## PG-0 — 2026-07-26

- Independently passed the Stage 0 exit Gate without requiring any real
  credential, provider write, deployment or GitHub publication.
- Added a fail-closed PG-0 validator that freezes the P0.5 closure commit and
  rejects changes to App, vendor bundles, TaskPack or historical Stage 0
  evidence.
- Ran 22 repository-preparation checks with seven credential-related
  environment keys removed, a temporary HOME, empty CODEX_HOME/WeChat state,
  isolated npm cache and value-free Git/npm configuration.
- Revalidated exact fixed sources, original licenses/notices/Corresponding
  Source, all 129 dependency entries, the module map and unresolved strict
  `GPL-3.0-only AND AGPL-3.0-only` obligations without claiming upstream
  clarification.
- Revalidated current architecture/substitutions/Feature Flags with zero
  unresolved conflicts, 4/4 simulator tests, 155/155 App tests,
  preflight/resource fixtures, activation sheet and clean missing-auth states.
- Revalidated DAG 30/6, traceability 53/53, no-wait zero hits and TaskPack 81
  files; credential values, P0/P1 secret findings and external writes were
  zero.
- Extended the Prestage validator to model a current Pass Gate fail-closed
  while preserving all existing task/phase/dependency checks.
- Marked only `PG-0` passed. `P1.1 / CB-100`, all 25 later tasks and PG-1–PG-5
  remain `not_started`; remote CyberBoss branch/PR/tag state remains empty.

## P0.5 / CB-040 — 2026-07-26

- Froze one value-free implementation baseline for the MetaDatabase/CyberBoss
  repository, OVH paths/services/ports, workspace, Private-MetaDatabase
  no-clone identity, Cloudflare domain and R2/OCI bucket-prefix boundaries.
- Resolved nine stale Feature Flag aliases/non-runtime switches by aligning
  four product documents to the exact validated implementation-kit names;
  defaults, Acceptance, Task DAG and source code were unchanged.
- Preserved the AGPL-3.0-only subtree and strict
  `GPL-3.0-only AND AGPL-3.0-only` whereabouts obligations, original source/
  licenses/conflict record and `upstream_clarification_received=false`.
- Mapped all 25 remaining tasks to exact existing/planned modules, tests,
  Acceptance criteria, evidence directories and immutable release artifacts
  without starting S1 implementation.
- Deterministically sampled 10 of 53 requirements from the P0.4 commit SHA;
  all ten locate Requirement → Acceptance → Task → Test → Evidence → Release.
- Recorded local baseline commit
  `8a75b55e92071bb33f1cae5872feca55ade1c858`, its parent/tree/path inventory
  and direct evidence that no CyberBoss remote branch, open PR or tag exists.
- Revalidated CB-000, Prestage, manifests, scope/config, DAG, traceability,
  no-wait, adapters, simulators, resource/SQLite reliability and all 155 App
  tests. Unresolved Canonical Facts conflicts and remote writes are zero.
- Marked CB-040 `passed` with decision `GO_TO_PG-0`; PG-0, all later tasks,
  push/PR/tag/release/deployment and real provider activation remain unstarted.

## P0.4 / CB-030 — 2026-07-26

- Ran the supplied WeChat simulator successfully and reproduced the supplied
  Codex simulator's clean-location `ERR_MODULE_NOT_FOUND` failure for its
  already-locked `ws` dependency.
- Reused that exact local dependency and extended only TaskPack/pinned-protocol
  gaps; no package, upstream fetch, remote or runtime source dependency was
  added.
- Added deterministic WeChat QR/login, empty/reverse/cursor/replay, duplicate
  update/ack, 401/403/429/500/503/timeout/reset and unknown-outcome fixtures.
- Added Codex initialize gate, thread/turn/progress, approval, retryable/
  terminal failure, interrupt, exact bounded-queue overload, crash/reconnect,
  false-success and late/duplicate-event fixtures with artifact SHA-256 Oracles.
- Made both simulators reject non-loopback binds and added one 4-test contract
  suite; all four simulator tests and all 155 frozen App tests passed.
- Probed local and authorized OVH auth state read-only without reading or
  persisting values. Local Codex is pinned/authenticated; OVH has no Codex CLI,
  Codex auth file or WeChat state, so target adapters remain
  `activation_pending`.
- Added one consolidated device-auth/QR/protection/re-login sheet and a
  1280×720 PNG explicitly labelled as a non-real WeChat fixture.
- Revalidated source/license/NOTICE/dependency evidence and scanned against
  seven protected known-secret values with zero hits/P0/P1 findings.
- Corrected literal-backslash word boundaries in the existing secret scanner
  and added independent hostile fixtures for all seven pattern families,
  closing token/JWT/Bearer/WeChat false-negative paths.
- Marked CB-030 `passed`; CB-040 and every later task/gate remain unstarted.

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
