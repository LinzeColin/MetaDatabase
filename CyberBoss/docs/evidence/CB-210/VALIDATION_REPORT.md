# CB-210 Validation Report

- Run: `P2.2 / CB-210`
- Task state: `passed`
- Stage 2 task progress: `2/5`
- Overall TaskPack/gate progress: `14/36` (`38.9%`)
- PG-2: `not_started`
- CB-220: `not_started`
- Implementation/release:
  `5c7b48d8f618bc83a70ebbd63eaf94b6ce6627ea`
- Target: same pseudonymous authorized asset as CB-010 through CB-200
- Runtime state source: transient synthetic acceptance state only
- Real Codex/WeChat/canonical sync: `activation_pending`
- Remote publication: `none`

## Result

The clean implementation commit separates WeChat fetch from cursor commit.
`DurableInboxCoordinator` sorts the complete raw batch, requires a stable
provider identity, records every accepted or rejected update in the encrypted
CB-200 spool, creates at most one executable job, and only then performs an
atomic compare-and-set cursor commit. Numeric cursors additionally require the
highest continuous sequence; gaps, duplicate sequences, regressions, stale
writers, symlinks and oversized cursor values fail closed.

Local syntax/config/root-contract checks passed, and the full App regression
passed 195/195. Ten named CB-210 tests passed. The standalone matrix executed
three real child-process `SIGKILL` cuts at `after_fetch_before_durable`,
`after_durable_before_cursor` and `after_cursor`. Every restart ended with one
inbox, one job, one synthetic execution, cursor committed, integrity `ok`,
accepted-but-lost `0` and duplicate executions `0`. The same provider source
replayed 1,000 times still produced one inbox, one job and one synthetic
execution. Synthetic execution is a test-harness transition and is not a claim
of an authenticated Runtime side effect.

The exact four-file artifact set contains complete Corresponding Source, an
artifact manifest, the durable-inbox matrix and SHA-256 checksums. Target
write-free check, two applies and one independent verify passed. The first
apply ran the immutable candidate's complete 195-test suite; the second apply
was idempotent. Target synthetic acceptance repeated the ten tests, crash
matrix, replay, ordering, database, reconciliation and plaintext/key scans.

After the report was read and its SHA-256 recorded, the exact CB-210 staging
tree, environment file, incoming artifact tree, bootstrap and synthetic
runtime/key state were removed. The exact candidate remains immutable and
inactive. `current` and the controlled workspace did not move; the service is
disabled/inactive, process/listener/incoming counts are zero, and the canonical
runtime database does not exist.

## Preserved execution corrections

Non-passing orchestration attempts are retained rather than rewritten:

1. The first example-config invocation omitted the documented
   `--allow-placeholders` option and returned only the two expected placeholder
   findings. The contract command was rerun with the option and passed.
2. The first protected-record parser was overly strict and stopped before SSH.
   The corrected parser verified the same pseudonymous target hash. A later
   read-only preflight stopped on the normal zero-result `pgrep` under
   `pipefail`; the corrected zero-safe count passed and made no target change.
3. macOS `shasum` could not initialize the inherited `C.UTF-8` locale after
   artifact construction. The already-built files were unchanged and all
   checksums were independently recomputed with Python.
4. Two attempted tar-stream transfer orchestrations failed fail-closed. Fresh
   readback after each showed candidate, staging, incoming and bootstrap all
   absent. They were abandoned in favor of an exact four-file `scp` staging
   flow with target-side inventory and checksum verification.
5. The first GitHub release query used a `gh api` flag belonging to standalone
   `jq`; the read-only request was rejected before mutation. The corrected
   official API query piped to `jq` and confirmed zero publication.

## Compliance and security boundary

Original App/vendor source, license files, notices and the unresolved
whereabouts conflict record remain intact. The conservative expression is
`AGPL-3.0-only AND GPL-3.0-only`, and
`upstream_clarification_received=false`.

The SSH deployment key was used only by the strict-known-host, key-only
transport and was never copied into source, artifacts, target staging output
or evidence. No Codex, WeChat, provider or Private-MetaDatabase credential was
read by the acceptance harness. Plaintext DB/WAL/SHM hits, encryption-key hits,
secret evidence hits, provider writes and Private-MetaDatabase operations are
all zero. No target address or credential value is stored here.

## Acceptance and boundary

- AC-004 durable-before-cursor: `passed`.
- AC-023 replay creates one durable job: `passed`.
- AC-063 crash recovery at all three cursor cuts: `passed`.
- Only CB-210 changed task state.
- CB-220, CB-230, CB-240 and every later task remain `not_started`.
- PG-2 through PG-5 remain `not_started`.
- Scheduler/global lease/claim recovery remains the CB-220 boundary.
- Outbox worker/retry/confirmation remains the CB-230 boundary.
- Real Runtime/WeChat activation remains `activation_pending`.
- No branch, PR, tag, release or push exists remotely.
