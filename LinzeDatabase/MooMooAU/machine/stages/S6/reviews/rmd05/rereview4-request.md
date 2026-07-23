# RMD-05 final independent re-review request

Review exactly the immutable candidate and candidate-bound local receipt below. This is a
read-only independent review. Do not edit files, execute protected Oracles, invoke production
workflows, access Gmail or any private repository, request Secrets, publish, push, or infer remote
or production success from local evidence.

## Immutable target

- Repository baseline: `2b8625a83e69093b9dce989f4eb964556e1b5fa2`
- Candidate commit: `ac46f96890103a142af724ca1bbd13fa81f3ef3c`
- Candidate tree: `9f649c9044ce19447fbfde3f2aae99e0a4d23c4c`
- Final candidate receipt: `machine/stages/S6/reviews/rmd05/execution-receipt4.json`
- Receipt SHA-256: `3359865176269e7eb1da39aa38d6fc9e8230e530f8d02a25f3d8b5f4a3057fc2`
- Receipt scope: `LOCAL_SYNTHETIC_ONLY`; 15 unique zero-exit commands; protected/production
  execution false; remote writes zero; ephemeral image removed.

The invocation supplies the SHA-256 of this exact request. Bind the reply target to that request
hash, the baseline, candidate commit, and candidate tree above.

## Required review dimensions

Return one result for each exact ID: `SCOPE`, `EVIDENCE_QUALITY`, `FAILURE_HONESTY`, and
`ROLLBACK`. A final `PASS` is permitted only if all four dimensions pass and every finding in this
reviewer's complete five-attempt history is explicitly `RESOLVED`. Otherwise return `FAIL` and at
least one `OPEN` finding with a concrete required fix.

## Preserved history to verify

The repository must preserve these prior attempts byte-for-byte and the candidate must implement a
five-attempt, ten-distinct-task provenance chain per the v2 schema and validator:

1. `INITIAL`: original candidate/request and two independent FAIL replies.
2. `REREVIEW_ADVERSE`: candidate-bound receipt1 and two FAIL replies opening
   `RMD05-CLOSURE-001`.
3. `REREVIEW_SUPERSEDED`: receipt2 and two PASS replies, retained only as superseded history.
4. `REREVIEW_TRANSITION_ADVERSE`: candidate `7524ea0401cda4a5c9b2809f4400b55a9b62747c`,
   tree `2ec39b324f1839e82f2bc768fe75a39a6f035e93`, request3 SHA-256
   `113b08b9262cee2c0e3900e32efe3d14f643d9d19c6afbed1b18ae46532d87d1`, receipt3 SHA-256
   `88d1db524f1d9421c806a73d532c9307b3b3a699b030964ce58dfd5650bd3a24`, and two FAIL
   replies. Terra opened `RMD05-CLOSURE-002`; Sol opened `RMD05-CLOSURE-003`.
5. `REREVIEW_FINAL`: this request, receipt4, and the fresh independent reply.

Each final reply must cover its own complete prior finding history and must explicitly include both
`RMD05-CLOSURE-002` and `RMD05-CLOSURE-003` as `RESOLVED` for a PASS. Do not erase or reinterpret
the prior FAIL/PASS records.

## Repairs that require adversarial inspection

Inspect the candidate diff from the frozen baseline and root-cause the earlier closure defects,
including at least:

- `schemas/delivery-status-v1.schema.json` couples the complete pre-closure state
  (v1.0.4, old findings, RMD-05 blocker and exact next action) and complete closed state
  (v1.0.5, `REV-P1-006`, RMD-06 blocker and exact next action) as two root alternatives. Both
  crossed version/fact combinations must be rejected.
- `machine/contracts/delivery_status_model.json`, `build_delivery_status.py`, and
  `validate_delivery_status.py` are candidate-complete: missing, malformed, failing, stale, or
  incomplete assurance can derive only pre-closure; only the hash-checked five-attempt two-family
  PASS chain can derive the closed state; closed validation additionally requires clean Git-bound
  post-review integrity.
- `tests/remediation/test_rmd05.py` contains negative tests for both crossed states, fail-closed
  transition selection, exact history, receipt tamper, task/model confusion, secret leakage, and
  post-review drift of status/package authority surfaces.
- `machine/tools/validate_assurance_reviews.py` preserves the fourth adverse attempt, requires five
  ordered attempts per family, ten distinct platform task IDs, the same final candidate/request/
  receipt, two distinct final replies, full finding-history closure, and rejects post-candidate
  drift under every protected workflow/runtime/test/schema/status/package authority prefix.
- `build_package_manifest.py`, `validate_package.py`, `build_governance_facts.py`, Stage 6 evidence
  schema/validator, secret scan, model-assurance workflow, and capture tool are already prepared for
  the final transition and protected from later code drift. Only hash-bound review wrappers,
  evidence/status/fact/document/package outputs may be generated after review.
- `machine/contracts/production_composition.json` remains hash-bound and validates; all production,
  protected, Gmail, private-repository, external-write and publication counters remain zero.

Adversarially check for a path that can emit or validate v1.0.5 without the exact final provenance,
for schema-valid crossed states, for unprotected authority code, for a stale receipt/candidate
binding, or for any implied protected/production claim. Any such path is blocking.

## Reply contract

Return only one UTF-8 JSON object followed by one LF, conforming to
`machine/stages/S6/schemas/review-reply-v2.schema.json`. Use model family exactly as requested by the
invocation. The reply must contain:

- exact target baseline/candidate/tree/request SHA-256;
- `review_mode: READ_ONLY_INDEPENDENT`;
- one verdict and exactly the four required dimensions with evidence references and rationale;
- all applicable historical and newly found findings, each `RESOLVED` or `OPEN` as required by the
  schema;
- honest limitations that local evidence does not prove protected Oracles, real Gmail/private
  repository behavior, production health, deployment, publication, RMD-06, RMD-07, or final
  AC-033;
- `sensitive_data_observed: false` and `production_or_protected_claimed: false` unless the review
  actually observed otherwise, in which case fail closed without reproducing sensitive content.
