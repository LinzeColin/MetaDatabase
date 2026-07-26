# CB-220 Validation Report

- Date: 2026-07-27
- Task: `P2.3 / CB-220`
- Task state: `passed`
- Implementation commit:
  `ac51cd2511a45def88068aef6d23fd10d7f507e4`
- Frozen base:
  `e5995d0967e789c99ce06b5b76fa794e5d455f68`
- CB-230: `not_started`
- PG-2: `not_started`
- Publication: none

## Result

AC-012、AC-013、AC-014、AC-015、AC-045 and AC-064 have executable local and
candidate-only target evidence. Runtime jobs use FIFO `created_at,id`
transactional claim; max active Runtime lease: `1`. A separate command control
lease prevents `/stop` from waiting behind the active Runtime lease.

Workspace alias revalidation occurs immediately before dispatch. The
allowlisted alias dispatches; absolute path、unknown alias and symlink escape
do not dispatch or alter the fixture filesystem. Runtime thread/turn values
remain in memory and durable records contain only irreversible references or
booleans.

Resource/readiness decisions fail closed for missing measurement and cover
poll freshness、Runtime health、memory、disk、inode、load、queue depth and stuck
leases. Target pressure ran inside a finite 128 MiB transient cgroup with
16 MiB allocated memory、8 MiB temporary disk and 100 queue items. The fixture
used no real-time soak and its OOM-kill delta was `0`.

Only explicitly terminal-retryable read-only work can requeue within its
attempt budget. Dispatch-started ambiguous bounded mutation never auto-replays.
Stale owners cannot heartbeat, and late/unmatched events cannot finish a newer
lease.

`/stop` acknowledgement records request truth only. Three executable outcomes
map Runtime `interrupted` to `cancelled`, `failed` to `failed_terminal` and
`completed` to `succeeded`; false terminal success count is zero.

## Verification

- Local scheduler specialty: `9/9`.
- Local CB-220 root contract: `2/2`.
- Local and target App regression: `213/213`.
- Target scheduler/workspace/resource/stop/recovery acceptance: `38/38`.
- Exact artifacts: four files; local and target SHA-256 gates passed.
- Target installer: write-free check, two applies and one independent verify
  passed; second apply was idempotent.
- Candidate: immutable/inactive with zero mutable entry findings.
- Final target: frozen `current` and workspace unchanged; workspace clean;
  business service disabled/inactive; process/listener/incoming/transient
  counts zero; canonical `runtime.db` absent.
- Cleanup: exact CB-220 staging、env、incoming、bootstrap、transfer and synthetic
  runtime removed; inactive exact candidate retained.
- GitHub: remote branch、PR、tag、release and commit-ref counts are all zero;
  no push was performed.

## Compliance and non-claims

Complete Corresponding Source, original source/licenses and the unresolved
conflict record are preserved. The conservative expression remains
`AGPL-3.0-only AND GPL-3.0-only`, and
`upstream_clarification_received=false`. No upstream support, sync,
clarification or endorsement is claimed.

No real Codex/WeChat credential or provider was used. Real Runtime, WeChat and
canonical sync remain `activation_pending`. Durable outbox worker/retry/
receipt belongs to CB-230; full operational self-heal belongs to CB-340.
PG-2 was not executed.

## Preserved corrections

Non-passing orchestration is retained rather than rewritten:

1. The first example-config command omitted `--allow-placeholders`; the exact
   documented form passed.
2. Literal macOS `/tmp` is a symlink and the acceptance output guard rejected
   it. The resolved private temporary directory passed without weakening the
   no-follow rule.
3. The first manifest hash command inherited an unsupported locale; the next
   formatting attempt removed the required `./` prefix and the validator
   reported 208 manifest findings. Canonical C-locale `shasum` formatting then
   passed with zero findings.
4. An indirect protected-record parser returned no target and was stopped by
   strict known-host. A regex escaping attempt stopped locally. The first
   connected read-only probe then stopped on a normal empty `pgrep` result
   under `pipefail`. The final parser required the frozen target hash, three
   known-host records and zero-safe counting. These attempts made no target
   mutation.
5. A post-build local checksum command inherited the same unsupported locale;
   rerunning with `LC_ALL=C` and `LANG=C` verified the unchanged artifacts.

CB-230 and every later task, plus PG-2–PG-5, remain `not_started`.
