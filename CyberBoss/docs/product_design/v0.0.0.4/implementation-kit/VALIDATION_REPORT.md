# CyberBoss v0.0.0.4 Design Baseline / v0.0.0.5 Product Validation Report

- Date: 2026-07-27
- Current Run: `P2.5 / CB-240`
- Owner amendment: TaskPack `v0.0.0.7`; product version remains locked at
  `v0.0.0.5`.
- Input closure:
  `8793e186f4baa2767dc3da0378492ffa17984d4d`
- Scope: redacted append-only canonical sync、identity-separated no-clone
  data plane、conflict-safe reconciliation and SQLite-independent rebuild
- Publication: local branch only; no push, PR, tag or release

## Current implementation readiness

- Schema v5 additively extends the v1–v4 runtime spool with immutable canonical
  event/batch identity、content hash、retry、receipt、verification and integrity
  state. Existing migrations remain readable and no destructive migration is
  introduced.
- The code plane maps terminal job/material events to a strict allowlist,
  recomputes every `record_sha256`, and writes only redacted stable fields.
  Full prompt/result、raw provider identity、credential and encryption key are
  excluded.
- Local objects are stable NDJSON in deterministic gzip (`mtime=0`) and are
  bounded by 50 records、262144 uncompressed bytes. Ordinary facts stage
  immediately but only a daily `03:20 UTC`/operator dispatch may write them
  remotely; 60-second age is parse-compatible only and never a remote trigger.
  The fixed material allowlist is `release_completed`、`incident_declared`、
  `recovery_completed`, with bounded immediate invocation, a material-only
  systemd path trigger and no empty commit.
- The code identity can stage outgoing objects and consume hash-only receipts.
  Only the separate `cyberboss-data` OS identity can execute the fail-closed
  wrapper around the pinned `private_db_client.py`; the only allowed operations
  are `ingest|get|list|verify`, with `Private-MetaDatabase`、`domain=CyberBoss`
  and no clone.
- The data worker re-reads canonical manifest/object/event sets before and after
  ingest. Manifest 409、403、429、transient and partial-success outcomes remain
  pending or reconcile by event-ID/hash set; last-write-wins is forbidden.
- Same event ID with a different record hash is quarantined as an integrity
  incident and blocks new bounded mutation. Resource breach and material retry
  also protect mutation; ordinary backlog age alone does not. An existing
  read-only job may still drain while the protected mutation remains queued.
- Rebuild starts from no-clone canonical objects and an optional deterministic
  R2 pointer fixture, does not require the prior SQLite, and emits only a
  terminal index、CB-300 Timeline source projection and rebuild report.
- The exact-commit builder/installer has a CB-240 branch. Installation is
  immutable and candidate-only, installs disabled/inactive systemd units and
  never switches `current`, starts/enables a unit or performs a real canonical
  operation.
- Strict `AGPL-3.0-only AND GPL-3.0-only`, original source/licenses, unresolved
  conflict record and `upstream_clarification_received=false` remain unchanged.

## Passed locally

- Focused App suite passed `20/20`: 50-record batching、ingest/list/get/verify,
  deterministic compression, 409 partial success, 429 retry hint, virtual
  ten-minute outage/catch-up, daily ordinary dispatch, three material-event
  immediate dispatches, empty-commit NOOP, ordinary-age non-protection,
  metadata-only receipt allowlisting, integrity quarantine, rebuild and
  scheduler mutation protection.
- Root CB-240 contract/acceptance passed `7/7`, including the executable
  deterministic acceptance.
- Executable acceptance generated 1,000 canonical events as 20 objects of 50,
  exercised 50 concurrent sync groups, and finished with event-ID/hash
  `set_diff=0`.
- AC-030 rebuild deleted the isolated SQLite and reconstructed 1,000 terminal
  events/jobs from canonical fixture objects plus an R2 pointer fixture.
- AC-031 proved 50 ordinary facts perform zero remote commits before daily
  dispatch, daily cadence is `03:20 UTC`, no-new-fact returns
  `noop_no_commit`, and all three material event types flush at virtual
  P95 `0s <= 60s`. Record/byte boundaries remain deterministic; ordinary age
  does not block bounded mutation.
- AC-032 exercised manifest 409、403、429 (`retry_hint_ms=120000`)、503,
  partial success and 600 seconds of virtual outage, with zero real wait calls
  and zero event loss.
- AC-033 scans reported full prompt/result/identity hits `0` and encryption-key
  hits `0`.
- Python identity/scope suite passed `9/9`; configuration validation passed.
- Full App syntax check passed. Full App regression passed `236/236`, with zero
  skipped and zero failed.
- Shared installer and canonical acceptance `--check` passed with
  `persistent_writes=false`、`live_commands=false`、`service_started=false`,
  `private_database_operations=false` and `pg_2_executed=false`.

## Retained correction records

- The first deterministic acceptance exposed fixture object names that did not
  carry the canonical ownership prefix. The fixture and production reader now
  share the same fail-closed prefix contract.
- Scheduler integration initially protected the FIFO mutation head but also
  prevented a later read-only job from draining. The database claim now accepts
  an explicit `read_only` filter while preserving the mutation in place.
- Canonical mapping initially collapsed material event semantics into only the
  terminal job status. It now preserves the allowlisted material event type
  (`job.<event_type>`) while retaining the terminal status separately.
- Final determinism/privacy review found locale-sensitive event sorting and a
  receipt parser that ignored extra fields. Event-set hashing now uses explicit
  UTF-8 byte ordering, and every receipt status has an exact metadata-only
  field allowlist.
- The first local manifest regeneration inherited an unsupported `C.UTF-8`
  locale and produced empty outputs. The next local validation caught the
  defect before any commit; both manifests were regenerated from unchanged
  inputs under the supported `C` locale.

## Closure boundary

- This report documents deterministic local readiness only. It does not claim
  real Private-Database/R2/Cloudflare/OCI activation, target service start,
  `current` switch, PG-2, or CB-300.
- Provider activation remains `activation_pending` until a later authorized
  native task supplies real credential-scoped evidence; simulator evidence is
  never promoted to real verification.
- Transfer only the bounded artifact set, apply the inactive candidate twice,
  verify once, and execute target deterministic canonical acceptance.
- Export redacted evidence, delete exact CB-240 staging/env/incoming/synthetic
  runtime/data state, and prove all units inactive/disabled、zero process and
  listener、unchanged `current`/workspace and absent canonical `runtime.db`.
- Commit evidence and closure state, then run the final fail-closed validator.
  `PG-2` and `CB-300` remain separate later Runs.

## Explicit non-claims

- Deterministic filesystem/API fixtures are not authenticated real
  Private-MetaDatabase operations.
- The R2 recovery pointer is a deterministic fixture, not a real R2 write/read.
- The Timeline output is only a canonical source projection for CB-300; no
  Timeline Web/build/search or Access route is implemented or verified here.
- Real Private-MetaDatabase credential activation remains
  `activation_pending`; no real credential is read.
- Candidate installation is not production activation and the canonical timer
  remains disabled/inactive.
- `PG-2` is not executed; it remains an independent later Run after all five
  Stage 2 tasks are closed.
- No upstream clarification, support or endorsement is claimed.
- No original vendor source, license, provenance, conflict or prior evidence is
  rewritten.
- No GitHub branch, PR, tag or release is created.
- CB-230 and PG-1 remain passed. `machine/facts/task_state.json` together with
  the sealed CB-240 closure evidence is the authoritative task state; this
  implementation report does not independently advance it. CB-300 onward and
  every later gate remain `not_started`.
