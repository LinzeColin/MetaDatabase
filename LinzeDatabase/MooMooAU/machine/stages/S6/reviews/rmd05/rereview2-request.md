# RMD-05 final isolated Stage 6 remediation re-review request

Review exactly the immutable final remediation candidate, the preserved adverse history, and the
candidate-bound execution receipt below. This is a read-only independent assurance re-review. It
is not an implementation task, protected Oracle run, production-readiness approval, deployment, or
permission to infer remote behavior.

## Immutable final target and artifacts

- Repository: `MetaDatabase`, project path `LinzeDatabase/MooMooAU`
- Baseline commit: `2b8625a83e69093b9dce989f4eb964556e1b5fa2`
- Final candidate commit: `d3c1d9144cd5a063662a15d85c93f5a589389cf0`
- Final candidate tree: `1d558f73ff2efdcd6f27dce635fa130a12a0fd0b`
- Original request: `machine/stages/S6/reviews/rmd05/request.md`, SHA-256
  `35247bddc79077b568509097cb9285e9a05299180a2833c8238b1cadac6c4e93`
- Original Sol FAIL: `machine/stages/S6/reviews/rmd05/initial/gpt-5.6-sol.reply.json`,
  SHA-256 `843e84445731e02c02f8e02bbcc8cd2091f428387356efeb0ae4dbe2120fc0bd`
- Original Terra FAIL: `machine/stages/S6/reviews/rmd05/initial/gpt-5.6-terra.reply.json`,
  SHA-256 `646786d09804730e98c71652c1ad98fede5d697c17c0a1d1ee6a0c81283ee9a3`
- First re-review request: `machine/stages/S6/reviews/rmd05/rereview-request.md`, SHA-256
  `e3fa55cb020a66dd2f17915f4015f0e62942e0aef1c93bc6152f193933fb85f4`
- First re-review receipt: `machine/stages/S6/reviews/rmd05/execution-receipt.json`, SHA-256
  `aed2a3dd2d5df19536e49d963755e229b0d4ac569365fb74f58df99fc72fd1fc`
- First Sol FAIL: `machine/stages/S6/reviews/rmd05/rereview1/gpt-5.6-sol.reply.json`,
  SHA-256 `5f1072d2e2e6525897fa5dca67bfb081e149bb35e5973abf9832c8d7bb417461`
- First Terra FAIL: `machine/stages/S6/reviews/rmd05/rereview1/gpt-5.6-terra.reply.json`,
  SHA-256 `bb2a72bf7c63425aca444eaf407a566de2d6f6e67f9a23dde295fc2f344fa718`
- Final execution receipt: `machine/stages/S6/reviews/rmd05/execution-receipt2.json`, SHA-256
  `e6d076632bcc36b410a04765bd4d3ebc69af16849266b3da429b7f0eb4cc9380`
- Final receipt scope: `LOCAL_SYNTHETIC_ONLY`; 15 unique candidate commands report exit zero.
- Required dimensions: `SCOPE`, `EVIDENCE_QUALITY`, `FAILURE_HONESTY`, `ROLLBACK`

The invocation supplies the SHA-256 of this final re-review request. Bind that exact digest into
the reply. Treat any digest, target, path, command-set, attempt-history, or artifact mismatch as
`FAIL`.

## Isolation and data boundary

1. Inspect only Git objects reachable through the baseline/final-candidate pair, this exact
   request, and the exact final execution receipt. The original and first-re-review artifacts are
   members of the final candidate and may be read only with the allowed `git show` operation.
2. Do not read any other current-worktree file, environment variable, credential, user directory,
   local configuration, Gmail state, private GitHub state, network resource, or out-of-scope file.
3. Do not execute tests or validators, write files, invoke network tools, spawn another agent,
   contact another reviewer, or use another model. Static Git-object inspection plus the immutable
   final receipt is the complete evidence boundary.
4. Do not inspect either legacy file directly under `machine/stages/S6/reviews/`; they are obsolete
   assertion-only records and are excluded from the diff. Final v2 provenance records are
   necessarily assembled only after both exact final replies exist.
5. If real or sensitive data appears, stop and return `FAIL` without reproducing that value.

The exact full-diff command is:

```text
git diff --no-ext-diff --unified=80 2b8625a83e69093b9dce989f4eb964556e1b5fa2 d3c1d9144cd5a063662a15d85c93f5a589389cf0 -- . ':(exclude)LinzeDatabase/MooMooAU/machine/stages/S6/reviews/gpt-5.6-sol.json' ':(exclude)LinzeDatabase/MooMooAU/machine/stages/S6/reviews/gpt-5.6-terra.json'
```

Use `git show d3c1d9144cd5a063662a15d85c93f5a589389cf0:<path>` only for a path
present in that diff. The final receipt and this request are the only allowed direct worktree
reads.

## Findings that must remain traceable

For `gpt-5.6-sol`, the final reply must include `RMD05-EVIDENCE-001`,
`RMD05-EVIDENCE-002`, `RMD05-CAPACITY-001`, and `RMD05-CLOSURE-001`. For
`gpt-5.6-terra`, it must include `RMD05-001` and `RMD05-CLOSURE-001`. Every applicable ID must be
`RESOLVED` with an evidence-based `resolution_ref`, or remain `OPEN` with `required_fix`. Do not
rename, omit, overwrite, or silently supersede any ID.

- `RMD05-EVIDENCE-001`: candidate/request/reply/model/task identities were not bound.
- `RMD05-EVIDENCE-002`: local PASS claims lacked candidate-bound command results and digests.
- `RMD05-CAPACITY-001`: projected write deltas were absent from capacity authorization.
- `RMD05-001`: `PRODUCTION_RUN` bypassed UNKNOWN/RED capacity and KILL-007.
- `RMD05-CLOSURE-001`: first re-review found post-review drift protection omitted the production
  workflow and evidence-capture tool, allowing a later commit to bypass final closure.

## Final remediation map to verify, not assume

- The first two adverse replies and their request/receipt are preserved byte-for-byte in the final
  candidate and fixed by hash in `machine/tools/validate_assurance_reviews.py` and
  `tests/tasks/test_t0606.py`.
- `machine/stages/S6/schemas/review-provenance-v2.schema.json` now requires exactly three ordered
  attempts per family: `INITIAL`, `REREVIEW_ADVERSE`, `REREVIEW_FINAL`. Both rereviews carry their
  own receipt binding; all six platform task IDs must be distinct; final closure must include all
  original and adverse open finding IDs.
- `machine/tools/validate_assurance_reviews.py` now rejects post-candidate changes under every
  workflow, container, Stage 6/7 contract/schema/tool surface, evidence-capture and assurance
  validator, dependency/schema/runtime/test surface listed in `PROTECTED_AFTER_REVIEW_PREFIXES`.
  Final review request/receipt/reply/provenance and package/status evidence remain addable by design.
- `tests/remediation/test_rmd05.py` uses real temporary Git repositories to prove that a later
  change to `.github/workflows/moomooau-production.yml` or
  `machine/tools/capture_candidate_gates.py` blocks closure, while a later documentation-only
  update does not.
- `.github/workflows/moomooau-stage6-model-assurance.yml` now triggers on the assurance schemas,
  Stage 6 validator, capture tool, assurance validator, and RMD-05 regression tests.
- `machine/tools/validate_stage6_secret_scan.py` treats receipts as structured evidence: it
  excludes their expected SHA-256 fields from generic entropy heuristics but independently blocks
  explicit age private-key, PEM private-key, OAuth refresh-token, GitHub-token, and Google-key
  patterns. The final receipt reports zero secret/publication findings.
- The previous capacity, KILL-007, and candidate-bound execution/provenance remediation remains in
  `src/moomooau_archive`, Stage 6/7 tests, the four v2/v1 schemas, the capture tool, the assurance
  validator, and both receipts. Re-check it for regression.

The final replies, their hash-bound provenance wrappers, v2 task evidence, and v1.0.5
package/status metadata cannot be members of the commit they attest without circularity. After the
two replies are preserved, the candidate's assurance validator is intended to require all three
attempts, exact request/reply/receipt hashes, exact model family and task IDs, distinct executions,
closure of every adverse finding, final candidate ancestry, a clean final worktree, and zero drift
in protected surfaces. If this post-candidate closure remains insufficient or bypassable, return
`FAIL`.

## Decision rule

- Return `PASS` only if all four dimensions pass, every applicable original/adverse finding is
  resolved, and there are no open findings.
- Return `FAIL` for any defect, unsupported claim, scope escape, unverifiable evidence, unsafe
  rollback, stale binding, incomplete adverse history, or material uncertainty. A new finding must
  be `OPEN` with a stable ID and `required_fix`.
- Do not infer remote CI, protected Oracle behavior, real Gmail/private-repository behavior,
  production health, final AC-033, deployment, publication, or RMD-06/RMD-07 readiness.
- Repository hashes and Codex task IDs are not signed third-party attestations; their platform
  execution identity remains auditable only through the retained Codex thread audit log.

## Exact response contract

Return exactly one single-line JSON object, with no Markdown fences or text before/after it. It must
validate against `machine/stages/S6/schemas/review-reply-v2.schema.json` and have this shape:

```json
{"schema_version":"moomooau.independent-review-reply.v2","target":{"baseline_commit":"2b8625a83e69093b9dce989f4eb964556e1b5fa2","candidate_commit":"d3c1d9144cd5a063662a15d85c93f5a589389cf0","candidate_tree":"1d558f73ff2efdcd6f27dce635fa130a12a0fd0b","request_sha256":"<digest supplied by invocation>"},"review_mode":"READ_ONLY_INDEPENDENT","verdict":"PASS or FAIL","dimensions":[{"id":"SCOPE","status":"PASS or FAIL","evidence_refs":["path:line or receipt field"],"rationale":"concise evidence-based rationale"},{"id":"EVIDENCE_QUALITY","status":"PASS or FAIL","evidence_refs":["path:line or receipt field"],"rationale":"concise evidence-based rationale"},{"id":"FAILURE_HONESTY","status":"PASS or FAIL","evidence_refs":["path:line or receipt field"],"rationale":"concise evidence-based rationale"},{"id":"ROLLBACK","status":"PASS or FAIL","evidence_refs":["path:line or receipt field"],"rationale":"concise evidence-based rationale"}],"findings":[{"id":"applicable original/adverse ID or new stable ID","severity":"BLOCKING or HIGH or MEDIUM or LOW","status":"RESOLVED or OPEN","finding":"finding or closure statement","evidence_refs":["path:line or receipt field"],"resolution_ref":"required for RESOLVED; omit for OPEN","required_fix":"required for OPEN; omit for RESOLVED"}],"limitations":["what this local static re-review does not prove"],"sensitive_data_observed":false,"production_or_protected_claimed":false,"summary":"concise final conclusion"}
```
