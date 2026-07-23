# RMD-05 final independent re-review request after output-integration repair

Review exactly the immutable candidate and candidate-bound local receipt below. This is a
read-only independent review. Do not edit files, execute protected Oracles, invoke production
workflows, access Gmail or any private repository, request Secrets, publish, push, or infer remote
or production success from local evidence.

## Immutable target

- Repository baseline: `2b8625a83e69093b9dce989f4eb964556e1b5fa2`
- Candidate commit: `c9ebf210e3397cd1626faa959aed3b3ddfdc66a1`
- Candidate tree: `ddd43a4837bb1766ae4b3c6f8b3ae262edeae151`
- Final candidate receipt: `machine/stages/S6/reviews/rmd05/execution-receipt5.json`
- Receipt SHA-256: `407519737d85e754ad6b4b9fdc4cbb0f2a182b5c60d9f9b90bd8a71db8525465`
- Receipt scope: `LOCAL_SYNTHETIC_ONLY`; 15 unique zero-exit commands; protected/production
  execution false; remote writes zero; ephemeral image removed.

The invocation supplies the SHA-256 of this exact request. Bind the reply target to that request
hash, the baseline, candidate commit, and candidate tree above.

## Required review dimensions

Return one result for each exact ID: `SCOPE`, `EVIDENCE_QUALITY`, `FAILURE_HONESTY`, and
`ROLLBACK`. A final `PASS` is permitted only if all four dimensions pass and every finding in this
reviewer's complete six-attempt history is explicitly `RESOLVED`. Otherwise return `FAIL` and at
least one `OPEN` finding with a concrete required fix.

## Preserved history to verify

The repository must preserve all earlier artifacts byte-for-byte and implement a six-attempt,
twelve-distinct-task provenance chain per model family:

1. `INITIAL`: original candidate/request and two independent FAIL replies.
2. `REREVIEW_ADVERSE`: receipt1 and two FAIL replies opening `RMD05-CLOSURE-001`.
3. `REREVIEW_SUPERSEDED`: receipt2 and two PASS replies retained as superseded history.
4. `REREVIEW_TRANSITION_ADVERSE`: receipt3 and two FAIL replies. Terra opened
   `RMD05-CLOSURE-002`; Sol opened `RMD05-CLOSURE-003`.
5. `REREVIEW_OUTPUT_INTEGRATION_SUPERSEDED`: candidate
   `ac46f96890103a142af724ca1bbd13fa81f3ef3c`, tree
   `9f649c9044ce19447fbfde3f2aae99e0a4d23c4c`, request4 SHA-256
   `62c9291f5ea6ef39a1123a4c96adaf7e3a58a2a69a5b36369818e99e381e17be`, receipt4 SHA-256
   `3359865176269e7eb1da39aa38d6fc9e8230e530f8d02a25f3d8b5f4a3057fc2`, and the two PASS
   replies under `final2/`. These replies are faithfully retained but are no longer final authority
   because post-review output integration exposed `RMD05-CLOSURE-004`.
6. `REREVIEW_FINAL`: this request, receipt5, and the fresh independent reply.

The final reply must cover its model family's complete history and explicitly include
`RMD05-CLOSURE-002`, `RMD05-CLOSURE-003`, and `RMD05-CLOSURE-004` as `RESOLVED` for a PASS.
Do not erase, relabel as final, or reinterpret any prior FAIL/PASS record.

## Newly exposed root defect and repair

Post-review generation correctly failed closed: Stage 6's dedicated validator required
`moomooau.stage6-evidence.v2`, but the shared `machine/tools/validate_evidence.py` selected only
the v1 schema. Consequently the deterministic status builder rejected every candidate-bound Stage
6 v2 task record and could not produce the closed v1.0.5 state. Treat this as
`RMD05-CLOSURE-004`.

Adversarially inspect that the candidate repairs the root cause without weakening pre-closure or
post-review integrity:

- `validate_evidence.py` accepts exactly the Stage 6 v1 pre-closure schema or v2 candidate-bound
  schema based on the declared schema version; unsupported versions remain rejected.
- `tests/remediation/test_rmd05.py` fixes both schema routes as explicit regression authority, and
  the candidate receipt's ruff/mypy scopes now include `validate_evidence.py`.
- Stage 6 v2 evidence schema and validator bind only `execution-receipt5.json`; the final task and
  aggregate evidence will be deterministic post-review outputs bound to this candidate/receipt.
- The provenance schema and validator require six ordered attempts, twelve distinct platform task
  IDs, exact hashes for the superseded fifth attempt, the same final candidate/request/receipt,
  two distinct final replies, complete history closure, and protected post-candidate integrity.
- The complete v1.0.4/v1.0.5 delivery-state coupling remains fail closed. Missing, malformed,
  stale, incomplete, or non-PASS assurance may derive only pre-closure; clean Git-bound assurance
  is additionally required to validate the closed state.
- Package validation records six attempts per family. Protected Oracles, Gmail, the private
  repository, production workflows, external writes, remote publication, RMD-06, RMD-07, and final
  AC-033 remain unexecuted and unclaimed.

Look for any unsupported evidence schema acceptance, stale receipt binding, omitted fifth-attempt
history, post-review protected-code mutation path, schema-valid crossed delivery state, or path to
v1.0.5 without the exact final provenance. Any such path is blocking.

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
