# Changelog

## P5.4 / CB-530 — 2026-07-27

- Promoted immutable release `25670bf32c6d27e3668fcf59bc9ab754035e161d` under
  Linux systemd without changing the Owner-locked product version `v0.0.0.5`
  or frozen design baseline `v0.0.0.4`; a valid immutable `previous` release
  remains retained as the rollback target.
- Executed one real online Runtime SQLite snapshot and wrote the same immutable
  backup id to the frozen R2 and OCI scopes. R2 runtime/manifest objects passed
  exact PUT/GET SHA-256 and network-disabled, non-promoted isolated restore.
  OCI runtime/manifest PUT receipts, ETags and local hashes passed. Its normal
  daily PAR is deliberately write-only, so routine OCI readback remains
  `activation_pending_write_only_par`; a one-object Owner ObjectRead check
  hash-matched then revoked its temporary credential.
- Installed and enabled the Linux-only `cyberboss-backup.timer`; backup/restore
  units use systemd credential slots and Linux OAuth refresh rather than a
  static Mac-side process. Cloud service, dedicated Tunnel, unauthenticated
  Cloudflare Access challenge, global Status collector and both no-clone
  Private-Database dispatches were rechecked after the final switch.
- Control-plane and operations model calls remain `0`, no authenticated turn or
  simulator was started, and no macOS `launchd` dependency exists. WeChat stays
  fail-closed pending (`/readyz=503`), and `FORMAL_FINAL_ACCEPTANCE` remains
  pending. The next native node is `CB-540`.

## P5.3 / CB-520 — 2026-07-27

- Promoted immutable release `bb5a201a0aec38117a7e14f470662b6f45bd49c7`
  without changing the Owner-locked product version `v0.0.0.5`; retained
  verified CB-510 release `82b47668c33cc403fee9194ad42b77e49c8b7da3` as
  `previous` and executed a real `current → previous → current` rollback
  receipt under Linux systemd.
- Passed the finite request-count Canary: loopback health/Timeline/protected
  Status success, anonymous protected Status rejection, public Cloudflare Access
  challenge, release-code accepted/reject/oversize checks and bounded `/stop`
  cancellation semantics. No actual Codex turn, simulator or control/operations
  model call was made.
- The controlled service switch also stopped the dedicated tunnel unit; it was
  deterministically restarted, verified active/enabled, and the existing global
  Status collector was refreshed after the final release restore. Automatic
  tunnel lifecycle hardening remains scoped to CB-540.
- Real WeChat delivery stays fail-closed pending (`/readyz=503`); R2/OCI backup
  work is next in `CB-530`, and `FORMAL_FINAL_ACCEPTANCE` remains pending.

## P5.2 / CB-510 — 2026-07-27

- Activated immutable release `82b47668c33cc403fee9194ad42b77e49c8b7da3` on the
  authorized Linux host without changing the Owner-locked product version
  `v0.0.0.5` or the frozen design baseline. `current` binds that exact release,
  `previous` remains distinct and retained, and both the CyberBoss service and
  its dedicated Cloudflare Tunnel are enabled under Linux systemd.
- Verified a real no-clone Private-MetaDatabase material roundtrip under the
  separated data identity; enabled the daily timer and material-event path;
  rebuilt the public Chinese Timeline only from the redacted canonical projection
  and passed a direct privacy scan before switching its current pointer.
- Created and verified proxied Cloudflare DNS plus an Owner-email allow-only,
  default-deny Access application. The public route presents an Access challenge;
  the existing global Status collector now publishes the CyberBoss row and owns
  both cloud and tunnel units.
- Real Codex login and the loopback app-server are live, while control-plane and
  operations model calls remain `0`. No authenticated turn was started because
  that would violate the permanent zero-model invariant. No authorized real
  WeChat credential was present, so channel/bridge remain fail-closed pending
  (`/readyz=503`) with no simulator fallback or false readiness claim.
- R2/OCI, request-count Canary and live rollback remain later native task
  boundaries. The next node is `CB-520`; `FORMAL_FINAL_ACCEPTANCE` remains
  pending.

## P5.1 / CB-500 — 2026-07-27

- Closed the clean, isolated local staging dress rehearsal against PG-4 closure
  a5802bca6ac63c435121ab3bc970a6adededb7de, bound to implementation commit
  ddda629feb4455da5dba213a5d5f827001ce8c71 and tree
  c93bf0154468b379e3bd12e124fd1d894569f802, without changing the Owner-locked
  product version v0.0.0.5 or design baseline v0.0.0.4.
- The TaskPack Router selected webapp-testing. Its native body is unavailable
  in the local catalog, so the frozen embedded microplaybook was used with
  actual Skill body loads=0. No verifier, secondary model, external research,
  browser persistence, provider call, macOS launchd dependency or real-time
  wait was used.
- Thirty credential-scrubbed local commands passed: clean staging fixture,
  Timeline/Status/Access, simulator E2E, canonical sync, fault matrix,
  backup/isolated restore, immutable candidate/request predicates/rollback,
  dual pipelines, secret scan, App regression and all pack constraints.
  The sealed rehearsal digest is dec0e1518a5f99751a3c04b2c59ed3079f78f5a9ac807ba44add179a206448e1.
- Marked only CB-500 passed in the local deterministic scope. Current remains
  unchanged; production promotion, candidate installation, live request-count
  Canary, live rollback, Private-Database, Cloudflare Access/DNS/Analytics,
  Timeline/Status, OCI, self-heal, timer and service activation remain
  activation_pending. R2 remains hazard_blocked. The next native node is
  CB-510.

## PG-4 — 2026-07-27

- Closed the independent Stage 4 dual-pipeline and safe-release gate against
  immutable CB-440 anchor `5ac84f31e6889dc416cad405011dda572a463d38`, bound to
  implementation commit `d9960a4de965500802afb08758a43d7fb8d5032d` and tree
  `1a2befd9a124551eebfd103e7cbc3859485168ec`, without changing the
  Owner-locked product version `v0.0.0.5` or design baseline `v0.0.0.4`.
- Re-attested the five frozen CB-400–CB-440 Subject/evidence/implementation
  bindings and sealed Stage 4 evidence digest
  `34f540bea38fbb4dfef0d6a08f15e06bf8fa5827b9023198a1fcaff639a8a512`.
  Software correctness, model-safety fixture, security/privacy/supply-chain,
  fault/restore and immutable release candidate contracts all passed with
  unaccepted P0/P1 findings=0.
- The package Router selected no Skill in `DETERMINISTIC_TEST_ONLY` mode.
  Twenty-two credential-free local commands and both immutable manifests passed;
  no verifier, model, provider operation, macOS launchd dependency or real-time
  wait was used.
- Marked only PG-4 passed in the local deterministic scope. This is not
  FORMAL_FINAL_ACCEPTANCE: candidate installation, current switch, live
  request-count Canary, live rollback and all unapproved cloud/data/service
  operations remain `activation_pending` (R2 remains `hazard_blocked`).
  The next native node is CB-500.

## P4.5 / CB-440 — 2026-07-27

- Closed the local deterministic immutable-release candidate contract against
  CB-430 closure `045682e330f20ce4a5271f1a444c17bf1e2bf42c`, bound to
  implementation commit `78cdc61a484fee5ae05e4ac63cd146557a32a7e9` and tree
  `8c2a400d5063876955a790b65e892aded696976d`, without changing the
  Owner-locked product version `v0.0.0.5` or design baseline `v0.0.0.4`.
- Added a content-addressed local candidate, frozen MVP flags, additive
  backward-read fixture, immutable candidate/current/previous slots and eight
  request-count predicates. P0/P1 fixture failure immediately requires the
  previous pointer and keeps current unchanged; no fixed wait is allowed.
- The package router selected `output-skill` and exactly one local body was
  loaded. Twenty-two credential-free local checks plus both immutable manifests
  passed, including cloud layout, migration fixture, frozen core predeploy,
  security assurance, secret scan, App regression and prior evidence anchors.
- Marked only CB-440 passed in the local deterministic scope. Candidate install,
  current switch, live request-count Canary and live rollback remain
  `activation_pending`; R2 remains `hazard_blocked`, model calls remain zero,
  and macOS launchd remains absent. The next native node is PG-4.

## P4.4 / CB-430 — 2026-07-27

- Closed the local deterministic fault/crash-cut/recovery/restore core set
  against CB-420 closure `9f70eb6629d84e675d8df7183ae072b7e9bff7d7`, bound to
  implementation commit `088f04c786870c176681d92b8d01027baa7314b7` and tree
  `db648d19ee2650d1be59bfde7f4b9ad39166ae18`, without changing the
  Owner-locked product version `v0.0.0.5` or design baseline `v0.0.0.4`.
- Added a fixed 14-case, no-network matrix for fake-clock daily/material
  dispatch, historical replay, persist-before-cursor, lease, unknown outcomes,
  service/runtime/channel recovery, isolated restore and bounded resource
  recovery. Every loss, duplicate execution/side effect, unbounded retry,
  real-time wait, provider operation or model call fails closed.
- The package router selected `output-skill` and exactly one local body was
  loaded. Twenty-three credential-free local validations plus both immutable
  manifests passed, including focused component suites, official secret scan,
  full App regression, TaskPack/DAG/traceability/no-wait and all prior evidence
  anchors.
- Marked only CB-430 passed in the local deterministic scope. Postdeploy matrix
  is manual-or-CI and nonblocking; timer and all real provider/service recovery
  remain `activation_pending` (R2 remains `hazard_blocked`); control-plane and
  operations LLM calls remain zero and macOS launchd remains absent. The next
  native node is CB-440.

## P4.3 / CB-420 — 2026-07-27

- Closed the local deterministic security, supply-chain, privacy and AGPL
  assurance gate against CB-410 closure
  `ea82f02b175e864d754ab5bdfaccd0e84a89e6d4`, bound to implementation commit
  `307810329127910b4e0ef64e435099d02c74bd6e` and tree
  `5d9bc218bc8be077d3d793562aaf74d5f47b0d0b`, without changing the
  Owner-locked product version `v0.0.0.5` or design baseline `v0.0.0.4`.
- Added a no-network, read-only assurance evaluator that binds the existing
  129-component canonical SBOM, locked three-source Corresponding Source
  closure, strict unresolved whereabouts dual-license posture, secret scan and
  existing Access/Analytics privacy guards. It creates neither a new source
  repository nor a parallel SBOM/source truth.
- Replaced one pre-existing synthetic PEM marker in a CB-330 privacy fixture
  with semantically identical runtime assembly. The current official bounded
  scanner therefore reports P0=0/P1=0 without weakening the runtime-image
  privacy rejection test.
- The package router selected `output-skill` and exactly one local body was
  loaded. Nineteen credential-free local validation commands plus both
  immutable manifests passed, including secret scan, Access/workspace/runtime
  boundaries, CB-410/CB-400 evidence anchors, full App regression, DAG,
  traceability and no-wait checks.
- Marked only CB-420 passed in the local deterministic scope. Cloudflare Web
  Analytics/source distribution and all provider/service activation remain
  `activation_pending` (R2 remains `hazard_blocked`); model, control-plane and
  operations LLM calls remain zero and macOS launchd remains absent. The next
  native node is CB-430.

## P4.2 / CB-410 — 2026-07-27

- Closed the local deterministic Codex model-safety fixture gate against CB-400
  closure `55192340a3bc80ac979e283a5308daee9158ad3e`, bound to implementation
  commit `911d14c83a313f5a611d595acd72ee80415d97fa` and tree
  `2d9ab76492ff13925e98a01c5d7ba751e3206abd`, without changing the
  Owner-locked product version `v0.0.0.5` or design baseline `v0.0.0.4`.
- Added a six-case, no-model evaluator and System Card. It accepts only
  redacted fixed fixtures, rejects prompt/credential-like fields, workspace
  escape, any runtime/model invocation or external effect, and makes a
  false-success claim release-blocking unless its failed diff/tests are
  detected.
- The package router selected `output-skill` and exactly one local body was
  loaded. Sixteen credential-free local validation commands plus both immutable
  manifests passed, including workspace/approval/Codex protocol boundaries,
  CB-400 root core and evidence anchor, full App regression, DAG,
  traceability and no-wait checks.
- Marked only CB-410 passed in the local deterministic scope. Real Codex
  golden/abuse/recovery trials and budget/latency remain `activation_pending`;
  release remains disabled. Real model, control-plane and operations LLM calls
  are all zero; no data-plane/provider/service operation or macOS launchd
  dependency exists. The next native node is CB-420.

## P4.1 / CB-400 — 2026-07-27

- Closed the local software-correctness pipeline against PG-3 closure
  `3845d560591311c7e2b11e77e1dbdfc256486903`, bound to implementation commit
  `3e203ba760cab21b1a8d0bbd5d7f1b76d2fb884c` and tree
  `3717f5aa708f96ccaf3ae298d0312c18756576a6`, without changing the
  Owner-locked product version `v0.0.0.5` or design baseline `v0.0.0.4`.
- Added one frozen 10-slice core suite covering install/build/start,
  migration compatibility, inbox/outbox crash recovery, scheduler singleton,
  canonical conflict/privacy, Timeline/Status/Access, backup/restore,
  resource self-heal and rollback discrimination. A failed slice produces only
  `discard_candidate_keep_accepted_baseline` and no deployment mutation.
- Repaired the existing Claude-gate fixture to provide its full local immutable
  release/toolchain preconditions and canonical temporary paths. The test still
  proves Claude stays disabled unless both explicit gates are true; it invokes
  no model or real service.
- The package router selected `output-skill`; exactly one local body was loaded.
  Thirteen credential-free local checks passed, including the real frozen suite,
  nonblocking postdeploy plan, App/root regressions, PG-3 evidence anchor,
  identity/config, DAG, traceability, no-wait and manifests.
- Marked only CB-400 passed. No deployment, service, Provider, data-plane or
  model operation occurred; macOS launchd remains absent. R2 remains
  `hazard_blocked`; all other external activation truth remains
  `activation_pending`. The next native node is CB-410.

## PG-3 — 2026-07-27

- Closed the independent Stage 3 exit gate against immutable anchor
  `c132ee648ab2ad0f5f66c0dc3ee923c11cabfa42` and its tree
  `7b82c30f2937dd8a17f69055f520ebc7b66dd806`; all five CB-300–CB-340
  implementation trees and frozen closure evidence trees were re-attested and
  sealed in one deterministic subject digest.
- The package Skill Router selected no Skill in `DETERMINISTIC_TEST_ONLY`
  mode. Thirteen credential-free local checks passed, including the focused
  Stage 3 suites, frozen adapter truth-state and rollback-contract review,
  full App regression, DAG, traceability, no-wait and manifest checks.
- Marked only PG-3 passed. No Private-Database, R2, Cloudflare, DNS, Analytics,
  Timeline, Status, OCI or service operation occurred; all model calls remain
  zero and macOS launchd remains absent. External activation truth is unchanged:
  R2 is `hazard_blocked` and every other provider/service state remains
  `activation_pending`. The next native node is CB-400.

## P3.5 / CB-340 — 2026-07-27

- Closed the local deterministic resource/self-heal/retention contract against
  CB-330 closure `69012f32ae99ea35960c3dc08db059905a4f29ec`, bound to local
  implementation commit `9bed78ee1824eebbc4134811993667cb3ca72a9b` (tree
  `83d61b1efd8656353d4c02a23b26aec67c6af14a`), without changing Owner-locked
  product version `v0.0.0.5` or design baseline `v0.0.0.4`.
- Reused the existing ResourceReadinessGate and frozen retention values to build
  a strict local policy: recover/warn/protect hysteresis, six-action allowlist,
  one injected action at most, 120-second restart cooldown, three restart
  attempts per ten-minute fake-clock window, and a no-executor
  `activation_pending` result. It contains no systemd command, timer install,
  polling loop, sleep or model call.
- Added a retention report for two latest local-verified backups, seven-day
  logs, thirty-day diagnostics, current/previous immutable release slots and a
  512 MiB reconstructable-cache cap. It only reports review/isolation candidates;
  automatic backup/log/spool deletion is false.
- The package router selected `output-skill`; exactly one local Skill body was
  loaded and no other Skill/model/research path was used. The 14-command
  credential-free prepare validation passed, including frozen resource/external
  fixtures and the complete App regression.
- Marked only CB-340 passed. No service restart, timer install, data deletion,
  Private-Database, R2, Cloudflare, DNS, Analytics, global Status, OCI, WeChat,
  Codex, OVH or GitHub operation occurred; all model calls remain zero, macOS
  launchd remains absent, and self-heal/timer activation remains
  `activation_pending`. The next native node is PG-3.

## P3.4 / CB-330 — 2026-07-27

- Closed the local deterministic online-snapshot/backup/isolated-restore
  contract against CB-320 closure
  `202e99cee168f0a2fb618e22819bc350e7f5261c`, bound to local implementation
  commit `d994f6272d056812683a920a0baaaba65539f27b` (tree
  `56a230b3f70cbcb87ba4b20c118a4973b02539f8`), without changing Owner-locked
  product version `v0.0.0.5` or design baseline `v0.0.0.4`.
- Added the `cyberboss.backup-manifest.v3` thin layer using the built-in
  `node:sqlite` `DatabaseSync.serialize()` consistent-image API. It captures
  Runtime SQLite only, records source commit/schema/integrity/logic digest and
  archive SHA-256, excludes authentication/cookie/token/cache/build content,
  fsyncs files/directories and uses atomic publish. Concurrent-write, crash-cut,
  hash-tamper and privacy/scope tests all fail closed.
- Added isolated, network-disabled restore and local R2/OCI object simulators
  constrained to the frozen bucket/prefix policy. Both simulator receipts prove
  local object metadata/hash only and are labeled `simulator_verified`; they
  are not real remote receipts and cannot promote R2/OCI to `verified`.
- The package router selected `output-skill`; exactly one local Skill body was
  loaded and no other Skill/model/research path was used. The 13-command
  credential-free prepare validation passed, and the full App regression also
  passed against the same sealed implementation tree.
- Marked only CB-330 passed. No Private-Database, R2, Cloudflare, DNS,
  Analytics, global Status, OCI, WeChat, Codex, OVH or GitHub operation occurred;
  control-plane and operations model calls remain zero, macOS launchd remains
  absent, real R2 remains `hazard_blocked`, and OCI remains
  `activation_pending`. The next native node is CB-340.

## P3.3 / CB-320 — 2026-07-27

- Closed the local Access/domain/origin contract against CB-310 closure
  `183c2a7b624e5ae25c4ba27bb39651ebf207bfb4`, bound to local implementation
  commit `beb92bfa1121f35ee008b10055962a24118a5ec7` (tree
  `d7fe8e698b5b5a3a7bb6b0ed0b50f9ee34621b84`), without changing the
  Owner-locked product version `v0.0.0.5` or design baseline `v0.0.0.4`.
- Reused the frozen identity-scope policy as the sole Cloudflare configuration
  authority. The new `cyberboss.access-domain.v1` plan creates no provider
  resource: it specifies a proxied CNAME only after Access application/policy,
  self-hosted deny-by-default Access, narrow Owner/service-token slots and a
  loopback `127.0.0.1:8780` tunnel origin.
- Added local RS256 JWT signature, issuer, audience, `exp`/`nbf`, host, tunnel
  and origin-port checks. Every displayed route requires Access JWT; direct
  origin, wrong audience/signature, unknown route and any non-loopback 8765
  Runtime boundary fail closed. No JWT, identity or request header is persisted.
- Added privacy-first Cloudflare Web Analytics payload guards: only fixed UI
  page views and aggregate Core Web Vitals are accepted; query/fragment, prompt,
  result, private message, Access identity, job/thread IDs, cookie/token and a
  second analytics database are rejected. Atomic plan crash cuts preserve a
  complete last-good JSON.
- The package router selected `webapp-testing`, whose body was unavailable;
  the frozen embedded microplaybook used unit/HTTP fixtures with zero Skill body
  loads. The 14-command credential-free local validation passed, including the
  frozen Access policy and plan-only adapter.
- Marked only CB-320 passed. No Private-Database, R2, Cloudflare, DNS,
  Analytics, global Status, OCI, WeChat, Codex, OVH or GitHub operation occurred;
  control-plane and operations model calls remain zero, macOS launchd remains
  absent, and all real Access/DNS/Analytics states remain `activation_pending`
  (R2 remains `hazard_blocked`). The next native node is CB-330.

## P3.2 / CB-310 — 2026-07-27

- Closed the atomic redacted Status snapshot against CB-300 closure
  `e8243ea81b5ecf239a8ec2df44189259c661adfa`, bound to local implementation
  commit `5f977da0ed8c449aeaec3ae769982f6beccfd35e` (tree
  `ea1985fe90e1fdb8f31e893c2cece946455ba866`), without changing the
  Owner-locked product version `v0.0.0.5` or design baseline `v0.0.0.4`.
- Added strict `cyberboss.status.v2` snapshot/schema validation, allowlisted
  component states, deterministic generation IDs and fsync/rename publication.
  Existing last-good JSON survives the before-rename crash cut; after rename,
  the replacement is always complete JSON. Sensitive values, nonmonotonic
  generations and any nonzero control-plane/self-heal agent counter fail closed.
- Reused only the frozen global Status collector adapter's local `buildRow`
  function; it performs no fetch, introduces no second Status platform and maps
  `unknown`/`activation_pending` to non-green state. User-facing row labels
  remain Chinese and `agent`/notification are fixed to `无`.
- The package router selected `webapp-testing`, whose body was unavailable;
  the frozen embedded microplaybook used existing unit/DOM fixtures with zero
  Skill body loads. The 12-command credential-free local validation passed,
  including component fault matrix, atomic crash cuts, DLP/schema and zero
  model counter checks.
- Marked only CB-310 passed. No Private-Database, R2, Cloudflare, OCI, global
  Status, WeChat, Codex, OVH or GitHub operation occurred; control-plane and
  operations model calls remain zero, macOS launchd remains absent, and all
  external Status/Cloud activation remains `activation_pending` (R2 stays
  `hazard_blocked`). The next native node is CB-320.

## P3.1 / CB-300 — 2026-07-27

- Closed the canonical Timeline projection against PG-2 closure
  `f3848fd3b694871f04aba59838704fe91f27cdc0`, bound to local implementation
  commit `02ac88119fc864c37b5346c2ad334e17c6bc7702` (tree
  `22415bfe64ebd8ea8c09120af6b8cc501ca56da8`), without changing the
  Owner-locked product version `v0.0.0.5` or design baseline `v0.0.0.4`.
- Reused the locked `timeline-for-agent` renderer only as a static view layer.
  The adapter accepts CB-240 canonical NDJSON only, removes raw identifiers and
  summaries, emits opaque public IDs/fixed Chinese titles, atomically publishes
  content-addressed releases, indexes search and preserves `last-good` on
  invalid input or build failure.
- The package router selected `webapp-testing`, whose body was unavailable;
  the frozen embedded microplaybook used existing unit/DOM fixtures with zero
  Skill body loads. The 12-command credential-free local validation passed,
  including clean/reused rebuild, search, privacy, Chinese UI, empty-state and
  last-good cases.
- Marked only CB-300 passed. No Private-Database, R2, Cloudflare, OCI, WeChat,
  Codex, OVH or GitHub operation occurred; control-plane/operations model calls
  remain zero, macOS launchd remains absent, and Timeline publication remains
  `activation_pending`. The next native node is CB-310.

## PG-2 — 2026-07-27

- Closed the independent Stage 2 durable messaging/canonical gate against the
  immutable CB-240 closure anchor `91e9c267a775b138e27b196f0cc96de552ba958b`.
  The sealed Stage 2 subject binds all five implementation commits, evidence
  trees, aggregate evidence digest and both frozen manifest digests without
  changing the Owner-locked product version `v0.0.0.5`.
- The package Skill Router returned `DETERMINISTIC_TEST_ONLY` for PG-2;
  no Skill was loaded. The fail-closed local gate actually reran focused Stage
  2 App/root suites, full App regression, identity/config, DAG, traceability,
  no-wait and TaskPack checks in a credential-name-scrubbed temporary state.
- Marked `PG-2=passed` only for the local deterministic Gate. No provider,
  Private-Database, R2, Cloudflare, OCI, WeChat, Codex, OVH or GitHub mutation
  occurred; real activation remains pending (R2 remains hazard-blocked), and
  the next independent native Run is `CB-300`.

## P2.5 / CB-240 — 2026-07-27

- Bound the redacted append-only canonical-sync implementation to local commit
  `fcfac053cab6944b2fc13a62491cce8ddb93e649` (tree
  `781a8e32d2c3248c4cc4aebfe164a033efd45949`) without changing the Owner-locked
  product version `v0.0.0.5` or the `v0.0.0.4` design baseline.
- Split local deterministic object formation from remote dispatch: ordinary
  facts stage immediately but remote dispatch is only daily at `03:20 UTC` or
  an explicit operator invocation; legacy 60-second age remains parse-compatible
  and cannot create a remote commit.
- Fixed the material allowlist to `release_completed`, `incident_declared` and
  `recovery_completed`. A material-only systemd path/oneshot data worker shares
  the existing canonical lock, never invokes a model, and remains disabled and
  inactive in the candidate-only installation path.
- Added bounded `daily|material|manual` data-worker modes (2,000 events,
  10 MiB uncompressed bytes, five attempts), `noop_no_commit` for no eligible
  work, material retry protection, ordinary-age observation without mutation
  blocking, and no-clone/reconcile/quarantine preservation.
- Passed local deterministic canonical acceptance, root CB-240 contract,
  identity/config/manifest checks and merge-safe `validate_cb240.py --prepare`.
  The acceptance covers 1,000 canonical fixture events, 50 concurrent groups,
  virtual 429/outage recovery, 409/partial success, same-ID/different-hash
  quarantine, daily/material cadence, no empty commit and rebuild.
- Sealed only the local CB-240 subject in `docs/evidence/CB-240/`. Real
  Private-Database/R2/Cloudflare/OCI activity, target candidate installation,
  `current` switching and service activation remain `activation_pending`; no
  credential content, external mutation, GitHub publication, PG-2 or CB-300
  execution is claimed.

## P2.4 / CB-230 — 2026-07-27

- Bound durable outbox and complete Corresponding Source to local
  implementation commit
  `1b3e338847d8819869a5e12091f25b5463a8d3be`.
- Added additive schema v4, encrypted payload/target storage, stable
  logical-message/dedupe/provider-client identity, append-only attempt events
  and provider-confirmation truth guards. Legacy active outbox identity is
  deterministically backfilled before claim.
- Routed accepted and final result/error/cancelled delivery through durable
  staging before provider dispatch. Jobs reach `replied` only after every
  required final chunk is confirmed.
- Passed virtual 503→503→200 in three attempts with 1000/2000 ms delays and no
  real wait; 1,000 same-key stages produced one durable row and one confirmed
  delivery.
- Passed deterministic 13,300-code-point four-chunk reconstruction, terminal
  401 fixed-advice handling, void-receipt rejection and four restart cuts.
  Unknown post-dispatch outcome auto-replay remained zero.
- Passed local and immutable-candidate App regressions at 227/227 and target
  synthetic acceptance at 37/37, with DB/WAL/SHM plaintext and key hits zero.
- Passed target write-free checks, two applies and an independent verify.
  Removed exact staging, env, incoming and synthetic runtime; retained only the
  immutable inactive candidate. `current`/workspace stayed frozen and service,
  process, listener and canonical runtime DB stayed inactive/absent.
- Preserved all fail-closed correction records, original source/licenses and
  the unresolved strict `AGPL-3.0-only AND GPL-3.0-only` conflict with
  `upstream_clarification_received=false`.
- Marked only CB-230 passed. CB-240 and all later tasks plus PG-2–PG-5 remain
  `not_started`; GitHub branch/PR/tag/release/publication remains empty.

## P2.3 / CB-220 — 2026-07-27

- Bound the single-lease Runtime scheduler and complete Corresponding Source
  to local implementation commit
  `ac51cd2511a45def88068aef6d23fd10d7f507e4`.
- Added additive schema v3, FIFO `created_at,id` transactional claim, global
  Runtime singleton lease, heartbeat/expiry recovery, stale-owner fencing and
  a separate command control lease.
- Revalidated the root-controlled workspace alias before every dispatch;
  absolute, unknown and symlink-escape cases reached Runtime zero times and
  changed the fixture filesystem zero times.
- Added deterministic channel-poll/Runtime/resource/queue readiness decisions,
  fail-closed unavailable measurements and safe read-only-only retry; ambiguous
  bounded mutation auto-replay remained zero.
- Preserved Runtime terminal truth across three `/stop` outcomes:
  interrupted→cancelled, failed→failed_terminal and completed→succeeded;
  acknowledgement claimed no terminal success.
- Passed local and immutable-candidate App regressions at 213/213, scheduler
  specialty 9/9, target executable acceptance 38/38 and a finite 128 MiB
  transient-cgroup pressure fixture with OOM-kill delta 0.
- Passed target write-free checks, two applies and an independent verify.
  Removed exact staging, env, incoming, bootstrap and synthetic runtime after
  evidence readback; retained only the immutable inactive candidate.
- Preserved the config-placeholder, symlink-output, manifest-locale/format and
  target-parser/zero-process correction records with no target mutation before
  the final authorized sequence.
- Preserved original source/licenses and the unresolved strict
  `AGPL-3.0-only AND GPL-3.0-only` conflict record with
  `upstream_clarification_received=false`.
- Marked only CB-220 passed. CB-230 and all later tasks plus PG-2–PG-5 remain
  `not_started`; GitHub branch/PR/tag/release/publication remains empty.

## P2.2 / CB-210 — 2026-07-27

- Bound durable inbox-before-cursor and complete Corresponding Source to local
  implementation commit
  `5c7b48d8f618bc83a70ebbd63eaf94b6ce6627ea`.
- Split WeChat fetch from explicit candidate cursor commit; added stable
  provider identity, accepted/rejected durable records, one-job replay,
  numeric highest-continuous ordering and atomic compare-and-set cursor writes.
- Passed ten named CB-210 tests, three real child-process `SIGKILL` cuts,
  1,000 replays, ordering/property, database integrity, canonical reconcile and
  plaintext/key scans with zero message loss or duplicate synthetic execution.
- Passed local and immutable-candidate App regressions at 195/195; target
  write-free check, two applies, independent verify and synthetic acceptance
  all passed.
- Preserved the local CLI, read-only preflight, checksum-locale, two fail-closed
  streaming-transfer and read-only GitHub-query correction records, including
  their zero-target-mutation or verified cleanup outcomes.
- Removed target staging, staging environment, incoming, bootstrap and
  synthetic runtime/key state after report readback. Left the exact candidate
  immutable/inactive, `current` and workspace unchanged, service
  disabled/inactive, and process/listener/canonical runtime DB absent.
- Preserved original source/licenses and the unresolved strict
  `AGPL-3.0-only AND GPL-3.0-only` conflict record with
  `upstream_clarification_received=false`.
- Marked only CB-210 passed. CB-220 and all later tasks plus PG-2–PG-5 remain
  `not_started`; GitHub branch/PR/tag/release/publication remains empty.

## P2.1 / CB-200 — 2026-07-27

- Bound the SQLite WAL spool, strict job state machine and complete
  Corresponding Source to local implementation commit
  `6c8d7a1092a1f4d10a7f512ebe9abd2380aa2287`.
- Added additive schema v2 migration, WAL/FULL/foreign-key/busy-timeout
  initialization, exact legal-transition guards, immutable job events, stable
  HMAC IDs, transactional replay deduplication and optimistic state versions.
- Added caller-key AES-256-GCM active payload storage, AAD binding, bounded TTL
  redaction and fail-closed redacted metadata validation.
- Passed 10,000 stable-ID fixtures, 10,000 transition attempts, 32 concurrent
  inserters, five child-process crash cut points, migration compatibility,
  canonical reconciliation and live DB/WAL/SHM plaintext/key scans.
- Passed local and immutable-candidate App regressions at 185/185; target
  write-free check, two applies, independent verify and synthetic acceptance
  all passed.
- Preserved the concurrency, target bootstrap, superseded candidate filename,
  macOS metadata inventory, shell-quoting and read-only process-filter
  correction records with their exact fail-before-acceptance, zero-mutation or
  cleanup outcomes.
- Removed target staging, staging environment, incoming, bootstrap, synthetic
  key and acceptance DB/WAL/SHM after evidence retrieval. Left the exact
  candidate inactive, `current` on CB-100, workspace on CB-120 and service
  disabled/inactive with zero process/listener and no canonical runtime DB.
- Preserved original source/licenses and the unresolved strict
  `AGPL-3.0-only AND GPL-3.0-only` conflict record with
  `upstream_clarification_received=false`.
- Marked only CB-200 passed. CB-210 and all later tasks plus PG-2–PG-5 remain
  `not_started`; GitHub branch/PR/tag/release/publication remains empty.

## PG-1 Stage 1 Exit Gate — 2026-07-27

- Independently froze and verified the five CB-100–CB-140 evidence trees,
  implementation commits, closure commits and 15 unique Acceptance IDs from
  P1.5 closure `4020f07bc086ab9827ab97ddf295927075189a9f`.
- Passed a 15-command credential-free matrix with temporary HOME, empty
  CODEX_HOME/WeChat state: simulator contract 5/5, Walking Skeleton static
  4/4, live process chain 1/1, two root contract suites 5/5 each, App check
  and full 175/175 regression.
- Revalidated frozen target results: simulator E2E 10/10, input-policy Runtime
  deltas 0/1/0, 20/20 latency samples, raw trace content=0, Mac dependency=0
  and non-loopback Runtime connection/listener=0.
- Performed a fresh strict-known-host, key-only target metadata probe. The
  CB-140 candidate remains inactive; service is disabled/inactive;
  process/listener/staging/env/incoming/token counts are zero; `current` and
  workspace are unchanged.
- Preserved the first read-only target probe's zero-result `pipefail` and the
  first rejected PR-query method error as non-passing attempts. Both made zero
  external object mutation; corrected probes passed.
- Confirmed GitHub branch/PR/tag/release counts are zero and performed no
  push/publication.
- Preserved original source/licenses and the unresolved strict
  `AGPL-3.0-only AND GPL-3.0-only` conflict record with
  `upstream_clarification_received=false`.
- Marked only PG-1 passed. Real Codex/WeChat remain `activation_pending`;
  CB-200 and all later tasks/PG-2–PG-5 remain `not_started`. No Stage 2 SQLite
  WAL spool is claimed.

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
