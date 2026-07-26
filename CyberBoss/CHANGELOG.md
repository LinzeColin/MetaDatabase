# Changelog

## P1.5 / CB-140 — 2026-07-27

- Bound the all-cloud Walking Skeleton and complete Corresponding Source to
  local implementation commit
  `571438751638a01c4648ff4fdf27403a97a971c3`; target check, two applies,
  independent verify and target App tests 175/175 passed.
- Added a pre-Runtime exact sender allowlist and UTF-8 byte gate. Unauthorized
  input and 32769 bytes caused zero Runtime calls; 32768 bytes caused exactly
  one.
- Correlated ten successful simulator E2E traces across inbound, Runtime,
  outbox, confirmed delivery and canonical event. Final redacted evidence has
  194 records, 34 trace IDs and no raw private-content or identity field.
- Passed 20/20 idle latency samples at P50 372 ms and P95 378 ms.
- Proved zero operational Mac source/config/process/connector dependency, zero
  non-loopback Runtime connection and three loopback-only listeners. Operator
  scans found 8765/8780/19080 externally unreachable three times each.
- Preserved the stale-manifest, locale, login-identity, SCP-permission,
  unsupported-CLI-field and browser-file-policy corrections with their exact
  no-mutation/cleanup outcomes.
- Produced a visibly simulator-labelled deterministic PNG evidence render;
  disclosed that browser security blocked direct local-file capture and that
  the PNG is not a browser capture or real WeChat evidence.
- Removed target staging, staging env and incoming artifacts after evidence
  retrieval. Left the exact candidate inactive, `current` on CB-100, workspace
  on CB-120 and service disabled/inactive with zero process/listener.
- Preserved original source/licenses and the unresolved strict
  `AGPL-3.0-only AND GPL-3.0-only` conflict record without claiming upstream
  clarification.
- Marked only CB-140 passed. PG-1, CB-200 and all later tasks/gates remain
  `not_started`; GitHub branch/PR/tag/release/publication remains empty.

## P1.4 / CB-130 — 2026-07-27

- Bound the loopback cloud process family and complete Corresponding Source to
  local implementation commit
  `81dc1ee211e554dd8b84001bfca4b8aa73bb89dd`; check, two applies,
  independent verify and target App tests 170/170 passed.
- Added one fixed non-shell supervisor for Runtime, channel and bridge under the
  existing `KillMode=control-group` unit, with no detached children and a
  single root-controlled lock owner.
- Added independent `/healthz`, `/readyz` and token-protected bounded status
  snapshot contracts; the forced-unready fixture remained healthy but not
  ready and could not fake green.
- Proved 8765/8780/19080 loopback-only listeners and operator-host
  unreachability for 8765/8780; final public and local listener counts are
  zero.
- Passed 100/100 concurrent systemd starts, 100/100 singleton-lock denials,
  100/100 real SIGKILL/restarts with complete cgroup-member replacement, and
  runtime/channel/bridge/service fault recovery 4/4.
- Preserved four non-passing transfer/install/acceptance attempts, including
  the Node 24 TAP-prefix parser correction and systemd 255
  `kill-whom=all` incompatibility, with exact cleanup outcomes.
- Left `current` on CB-100, workspace on CB-120, service disabled/inactive,
  transient drop-in/token/incoming counts at zero, and real Codex/WeChat
  activation at `activation_pending`.
- Preserved original source/licenses and the unresolved strict
  `AGPL-3.0-only AND GPL-3.0-only` conflict record without claiming upstream
  clarification.
- Marked only CB-130 passed. CB-140, all later tasks and PG-1–PG-5 remain
  `not_started`; GitHub branch/PR/tag/release/publication remains empty.

## P1.3 / CB-120 — 2026-07-26

- Bound complete Corresponding Source, a no-external-fetch partial repository
  seed, the canonical no-clone client and GitHub CLI `2.96.0` to local commit
  `10d988e908d72ea1a43bbed04a2130a338663363`.
- Installed one root-controlled `cyberboss` registry and exact sparse
  workspace with `.github`/`CyberBoss`, `blob:none`, a local immutable seed
  remote, clean status and no object hardlinks.
- Added code/data OS identity separation: code cannot read/execute the data
  client, data cannot modify the workspace, credential state remains absent,
  and the wrapper passed plan-only with no Private-Database clone/operation.
- Replaced the macOS-only sticker conversion path with a bounded,
  dependency-free Linux PNG-to-GIF implementation; the full target App suite
  passed 166/166.
- Passed installer check, two exact-commit applies, independent verify, 9/9
  target workspace/Runtime-boundary tests and live `recover` budget checks.
- Passed the bounded 128 MiB target cgroup pressure fixture with 16 MiB
  memory, 8 MiB disk, 100 queue items, no fixed sleep and zero OOM events.
- Preserved six superseded implementation/acceptance outcomes and the final
  pressure-created Python cache correction. Only the two verified transient
  cache entries were deleted; no source file was removed.
- Kept `current` on CB-100, service disabled/inactive, business process and
  8765/8780 listener counts at zero, and provider/data writes at zero.
- Preserved original source/licenses and the unresolved strict
  `AGPL-3.0-only AND GPL-3.0-only` conflict record without claiming upstream
  clarification.
- Marked only CB-120 passed. CB-130, all later tasks and PG-1–PG-5 remain
  `not_started`; GitHub branch/PR/tag/release/publication remains empty.

## P1.2 / CB-110 — 2026-07-26

- Pinned Node.js `24.18.0`, Codex CLI `0.146.0-alpha.3.1` and all three
  official archive SHA-256 values in one machine-readable runtime spec.
- Installed both tools into immutable project-local paths without npm
  lifecycle scripts, `/usr/local` writes, Git dependencies or global
  Node/Codex replacement; two applies and an independent verify passed.
- Created `/var/lib/cyberboss/.codex` as `0700 cyberboss:cyberboss`, prepared
  the device-auth command but did not execute it, and retained accurate target
  auth state `activation_pending` without reading credential content.
- Passed Node `node:sqlite` create/insert/select and Codex App Server
  `/readyz`, `initialize` and `initialized` against the real installed CLI.
- Proved the active 8765 listener was exactly `127.0.0.1:8765` and externally
  unreachable; final listeners, App Server processes and staging artifacts
  were zero, with the main service still disabled/inactive.
- Left Claude Code binary and credential absent; added a fail-closed controlled
  startup gate requiring both feature and eval flags, and passed all three
  negative combinations without starting the adapter.
- Preserved the initial hold-marker timeout and the subsequent protected-
  staging export failure before the final complete acceptance rerun passed.
- Kept fixed App/vendor source, original licenses and strict
  `GPL-3.0-only AND AGPL-3.0-only` conflict record unchanged, with
  `upstream_clarification_received=false`.
- Marked only CB-110 passed. CB-120, all later tasks and PG-1–PG-5 remain
  `not_started`; GitHub branch/PR/tag/publication remains empty.

## P1.1 / CB-100 — 2026-07-26

- Bound the supplied host-layout installer to one full local implementation
  commit SHA and deployed that exact archive as immutable
  `releases/<sha>` plus an atomic `current` pointer.
- Created the dedicated non-root `cyberboss` identity, exact root/service-owned
  directories, root-only environment/credential boundaries and a preserved
  first-apply rollback prestate.
- Installed only `cyberboss-cloud.service`; no backup/status/self-heal unit,
  Runtime, public route, provider resource or Private-MetaDatabase object was
  installed or activated.
- Hardened the main unit with `KillMode=control-group`, bounded restart and
  resource policy, strict filesystem sandbox/write allowlist and a size/rate-
  bounded `cyberboss` journald namespace.
- Made second apply truly idempotent for the same release: it validates the
  immutable manifest and existing profile/drop-in/journal instead of
  remeasuring resources or overwriting the original rollback pointer.
- Passed exact-target preflight, archive SHA-256 verification, two applies,
  permission negatives, 100/100 actual systemd kill/restarts and 100/100
  singleton-lock contention; final state is disabled/inactive with ports
  8765/8780 unused.
- Preserved the first acceptance harness's ambiguous raw-route-hash failure;
  the final complete rerun used a normalized topology that excludes only
  volatile route timers and passed unchanged-topology plus final verification.
- Kept the frozen App/vendor source bundles and strict
  `GPL-3.0-only AND AGPL-3.0-only` conflict record unchanged, with
  `upstream_clarification_received=false`.
- Marked only CB-100 passed. CB-110, all later tasks and PG-1–PG-5 remain
  `not_started`; GitHub branch/PR/tag/publication remains empty.

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
