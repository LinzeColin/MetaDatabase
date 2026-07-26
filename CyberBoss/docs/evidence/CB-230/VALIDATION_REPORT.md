# CB-230 Validation Report

- Date: 2026-07-27
- Task: `P2.4 / CB-230`
- Task state: `passed`
- Implementation commit:
  `1b3e338847d8819869a5e12091f25b5463a8d3be`
- Frozen base:
  `916651854a6402254724c885398060b2e267e496`
- CB-240: `not_started`
- PG-2: `not_started`
- Publication: none

## Result

AC-020、AC-021、AC-022、AC-024、AC-025 and AC-062 have executable local and
candidate-only target evidence. Accepted acknowledgements are staged before
cursor commit. Final result、terminal error and cancelled replies are staged
before provider dispatch. Active payload and target references use
AES-256-GCM; ordinary row/event/evidence views contain no plaintext target or
reply.

Stable Unicode chunk、dedupe、logical-message and provider client identity
survive restart. Existing schema-v1 active outbox rows are deterministically
backfilled before a v4 claim. The provider API accepts one bounded chunk and
must return a structured matching confirmation; a void or unknown outcome
cannot become confirmed.

Virtual provider sequence 503→503→200 used attempts `3`, delays
`1000/2000 ms` and real wait calls `0`. Replaying one outbox key 1,000 times
created one durable row; confirmed delivery count: `1`. The 13,300-code-point
result became four ordered chunks below the provider limit, and its
reconstructed SHA-256 equals the source.

The four recovery cases cover pending, claimed-before-dispatch,
provider-returned-before-confirmation-commit and
confirmation-committed-before-crash. Pre-dispatch work retries safely.
Post-dispatch unknown becomes terminal ambiguous/manual reconciliation;
unknown dispatch auto replay: `0`. A confirmation-commit crash reconciles the
job to `replied` without a second provider call. A job never reaches `replied`
before all final chunks are confirmed.

401 is terminal. Raw provider detail is not forwarded. Only a refreshed
context can stage a separate fixed, redacted re-login advice row.

## Verification

- Local and target App regression: `227/227`.
- Local CB-230 root contract: `7/7`.
- Local and target executable outbox suite: `37/37`.
- Exact artifacts: four files; local and target SHA-256 gates passed.
- Target installer: write-free checks, two applies and one independent verify
  passed; the second apply returned `verified` without changing the candidate.
- Candidate: immutable/inactive; mutable and cache entry counts are zero.
- Security: DB/WAL/SHM plaintext hits `0`; encryption-key hits `0`; real
  credential reads、provider writes and Private-Database operations are zero.
- Final target: frozen `current` and workspace unchanged; workspace clean;
  service disabled/inactive; process/listener/incoming counts zero; canonical
  `runtime.db` absent.
- Cleanup: exact CB-230 staging、env、incoming、transfer and synthetic runtime
  removed; inactive exact candidate retained.
- GitHub: remote branch、implementation ref、PR、tag and release counts are all
  zero; no push was performed.

## Compliance and non-claims

Complete Corresponding Source, original source/licenses and the unresolved
conflict record are preserved. The conservative expression remains
`AGPL-3.0-only AND GPL-3.0-only`, and
`upstream_clarification_received=false`. No upstream support, sync,
clarification or endorsement is claimed.

No real Codex/WeChat credential、provider、Runtime or
Private-MetaDatabase operation was used. Real adapter activation and canonical
sync remain `activation_pending`. CB-240 owns canonical sync/reconcile;
CB-340 owns full operational self-heal. PG-2 was not executed.

## Preserved corrections

Non-passing orchestration is retained rather than rewritten:

1. Final code audit found that legacy active outbox rows could lack v4 stable
   identity. A deterministic pre-claim backfill and existing-v1 regression
   closed the gap before the implementation commit.
2. The first post-build checksum inherited an unsupported locale. The unchanged
   artifacts passed under the C locale.
3. Target discovery rejected an unsupported look-around expression and a
   failing PCRE locale attempt; a known-host comment was also initially counted.
   The final portable parser required the exact pseudonymous target hash and
   three non-comment host keys. These attempts made no target mutation.
4. Direct SFTP could not traverse the protected incoming parent. Four exact
   files were instead checksum-verified in an owner-only transient directory
   and installed under root. A subsequent ordinary-user `cd` check also
   stopped on the intended protection; the sudo checksum passed. Service never
   started and the upload directory was removed.
5. The first cleanup precondition could not traverse root-controlled paths as
   the ordinary SSH identity and stopped before deletion. The corrected
   sudo-based exact-path preflight locked the report hash and removed only
   staging/env/incoming/synthetic runtime.
6. A read-only release-list query requested an unsupported field. The
   supported tag query plus exact remote branch/ref/tag and PR checks passed
   with zero publication.

CB-240 and every later task, plus PG-2–PG-5, remain `not_started`.
