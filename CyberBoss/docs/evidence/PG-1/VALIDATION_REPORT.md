# PG-1 Validation Report

- Date: `2026-07-27`
- Frozen input: `4020f07bc086ab9827ab97ddf295927075189a9f`
- Gate state: `passed`
- P2.1 / CB-200: `not_started`
- Decision: `PASS`

## Independent results

- Stage 0 and Stage 1 are 10/10 tasks passed. All 20 tasks from CB-200 onward
  remain `not_started`.
- The five Stage 1 evidence trees exactly match the frozen input. Their five
  implementation commits, five closure commits and 17 Task-to-Acceptance
  references covering 15 unique Acceptance IDs validate.
- CB-100 non-root systemd, permissions, 100 restart and 100 singleton Oracles;
  CB-110 pinned Node/Codex, loopback App Server and disabled Claude adapter;
  CB-120 bounded workspace/no-clone identity boundary; and CB-130 one-cgroup
  supervised process family remain executable-evidence backed.
- A fresh isolated matrix passed 15/15 commands: simulator contract 5/5, App
  Walking Skeleton static 4/4, live process chain 1/1, root CB-140 contract
  5/5, root CB-130 contract 5/5, App check and full App regression 175/175.
- Frozen CB-140 target evidence records simulator E2E 10/10, input-policy
  Runtime deltas 0/1/0, 20/20 latency samples at P50 372 ms/P95 378 ms and a
  complete correlated chain without raw message/result/identity fields.
- Mac source/config/process/connector dependency and non-loopback Runtime
  connection/listener counts are zero. Prior operator scans found
  8765/8780/19080 externally unreachable three times each.
- The credential-free matrix removed seven credential-related environment
  keys, used a temporary HOME, empty CODEX_HOME and empty WeChat state.
  Codex and WeChat both returned `activation_pending`; external mutation and
  credential value emission were zero.
- Secret scan result=`passed`; forbidden/known-secret hits, P0/P1 and
  unreadable files are all zero.
- DAG=30 tasks/6 stages, traceability=53/53, no-wait real-time-soak,
  credential-wait and fixed-sleep hits=0, TaskPack and Prestage passed.
- The pre-commit final validator reported exactly `closure_parent` and
  `worktree_dirty`; these are the expected fail-closed topology results before
  the single Gate closure commit and are not counted as a Gate pass.
- The first post-commit final validator passed all Gate, scope, topology,
  evidence and credential-free checks from the single closure commit.
- A fresh strict-known-host, key-only target metadata probe found the CB-140
  candidate retained inactive. Service is disabled/inactive; process,
  listener, staging, incoming and token counts are zero; `current` and
  workspace remain unchanged.
- Read-only remote/GitHub checks found branch/PR/tag/release counts all zero.
  No push, PR, tag, release or other external object mutation succeeded.

## Preserved non-passing probe attempts

- The first target read-only shell treated the normal no-process exit code as
  a `pipefail` failure and stopped before evidence output. It made no target
  mutation and is not counted as a pass. The corrected probe normalized only
  the zero-result query and retained every expected-zero assertion.
- The first PR query omitted an explicit `GET`; the service rejected it
  because creation fields were missing. The final explicit read-only query
  confirmed no PR exists. No GitHub object was created, and the rejected query
  is not counted as a pass.

## License and claim boundaries

- The unresolved source metadata/file-license conflict remains governed by
  `AGPL-3.0-only AND GPL-3.0-only`. Original source, licenses and conflict
  records remain preserved; `upstream_clarification_received=false`.
- Real Codex and WeChat remain `activation_pending`. This Gate does not claim
  a real authenticated turn, QR scan, account message or AC-001/AC-010 real
  verification.
- The deterministic fixture screenshot remains explicitly non-real and is not
  used as browser-captured WeChat proof.
- The Stage 1 bridge boundary is not the Stage 2 SQLite WAL spool. This Gate
  does not claim `CB-200`, durable crash recovery or canonical fact sync.
- No Private-MetaDatabase operation, provider write, public Runtime, `current`
  switch, new repository or GitHub publication was performed.

## Decision

`PG-1=PASS`. This independent Gate starts no additional phase. The next
eligible Run is exactly `P2.1 / CB-200`, under a separate Run Contract.
