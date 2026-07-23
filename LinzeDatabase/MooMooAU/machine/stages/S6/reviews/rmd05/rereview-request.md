# RMD-05 isolated Stage 6 remediation re-review request

Review exactly the immutable remediation target and the candidate-bound execution receipt below.
This is a read-only independent assurance re-review. It is not an implementation task, a protected
Oracle run, a production-readiness approval, or permission to infer remote behavior.

## Immutable target and artifacts

- Repository: `MetaDatabase`, project path `LinzeDatabase/MooMooAU`
- Baseline commit: `2b8625a83e69093b9dce989f4eb964556e1b5fa2`
- Candidate commit: `e456bdae5d7fbca69fdd2b2f605c515d4584377c`
- Candidate tree: `15625ffd5526a45aafa33d9c0b19f3b578ef5723`
- Original request path: `machine/stages/S6/reviews/rmd05/request.md`
- Original request SHA-256: `35247bddc79077b568509097cb9285e9a05299180a2833c8238b1cadac6c4e93`
- Original Sol reply path: `machine/stages/S6/reviews/rmd05/initial/gpt-5.6-sol.reply.json`
- Original Sol reply SHA-256: `843e84445731e02c02f8e02bbcc8cd2091f428387356efeb0ae4dbe2120fc0bd`
- Original Terra reply path: `machine/stages/S6/reviews/rmd05/initial/gpt-5.6-terra.reply.json`
- Original Terra reply SHA-256: `646786d09804730e98c71652c1ad98fede5d697c17c0a1d1ee6a0c81283ee9a3`
- Execution receipt path: `machine/stages/S6/reviews/rmd05/execution-receipt.json`
- Execution receipt SHA-256: `aed2a3dd2d5df19536e49d963755e229b0d4ac569365fb74f58df99fc72fd1fc`
- Receipt scope: `LOCAL_SYNTHETIC_ONLY`; 15 unique candidate commands report exit code zero.
- Required dimensions: `SCOPE`, `EVIDENCE_QUALITY`, `FAILURE_HONESTY`, `ROLLBACK`

The invocation supplies the SHA-256 of this re-review request. Bind that exact digest into the
reply. Treat a digest, target, path, command set or artifact mismatch as `FAIL`.

## Isolation and data boundary

1. Inspect only Git objects reachable through the baseline/candidate pair, this exact request, the
   exact execution receipt above, and the three original request/reply artifacts at their candidate
   Git-object versions. Do not inspect any other current-worktree file.
2. Do not read environment variables, credentials, user directories, local configuration, Gmail,
   private GitHub state, network resources, or files outside this closed set.
3. Do not execute tests or validators, write files, invoke network tools, spawn another agent,
   contact another reviewer, or use another model. Static inspection plus the immutable receipt is
   the entire evidence boundary.
4. Do not inspect either legacy file directly under `machine/stages/S6/reviews/`; they are the
   obsolete assertion-only records identified by the initial review and are excluded from the
   reviewed diff. Fresh v2 provenance records are necessarily assembled only after both exact
   re-review replies exist.
5. The target and receipt must contain only code, contracts and synthetic/local evidence. If real
   or sensitive data appears, stop and return `FAIL` without reproducing that value.

The exact full-diff command is:

```text
git diff --no-ext-diff --unified=80 2b8625a83e69093b9dce989f4eb964556e1b5fa2 e456bdae5d7fbca69fdd2b2f605c515d4584377c -- . ':(exclude)LinzeDatabase/MooMooAU/machine/stages/S6/reviews/gpt-5.6-sol.json' ':(exclude)LinzeDatabase/MooMooAU/machine/stages/S6/reviews/gpt-5.6-terra.json'
```

Use `git show e456bdae5d7fbca69fdd2b2f605c515d4584377c:<path>` only for a path present
in that diff. The execution receipt and this request are the only allowed direct worktree reads.

## Initial adverse findings that must remain traceable

For `gpt-5.6-sol`, the final reply must include all three IDs below. For `gpt-5.6-terra`, it must
include `RMD05-001`. Each applicable initial ID must be `RESOLVED` with an evidence-based
`resolution_ref`, or remain `OPEN` with `required_fix`. Do not rename, omit or silently supersede an
initial ID.

- `RMD05-EVIDENCE-001`: review records did not bind candidate commit/tree/request or prove fresh,
  distinct model executions.
- `RMD05-EVIDENCE-002`: local PASS claims were assertion-only and lacked candidate-bound command,
  exit-status, tool-version and output-digest evidence.
- `RMD05-CAPACITY-001`: capacity authorization omitted prospective repository/LFS/object/release
  deltas and could authorize a write that crossed a limit.
- `RMD05-001`: `PRODUCTION_RUN` bypassed UNKNOWN/RED capacity and KILL-007.

## Remediation map to verify, not assume

- Candidate-bound review/evidence chain:
  `machine/stages/S6/schemas/review-provenance-v2.schema.json`,
  `machine/stages/S6/schemas/review-reply-v2.schema.json`,
  `machine/stages/S6/schemas/stage6-evidence-v2.schema.json`,
  `machine/stages/S6/schemas/execution-receipt-v1.schema.json`,
  `machine/tools/validate_assurance_reviews.py`,
  `machine/stages/S6/tools/validate_stage6.py`, and
  `tests/remediation/test_rmd05.py`.
- Candidate-bound local gate capture:
  `machine/tools/capture_candidate_gates.py` plus the exact receipt named above. Check target/tree,
  command closure, exit codes, tool versions, raw-output metadata, sanitized-output digests,
  no local-path/sensitive leakage, zero remote writes, and the local/synthetic scope limitation.
- Prospective capacity and operation gating:
  `src/moomooau_archive/capacity.py`, `src/moomooau_archive/operation_gate.py`,
  `src/moomooau_archive/ga_runtime.py`, `src/moomooau_archive/canary_runtime.py`,
  `src/moomooau_archive/blue_green_runtime.py`,
  `src/moomooau_archive/gmail_sync_checkpoint.py`,
  `src/moomooau_archive/timeline_snapshot.py`, and the affected Stage 6/7 tests.
- `PRODUCTION_RUN` and KILL-007 closure:
  `src/moomooau_archive/operation_gate.py`, `src/moomooau_archive/kill_switch.py`,
  `tests/tasks/test_t0607.py`, and `tests/tasks/test_t0704.py`.

The final re-review reply itself, its hash-bound v2 provenance wrapper, v2 task evidence, and final
package/status metadata cannot be members of the commit they attest without circularity. After the
two replies are preserved, the candidate's assurance validator is intended to require the exact
request/reply/receipt hashes, exact model family and platform task IDs, distinct executions, closure
of every initial finding, candidate ancestry, a clean final worktree, and no post-review drift in
runtime, tests, Stage 6 schemas/tools, workflows or the assurance validator. Evaluate that closure
mechanism. If this post-candidate mechanical closure is insufficient or bypassable, return `FAIL`.

## Decision rule

- Return `PASS` only if all four dimensions pass, every applicable initial finding is resolved,
  and there are no open findings.
- Return `FAIL` for any defect, unsupported claim, scope escape, unverifiable evidence, unsafe
  rollback, stale binding, or uncertainty material to a dimension. A new finding must be `OPEN`
  with a stable ID and `required_fix`.
- Do not infer remote CI, protected Oracle behavior, real Gmail/private-repository behavior,
  production health, final AC-033, deployment, publication, or readiness for RMD-06/RMD-07.
- Repository hashes and Codex task IDs are not signed third-party attestations; their platform
  execution identity remains auditable only through the retained Codex thread audit log.

## Exact response contract

Return exactly one single-line JSON object, without Markdown fences or text before/after it. It must
validate against `machine/stages/S6/schemas/review-reply-v2.schema.json` and have this shape:

```json
{"schema_version":"moomooau.independent-review-reply.v2","target":{"baseline_commit":"2b8625a83e69093b9dce989f4eb964556e1b5fa2","candidate_commit":"e456bdae5d7fbca69fdd2b2f605c515d4584377c","candidate_tree":"15625ffd5526a45aafa33d9c0b19f3b578ef5723","request_sha256":"<digest supplied by invocation>"},"review_mode":"READ_ONLY_INDEPENDENT","verdict":"PASS or FAIL","dimensions":[{"id":"SCOPE","status":"PASS or FAIL","evidence_refs":["path:line or receipt field"],"rationale":"concise evidence-based rationale"},{"id":"EVIDENCE_QUALITY","status":"PASS or FAIL","evidence_refs":["path:line or receipt field"],"rationale":"concise evidence-based rationale"},{"id":"FAILURE_HONESTY","status":"PASS or FAIL","evidence_refs":["path:line or receipt field"],"rationale":"concise evidence-based rationale"},{"id":"ROLLBACK","status":"PASS or FAIL","evidence_refs":["path:line or receipt field"],"rationale":"concise evidence-based rationale"}],"findings":[{"id":"applicable initial ID or new stable ID","severity":"BLOCKING or HIGH or MEDIUM or LOW","status":"RESOLVED or OPEN","finding":"finding or closure statement","evidence_refs":["path:line or receipt field"],"resolution_ref":"required for RESOLVED; omit for OPEN","required_fix":"required for OPEN; omit for RESOLVED"}],"limitations":["what this local static re-review does not prove"],"sensitive_data_observed":false,"production_or_protected_claimed":false,"summary":"concise final conclusion"}
```
