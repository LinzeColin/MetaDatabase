# RMD-05 final independent re-review request after evidence-coupling repair

Review exactly the immutable candidate and candidate-bound local receipt below. This is a
read-only independent review. Do not edit files, execute protected Oracles, invoke production
workflows, access Gmail or any private repository, request Secrets, publish, push, or infer remote
or production success from local evidence.

## Immutable target

- Repository baseline: `2b8625a83e69093b9dce989f4eb964556e1b5fa2`
- Candidate commit: `f459d504b62d4a528858dcc3321a58f8218b160f`
- Candidate tree: `2bf05a0209738a97c73535292f30aa1882a1f372`
- Final candidate receipt: `machine/stages/S6/reviews/rmd05/execution-receipt6.json`
- Receipt SHA-256: `9c1b087a4d24f49069305b1892553f6ab7d579892cc71bfa77ff0e102d143650`
- Receipt scope: `LOCAL_SYNTHETIC_ONLY`; 15 unique zero-exit commands; protected/production
  execution false; remote writes zero; ephemeral image removed.

The receipt and this request are intentionally post-candidate review inputs. Inspect protected
source with `git show` or a detached checkout of the candidate; do not treat the candidate's old
top-level provenance wrappers as final authority. The invocation supplies the SHA-256 of this
exact request. Bind the reply target to that request hash, the baseline, candidate commit, and
candidate tree above.

## Required review dimensions

Return one result for each exact ID: `SCOPE`, `EVIDENCE_QUALITY`, `FAILURE_HONESTY`, and
`ROLLBACK`. A final `PASS` is permitted only if all four dimensions pass and every finding in this
reviewer's complete seven-attempt history is explicitly `RESOLVED`. Otherwise return `FAIL` and at
least one `OPEN` finding with a concrete required fix.

## Preserved history to verify

The repository must preserve all earlier artifacts byte-for-byte and implement seven ordered
attempts per model family with fourteen distinct platform task IDs across the two families:

1. `INITIAL`: original candidate/request and two independent FAIL replies.
2. `REREVIEW_ADVERSE`: receipt1 and two FAIL replies opening `RMD05-CLOSURE-001`.
3. `REREVIEW_SUPERSEDED`: receipt2 and two PASS replies retained as superseded history.
4. `REREVIEW_TRANSITION_ADVERSE`: receipt3 and two FAIL replies. Terra opened
   `RMD05-CLOSURE-002`; Sol opened `RMD05-CLOSURE-003`.
5. `REREVIEW_OUTPUT_INTEGRATION_SUPERSEDED`: candidate
   `ac46f96890103a142af724ca1bbd13fa81f3ef3c`, tree
   `9f649c9044ce19447fbfde3f2aae99e0a4d23c4c`, request4 SHA-256
   `62c9291f5ea6ef39a1123a4c96adaf7e3a58a2a69a5b36369818e99e381e17be`, receipt4 SHA-256
   `3359865176269e7eb1da39aa38d6fc9e8230e530f8d02a25f3d8b5f4a3057fc2`, and two PASS replies
   under `final2/`. These remain superseded because output integration exposed
   `RMD05-CLOSURE-004`.
6. `REREVIEW_EVIDENCE_COUPLING_ADVERSE`: candidate
   `c9ebf210e3397cd1626faa959aed3b3ddfdc66a1`, tree
   `ddd43a4837bb1766ae4b3c6f8b3ae262edeae151`, request5 SHA-256
   `45e531415d8176d599f7573f22770b5110211a41c724f524fccd9dbc590dc2d7`, receipt5 SHA-256
   `407519737d85e754ad6b4b9fdc4cbb0f2a182b5c60d9f9b90bd8a71db8525465`, a Sol FAIL reply and
   Terra PASS reply under `rereview5/`. Preserve the mixed verdicts exactly. Sol opened
   `RMD05-CLOSURE-005` because CLOSED could still accept Stage 6 v1 pre-closure evidence.
7. `REREVIEW_FINAL`: this request, receipt6, and the fresh independent reply.

The final reply must cover its model family's complete history and explicitly include
`RMD05-CLOSURE-002`, `RMD05-CLOSURE-003`, `RMD05-CLOSURE-004`, and
`RMD05-CLOSURE-005` as `RESOLVED` for a PASS. Do not erase, relabel as final, or reinterpret any
prior FAIL/PASS record.

## Newly exposed root defect and repair

The sixth review found that a final assurance PASS could select CLOSED while the eight Stage 6
task records remained `moomooau.stage6-evidence.v1`. The generic validator accepted those valid
pre-closure records, so a v1.0.5 status was not mechanically coupled to candidate-bound Stage 6 v2
evidence. Treat this as `RMD05-CLOSURE-005`.

Adversarially inspect that the candidate repairs the root cause without weakening pre-closure,
secret safety, or post-review integrity:

- `build_delivery_status.py` enforces the evidence transition: v1.0.4 PRE_CLOSURE requires all
  T0601-T0608 records to remain v1; v1.0.5 CLOSED requires all eight records to be v2 and requires
  the complete candidate-bound Stage 6 bundle validator to pass.
- `validate_evidence.py` verifies receipt6's schema/hash/subject, exactly the 15 required unique
  zero-exit command IDs, each task's exact candidate/tree/receipt/hash/command subset, the
  aggregate's exact candidate/tree/receipt/hash/full command set, and local-only zero/NOT_RUN
  observations. Missing aggregate, stale receipt hash, crossed candidate, unsupported schema, or
  incomplete command closure must fail closed.
- `validate_delivery_status.py` independently revalidates the complete v2 bundle for CLOSED;
  `machine/stages/S6/tools/validate_stage6.py` uses the same bundle authority; the v2 schema binds
  only `execution-receipt6.json`; delivery-status source digests include the aggregate evidence.
- Regression tests prove pre-closure v1 remains accepted, CLOSED with v1 is rejected, a complete
  v2 bundle passes, and missing aggregate/stale receipt/crossed candidate cases fail.
- The provenance schema and validator require seven exact ordered attempts, fourteen distinct
  task IDs, exact hashes and verdicts for the mixed sixth attempt, the same final
  candidate/request/receipt, two distinct final replies, complete finding closure, and protected
  post-candidate integrity.
- The secret gate structurally checks top-level provenance JSON for credential/private-key
  patterns before excluding deterministic Git/artifact hashes from entropy scanning; regression
  tests permit ordinary 64-hex digests but reject an age secret-key pattern.
- The complete v1.0.4/v1.0.5 delivery-state coupling remains fail closed. Missing, malformed,
  stale, incomplete, or non-PASS assurance may derive only pre-closure; clean Git-bound assurance
  is additionally required to validate the closed state.
- Package validation records seven attempts per family. Protected Oracles, Gmail, the private
  repository, production workflows, external writes, remote publication, RMD-06, RMD-07, and final
  AC-033 remain unexecuted and unclaimed.

The final top-level provenance wrappers, candidate-bound v2 task/aggregate evidence, v1.0.5
status and taskpack are deterministic post-review outputs and are not part of the immutable
candidate. Look for any path that can produce or validate CLOSED without the exact receipt6-bound
v2 bundle and final two-family provenance, any omitted/mutated history, any secret-scan bypass, or
any permitted protected-code mutation after review. Any such path is blocking.

## Reply contract

Return only one UTF-8 JSON object followed by one LF, conforming to
`machine/stages/S6/schemas/review-reply-v2.schema.json`. Use the requested model family exactly.
The reply must contain:

- the exact baseline/candidate/tree/request SHA-256 target;
- `review_mode: READ_ONLY_INDEPENDENT`;
- one verdict and exactly the four required dimensions with evidence references and rationale;
- all applicable historical and newly found findings, each `RESOLVED` or `OPEN` as required;
- honest limitations that local evidence does not prove protected Oracles, real Gmail/private
  repository behavior, production health, deployment, publication, RMD-06, RMD-07, or final
  AC-033;
- `sensitive_data_observed: false` and `production_or_protected_claimed: false` unless the review
  actually observed otherwise, in which case fail closed without reproducing sensitive content.
