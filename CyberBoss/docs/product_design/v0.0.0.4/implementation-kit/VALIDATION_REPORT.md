# CyberBoss v0.0.0.4 Implementation Kit Validation Report

- Date: 2026-07-27
- Current Run: `P2.3 / CB-220`
- Input closure:
  `e5995d0967e789c99ce06b5b76fa794e5d455f68`
- Scope: single Runtime lease、FIFO claim、resource/readiness gate、
  workspace revalidation、truthful stop and fail-closed Runtime recovery
- Publication: local branch only; no push, PR, tag or release

## Current implementation readiness

- Runtime jobs are ordered by `created_at,id` and claimed in one SQLite
  transaction. A partial unique index plus owner token, heartbeat, expiry and
  state-version fencing enforce one global active Runtime lease.
- Slash commands use a separate singleton control lease. `/stop` can therefore
  reach an active Runtime without waiting behind it; acknowledgement records
  `cancel_requested` only, while Runtime terminal events remain authoritative.
- Runtime thread/turn identifiers stay in memory. Durable records contain only
  HMAC references or booleans, and late/unmatched events cannot release another
  job's lease.
- Dispatch revalidates the root-controlled workspace alias every time.
  absolute、unknown、symlink escape and root drift are rejected before Runtime
  invocation and without filesystem mutation.
- The resource/readiness gate is deterministic and fail closed for unavailable
  measurement、stale poll、unhealthy Runtime、memory/disk/inode/load pressure、
  queue pressure and stuck lease. All timing accepts an injected clock; no
  acceptance uses a real-time soak.
- Recovery distinguishes before-dispatch read-only work from dispatch-started
  ambiguity. Only explicit terminal-retryable read-only jobs can requeue within
  budget; bounded mutation ambiguity is terminal and never auto-replayed.
- Codex and Claude Code event normalization preserves completion status,
  cancellation, retryability, error class and approval turn binding. Real
  Runtime activation remains `activation_pending`.
- The shared exact-commit builder/installer now has a CB-220 branch while
  preserving CB-130 through CB-210 behavior. Candidate installation remains
  immutable/inactive and cannot switch `current` or enable/start the service.
- Strict `AGPL-3.0-only AND GPL-3.0-only`, original source/licenses, unresolved
  conflict record and `upstream_clarification_received=false` remain unchanged.

## Passed locally

- Scheduler matrix: five queued Runtime jobs dispatch FIFO with historical
  maximum active lease `1`; two DB owners cannot claim a second lease.
- Lease/recovery matrix: stale owner heartbeat fails, pre-dispatch work can be
  safely recovered, dispatch-started mutation is terminal, and late events are
  fenced.
- Retry matrix: proven read-only retry requeues once; bounded mutation never
  auto-replays.
- Control matrix: three `/stop` outcomes map Runtime `interrupted` to
  `cancelled`, `failed` to `failed_terminal` and `completed` to `succeeded`;
  acknowledgement claims no terminal success.
- Workspace matrix: allowlisted alias dispatches; absolute path、unknown alias
  and symlink escape do not dispatch or alter the fixture filesystem.
- Resource matrix: protect blocks mutation and recover permits dispatch across
  poll/runtime/memory/disk/inode/load/queue/stuck deterministic fixtures.
- App integration proves `/bind` and `/new` reject while a Runtime lease is
  active, `/status` remains privacy-bounded, and an allowed alias binds the
  exact in-memory Runtime run.
- Codex terminal/approval event mapping is executable. Scheduler specialty
  suite passed `9/9`; root CB-220 contract tests passed `2/2`.
- Full App syntax check passed. Full App regression passed `213/213`, zero
  skipped and zero failed.
- Shared installer and target acceptance `--check` passed with
  `persistent_writes=false`、`live_commands=false` and
  `service_started=false`.

## Retained correction record

- A manual acceptance invocation under literal `/tmp` was rejected with
  `OUTPUT_PARENT_INVALID` because macOS exposes `/tmp` as a symlink. The
  acceptance contract intentionally rejects symlink output parents; the root
  executable test uses a resolved private temporary directory and passes.
- The earlier full App run exposed a historical CB-140 fixture that omitted a
  workspace registry from its app-like stub. The compatibility fallback now
  applies only to that pre-scheduler test shape; production App paths retain
  mandatory registry revalidation.

## Pending before CB-220 may pass

- Regenerate both exact SHA-256 manifests and run prestage/TaskPack/CB-220
  prepare validators.
- Create the exact implementation commit and build four artifacts from its
  clean tree: Corresponding Source、artifact manifest、scheduler matrix and
  checksums.
- Resolve the existing protected target from local deployment records, then
  perform fresh read-only preflight.
- Transfer only the bounded artifact set, run two candidate applies and one
  verify, then execute target scheduler acceptance plus the transient-cgroup
  pressure fixture.
- Export redacted evidence, delete exact CB-220 staging/env/incoming/synthetic
  runtime state, and prove disabled/inactive、zero process/listener、unchanged
  `current`/workspace and absent canonical `runtime.db`.
- Commit evidence and closure state, then run the final fail-closed validator.
  CB-230 and PG-2 remain separate later Runs.

## Explicit non-claims

- Deterministic fixture dispatch is not authenticated real Runtime execution.
- Cancel request acknowledgement is not terminal cancellation success.
- Resource fixture coverage is not a real-time production soak.
- Durable outbox worker/retry/receipt/confirmation is not implemented; it
  belongs to CB-230.
- Full operational status/self-heal belongs to CB-340.
- Real WeChat, Codex Runtime and Private-MetaDatabase remain
  `activation_pending`; no real credential is read.
- PG-2 is not executed; it requires all five Stage 2 tasks in a later
  independent Run.
- No upstream clarification, support or endorsement is claimed.
- No original vendor source, license, provenance, conflict or prior evidence is
  rewritten.
- No GitHub branch, PR, tag or release is created.
- CB-210 and PG-1 remain passed. CB-220 remains `not_started` until exact target
  acceptance closes; CB-230 onward and every later gate remain `not_started`.
