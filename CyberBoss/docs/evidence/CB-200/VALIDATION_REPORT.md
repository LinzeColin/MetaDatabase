# CB-200 Validation Report

- Run: `P2.1 / CB-200`
- Task state: `passed`
- Stage 2 task progress: `1/5`
- PG-2: `not_started`
- CB-210: `not_started`
- Implementation/release:
  `6c8d7a1092a1f4d10a7f512ebe9abd2380aa2287`
- Target: same pseudonymous authorized asset as CB-010 through PG-1
- Runtime state source: transient synthetic acceptance state only
- Real Codex/WeChat/canonical sync: `activation_pending`
- Remote publication: `none`

## Result

The clean implementation commit adds an additive SQLite schema version 2,
WAL/FULL/foreign-key/busy-timeout initialization, strict job transition
guards, immutable job events, stable HMAC identifiers, transactional replay
deduplication, optimistic state versions, AES-256-GCM active-payload storage,
TTL redaction, and repository-only outbox/sync/service-state APIs.

Local App regression passed 185/185. Runtime-spool acceptance covered clean
and existing-v1 migrations, a legacy-v1 reader after v2, 10,000 stable-ID
fixtures, 10,000 transition attempts, 32 concurrent inserters, five real child
process crash cut points, raw-SQL illegal-transition rejection, canonical
reconciliation and live DB/WAL/SHM plaintext/key scanning.

The corrected exact artifact contained three files: complete Corresponding
Source, a machine-readable manifest and SHA-256 checksums. Target check mode
was write-free. Two applies and one independent verify passed against the
same commit; the immutable candidate passed the complete 185-test App suite
and synthetic acceptance. The target's `current` pointer and controlled
workspace did not move, the service never started, and the canonical runtime
database was never created.

After evidence retrieval, candidate-specific staging, environment, incoming
files, bootstrap, synthetic key and acceptance DB/WAL/SHM files were removed.
The exact immutable candidate remains retained but inactive. Final service
state is disabled/inactive with zero CyberBoss process, listener and incoming
entry.

## Preserved execution corrections

Non-passing attempts are retained rather than rewritten as success:

1. The first 32-worker concurrency run produced two constructor errors because
   every connection repeated `PRAGMA journal_mode=WAL`. Initialization was
   changed to read the mode first and set WAL only when creating the database;
   the full 185/185 suite then passed.
2. The first target bootstrap used `/run`, whose target mount denied execution.
   It stopped before candidate or staging creation. The transient bootstrap
   moved to the exact authorized CyberBoss state directory and passed.
3. The first candidate used superseded local commit
   `5180bc00de5e29069189c01d7f60ed960ac31cd3`. Two applies, verify and 185
   candidate tests passed, but acceptance stopped before evidence because its
   database discovery expected literal `runtime.db*` names while the target
   used a commit-bound filename. Output remained empty; acceptance DB/WAL/SHM
   and key material were removed. The candidate, staging and incoming files
   were removed only after exact manifest verification. The unpublished local
   implementation commit was amended to the corrected commit recorded above.
4. The first corrected archive transfer contained four unmanifested macOS
   metadata files in addition to the required three artifacts. The inventory
   gate rejected it before candidate or staging creation. Incoming was removed
   and retransferred with metadata generation disabled and an explicit
   three-file inventory; checksums passed.
5. One remote inventory verification command failed because of local shell
   quoting. Independent readback proved an exact three-file inventory and
   valid checksums; no candidate or staging existed at that point. The
   corrected orchestration then completed in full.
6. The first post-closure read-only process count matched the audit's own
   `awk` command line and reported one process even though systemd MainPID and
   listeners were zero. It made no target mutation. Excluding the audit
   process itself produced zero CyberBoss processes and the complete final
   target-state audit passed.

The pre-closure `--final` validator is deliberately run before the closure
commit and must fail only `closure_parent`. That expected fail-closed result is
retained in `validation.txt`; the authoritative pass is rerun from the clean
one-child closure commit.

All removed material is recoverable from the exact local implementation
commit and artifact manifest.

## Compliance and security boundary

Original App/vendor source, license files, notices and the unresolved
whereabouts conflict record are preserved. The conservative expression remains
`AGPL-3.0-only AND GPL-3.0-only`, and
`upstream_clarification_received=false`.

P0/P1 findings, secret-value hits, plaintext DB/WAL/SHM hits, encryption-key
hits, real credential reads, provider writes and Private-MetaDatabase
operations are all zero. No target address or credential value is stored in
this evidence.

## Acceptance

- AC-003 durable local-before-execution spool: `passed`.
- AC-016 replay/deduplication and deterministic identifiers: `passed`.
- AC-055 encrypted active payload plus TTL redaction: `passed`.
- AC-063 crash consistency and canonical reconciliation: `passed`.
- Only CB-200 changes task state.
- CB-210 and every later task, plus PG-2–PG-5, remain `not_started`.
- Scheduler, channel polling, outbox worker and real canonical sync were not
  integrated in this Run.
- No branch, PR, tag, release or push exists remotely.

The fail-closed repository validator result is recorded in `validation.txt`.
