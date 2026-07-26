# CyberBoss v0.0.0.4 Implementation Kit Validation Report

- Date: 2026-07-27
- Current Run: `P2.2 / CB-210`
- Input closure:
  `4f914e3b6ed3145a16c1572f4176068b9829b920`
- Scope: WeChat candidate cursor、durable inbox before cursor、source replay
  idempotency、three crash cuts and candidate-only acceptance
- Publication: local branch only; no push, PR, tag or release

## Current implementation readiness

- WeChat `fetchUpdates` only returns raw messages, committed cursor and candidate
  cursor. It does not write cursor or context state. Cursor commit is a separate
  compare-and-set operation using owner-only directories/files, no-follow
  checks, file fsync, atomic rename and directory fsync.
- Numeric cursor fixtures require the unique continuous sequence
  `committed+1 ... candidate`; gap、duplicate sequence and regression fail
  closed. Opaque provider cursors advance only after every actionable message
  in the returned batch is durable.
- Stable source identity prefers provider `message_id`, then `client_id`, then
  a stable sequence/time/sender tuple. If none exists, ingestion fails closed
  rather than inventing a random or receive-time identity.
- `DurableInboxCoordinator` normalizes with in-memory dedupe disabled, encrypts
  active payload/context through the CB-200 SQLite spool, persists
  `cursor_batch_id`, and commits the candidate cursor only after every accepted
  or policy-rejected user message is durable.
- Policy rejection creates a durable rejected inbox and no executable job.
  Replay of an accepted source returns the existing deterministic job and never
  creates a second executable job.
- `CB_DURABLE_INBOX` defaults to `true`. App startup requires two distinct
  owner-only 32-byte key files and an absolute runtime DB path. The imported
  direct-dispatch flow is available only with explicit non-production staging
  flags.
- The durable App branch queues jobs and does not directly call Runtime.
  Scheduler/global lease/resource gate and claim-after-crash recovery remain
  `CB-220`; durable outbox/send confirmation remain `CB-230`.
- Builder and installer package complete Corresponding Source and a generated
  `durable-inbox-matrix.json` from one clean exact commit. Candidate install
  stays immutable/inactive and does not switch `current`, enable/start service,
  use real credentials/provider/Private-MetaDatabase or execute PG-2.
- Strict `AGPL-3.0-only AND GPL-3.0-only`, original source/licenses, unresolved
  conflict record and `upstream_clarification_received=false` remain unchanged.

## Passed locally

- Cursor store: atomic commit, `0600` file, `0700` directory, stale-writer
  rejection, numeric regression rejection, symlink/oversize rejection and no
  leftover temporary file.
- Adapter integration: real loopback HTTP fixture proves fetch returns the
  candidate while cursor and plaintext context cache remain unchanged.
- Crash matrix: real child-process `SIGKILL` at
  `after_fetch_before_durable`、`after_durable_before_cursor` and
  `after_cursor`; every restart ends with one inbox, one job, cursor committed,
  integrity `ok`, message loss `0` and synthetic execution count `1`.
- Replay: the same provider source is ingested 1,000 times; final counts are one
  inbox, one job, two initial immutable job events and one synthetic execution.
- Ordering/property: reversed 3-message batch is sorted and committed;
  numeric gap、duplicate sequence and regression are rejected without DB or
  cursor advancement.
- Rejection: disallowed source is durable with `status=rejected` and no job.
- Mock canonical outage/recovery remains executable; final reconcile set diff
  is `0`.
- Synthetic acceptance runner repeats all ten named CB-210 tests, crash
  matrix, replay, ordering, DB/query and plaintext/key scans. Result:
  `replay_count=1000`、`execution_count=1`、`crash_cut_points=3`、
  `plaintext_hits=0`、`reconcile_set_diff=0`.
- Shared installer and acceptance `--check` pass with
  `persistent_writes=false`、`live_commands=false` and
  `service_started=false`.
- Root CB-210 contract tests: `7/7`.
- Full App regression: `195/195`; zero skipped and zero failed.

## Retained correction record

- The first full App run passed `192/193`. The historical CB-140 live simulator
  inherited the new mandatory durable default but intentionally has no spool
  keys because it tests the pre-Stage-2 direct path. Its fixture now explicitly
  declares `NODE_ENV=test`、`CB_DURABLE_INBOX=false` and
  `CB_ALLOW_BASELINE_STAGING=true`; production fallback remains forbidden. The
  unchanged CB-140 live mechanism and the full suite then passed.

## Pending before CB-210 may pass

- Finalize README/report and regenerate both exact SHA-256 manifests.
- Run prestage/TaskPack validators and `validate_cb210.py --prepare`.
- Create the exact implementation commit and build four artifacts from its
  clean tree: Corresponding Source, artifact manifest, durable matrix and
  checksums.
- Run protected-target fresh read-only preflight, transfer only the bounded
  artifact set, run two candidate applies and one verify.
- Run target synthetic acceptance in CB-210 staging, preserve redacted
  crash/replay/ordering/query/security evidence, then delete staging
  env/state/incoming and the synthetic runtime root.
- Prove final disabled/inactive, zero process/listener, unchanged
  `current`/workspace and absent canonical `runtime.db`.
- Commit only evidence/closure state, run final validators, then mark CB-210
  passed. CB-220 and PG-2 remain separate Runs.

## Explicit non-claims

- Synthetic execution is not authenticated real Runtime execution.
- Claim-after-cursor scheduler/lease recovery is not implemented; it belongs to
  CB-220.
- Durable outbox worker/retry/receipt/confirmation is not implemented; it
  belongs to CB-230.
- Real WeChat, Codex Runtime and Private-MetaDatabase remain
  `activation_pending`; no real credential is read.
- PG-2 is not executed; it requires all five Stage 2 tasks in a later
  independent Run.
- No upstream clarification, support or endorsement is claimed.
- No original vendor source, license, provenance, conflict or prior evidence is
  rewritten.
- No GitHub branch, PR, tag or release is created.
- CB-200 and PG-1 remain passed. CB-210 remains `not_started` until exact target
  acceptance closes; CB-220 onward and every later gate remain `not_started`.
