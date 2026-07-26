# CB-030 Validation Report

- Task: `P0.4 / CB-030`
- State: `PASS`
- Claim level: simulator-backed non-activation validation
- Real Codex adapter: `activation_pending`
- Real WeChat adapter: `activation_pending`
- External mutation: none
- GitHub publication: none

## Acceptance accounting

| Acceptance | P0.4 result | Evidence boundary |
|---|---|---|
| AC-001 | non-activation simulator Oracle passed; real Oracle `activation_pending` | synthetic poll/send, duplicate/cursor/fault matrix and fixture screenshot; no real account claim |
| AC-010 | non-activation runtime/crash Oracle passed; real Oracle `activation_pending` | App Server success/crash/overload/approval/false-success matrix; no claim of 10/10 OVH E2E with Mac offline |
| AC-056 | passed | clean missing-auth fixture continued, both real adapters classified `activation_pending`, no wait node |
| AC-065 | passed for P0.4 scope | loopback enforcement, metadata-only auth probes and final secret scan report P0=0/P1=0 |

The TaskPack completion rule permits CB-030 to pass because every claimed
non-activation Oracle has executable evidence and the unavailable real items
are reported exactly as `activation_pending`, never inferred as verified.

## Executed verification

- WeChat simulator login, poll/send, candidate cursor, replay, duplicate
  acknowledgement, unknown outcome, out-of-order and deterministic fault
  fixtures;
- Codex simulator handshake, thread/turn, progress, approval, completion,
  retryable/terminal error, interrupt, overload, false-success,
  late/duplicate event and crash/reconnect fixtures;
- simulator contract: 4/4 passed, 0 failed;
- existing application regression: type/check passed; 155/155 tests passed;
- exact pinned CLI started on an ephemeral loopback port with an empty
  temporary `CODEX_HOME`; its unauthenticated `/readyz` returned HTTP 200 and
  the process/temp state were removed without external requests;
- clean missing-auth authentication fixture passed without external access;
- local and authorized OVH metadata-only probes completed with no credential
  values and no remote persistent write;
- all seven secret-pattern families were exercised independently after fixing
  the prior literal-word-boundary false-negative defect;
- scope, identity, external-adapter, Access-policy, CB-000
  source/license, TaskPack, DAG, traceability, no-wait and Prestage validators
  passed;
- both normalized SHA-256 package manifests and repository diff hygiene
  passed;
- historical `CB-020` revalidation passed at its exact P0.3 commit on a
  temporary compliant local branch; the initial detached-HEAD attempt correctly
  failed only the branch-name gate, then the temporary branch/worktree were
  deleted after the passing rerun;
- final secret scan loaded seven protected known-secret values, found zero
  matches/pattern hits/unreadable files and emitted no values;
- no simulator process remained after testing.

## Protocol and source disposition

The extended Codex simulator aligns its handshake, header omission and exact
WebSocket overload error with the current official App Server contract while
retaining the exact tested CLI pin `0.146.0-alpha.3.1`. The simulator extension
uses the existing locked application dependency; it adds no package, runtime
fetch or upstream relationship. The frozen source and strict dual-license
conflict treatment are unchanged.

## Residual activation inputs

The authorized OVH target does not yet contain Codex CLI/auth state or WeChat
account/session state. The consolidated commands in `auth-gates.md` are
prepared but were not executed. A later activation must independently prove a
real `ping`/`pong` channel round trip and 10/10 OVH E2E with the Mac offline.

`CB-040 / P0.5` and all later tasks remain `not_started`.
