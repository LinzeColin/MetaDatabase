# MooMooAU RMD-05 final independent rereview request (attempt 14)

## Immutable target

- Baseline commit: `2b8625a83e69093b9dce989f4eb964556e1b5fa2`
- Review candidate anchor: `3054a409ec3e4064a6dc0827c9cf3415ce5798ef`
- Execution candidate parent: `19cd62d8a50becce469a7369dd1964f2e1113cf6`
- Shared candidate tree: `357258dbea6482767eb16af22b754603388f0c2c`
- Candidate-bound receipt: `machine/stages/S6/reviews/rmd05/execution-receipt13.json`
- Receipt SHA-256: `3d961beba530ddc416b70d6b3c1116f7d2016f99e630ce752b36ed75612a7f78`
- Scope: `LOCAL_SYNTHETIC_ONLY`

The anchor has exactly one parent, the anchor and its parent resolve to the same tree, and its
commit message contains exactly one execution-candidate trailer and exactly one receipt-digest
trailer. Treat the anchor, parent, tree, request and receipt as immutable review inputs.

## Preserved attempt-13 result

Attempt 13 is not a closure. Its exact independent replies are preserved without normalization or
reinterpretation:

- Sol: `machine/stages/S6/reviews/rmd05/final9/gpt-5.6-sol.reply.json`
  - SHA-256 `6fd80ffa03465013e18d48df85a979984918f912af6296f60bc39b6bd903a226`
  - verdict `FAIL`
- Terra: `machine/stages/S6/reviews/rmd05/final9/gpt-5.6-terra.reply.json`
  - SHA-256 `4f2d16dfb2b74233a120898c229a840b4bc3b9eb664b50d209f8fa4ed7e06636`
  - verdict `FAIL`
- Shared request: `machine/stages/S6/reviews/rmd05/rereview12-request.md`
  - SHA-256 `1f3fd30f6b348d903293d4db736e1163b7d283dc0b9d6f0f116548a9c96d4385`
- Shared receipt: `machine/stages/S6/reviews/rmd05/execution-receipt12.json`
  - SHA-256 `1bfe12fcbf5f2ec0ffadf38ee67d8adf9b8dbfada8d23f914c4e3ac50fcb3b0b`

Both current provenance records therefore contain exactly 13 ordered attempts, 26 distinct Codex
platform task IDs and `closure_status=BLOCKED`. Attempt 13 is
`REREVIEW_AUTHORITY_MATERIALIZATION_ADVERSE`; attempt 14 may become `REREVIEW_FINAL` only if both
new replies are independently PASS and close the complete finding history.

## Finding to verify

Both attempt-13 reviewers kept `RMD05-CLOSURE-009` OPEN. The shared substance was:

> The final authority allowance was not fail closed because its deterministic Acceptance builder,
> validator and schemas remained mutable after review. Broad facts and Acceptance authority
> prefixes also admitted files not produced by the deterministic builders, and the Git regression
> did not couple the real changed-path delta to the final authority validator.

The dual FAIL result was preserved. No v1.0.5 closure outputs were accepted from attempt 13.

## Remediation under review

### 1. Post-review paths are exact sets, with no authority prefixes

`machine/tools/validate_assurance_reviews.py` now defines exactly 60 authority files:

- the Stage 6 aggregate and `T0601` through `T0608` evidence;
- exactly `AC-001` through `AC-034` plus the Acceptance summary;
- `machine/status/latest.json`;
- exactly the 13 files emitted by `build_governance_facts.py`;
- `taskpack/SOURCE_PROVENANCE.v1.0.5.json`;
- `taskpack/PACKAGE_MANIFEST.v1.0.5.json`.

There is no broad `machine/facts/` or `evidence/acceptance/` authority prefix. The only other
post-review changes permitted by `_validate_git_subject` are an exact 12-file final-output set:
README, VERSION, the two top-level provenance records, receipt13, request13, two final10 replies and
the four v1.0.5 taskpack narrative files. Every other descendant path is unconditionally blocked,
including all of `machine/acceptance/`, source, tests, workflows, dependencies, contracts, schemas,
validators, `machine/facts/metrics.json`, unexpected facts, extra Acceptance files and Oracle paths.
This remains true when `allow_post_review_authorities=True`.

### 2. The allowed authority delta must equal deterministic materialization exactly

Only a provenance state already containing two attempt-14 PASS replies may request the authority
materialization allowance. `_validate_post_review_authorities` then:

1. validates receipt13-bound Stage 6 v2 evidence and records its exact nine payloads;
2. rebuilds and validates the exact 35-file blocked Acceptance bundle;
3. rebuilds the exact CLOSED delivery status from the already-verified PASS result;
4. rebuilds the exact 13 governance facts;
5. rebuilds and validates exact v1.0.5 source provenance;
6. rebuilds the canonical package manifest;
7. requires those builders to produce the complete frozen 60-file authority set;
8. compares every deterministic payload with the corresponding blob in the reviewed execution
   candidate and derives the exact expected materialization delta;
9. requires the real Git `authority_paths` from candidate-to-HEAD to equal that expected delta.

An extra authority path, a missing changed authority, a missing builder output, non-deterministic
bytes or any changed path outside the two frozen sets blocks closure. Final acceptance still requires
`verify_git=True` against a clean committed delivery tree. `verify_git=False` exists only for the
post-dual-PASS deterministic builder phase and cannot be used for final acceptance.

### 3. Regressions exercise the real Git path and adversarial file classes

`tests/remediation/test_rmd05.py` now includes committed descendant mutations with
`allow_post_review_authorities=True` for:

- the Acceptance builder/validator and its schema under `machine/acceptance/`;
- `machine/facts/metrics.json` and an unexpected facts file;
- an extra Acceptance JSON file and an Acceptance Oracle subpath.

Each must be rejected before authority validation. The exact-set tests also prove representative
status, Stage 6, task, Acceptance, facts, provenance and manifest files are authorities while
unexpected paths are not.

An end-to-end regression creates a real clean Git execution candidate and descendant, obtains the
actual changed path list through `_validate_git_subject(...,
allow_post_review_authorities=True)`, and passes it to `_validate_post_review_authorities`. The
deterministic materialization succeeds only with the exact delta; removing one expected path yields
the exact-delta blocker.

### 4. The review protocol preserves the rejected attempt and advances non-circularly

- Schema and validator permit exactly 13 attempts only with `closure_status=BLOCKED`.
- They permit exactly 14 attempts only with `closure_status=PASS`.
- Attempt 13's two FAIL replies, request12 and receipt12 are hash pinned.
- Attempt 14 must add two new and distinct platform task IDs, a shared request13, two distinct
  final10 reply artifacts, receipt13 and the same immutable candidate anchor/tree.
- A final reply must have all four required dimensions PASS, no OPEN finding, and explicitly close
  the full history through `RMD05-CLOSURE-009`.
- Package/provenance semantics derive 14 attempts and 19 gate commands from shared constants.
- User-visible Stage 6 help says `thirteen-attempt rejected history`.
- Closed governance wording says `十四次不可变尝试链`.

## Candidate-bound local gates

Receipt13 records exactly 19 distinct commands, all with exit code zero. Every sanitized stdout and
stderr SHA-256 is independently recomputable from the receipt payload. Recorded outcomes include:

- Stage 6 task tests: `55 passed`;
- affected Stage 7 runtime regressions: `37 passed`;
- RMD-05 remediation regressions: `29 passed`;
- Ruff format and lint PASS;
- strict mypy PASS over 72 source files;
- assurance history integrity PASS with 13 attempts per model and 26 distinct task IDs while
  closure remains BLOCKED;
- Stage 6 `REVIEW_INPUT` PASS;
- delivery status PASS in exact v1.0.4 `PRE_CLOSURE` state;
- governance facts check PASS;
- dependency audit PASS;
- reproducible sanitized SBOM PASS;
- secret scan zero findings;
- publication scan zero forbidden findings;
- pinned shared Governance validation PASS;
- local container build, network-none/read-only smoke and cleanup PASS;
- local package build PASS.

Receipt13 also records `sensitive_data_observed=false`,
`production_or_protected_executed=false`, `remote_service_writes=0` and
`ephemeral_local_outputs_removed=true`.

## Required independent review method

Review read-only and independently. Inspect the exact Git objects, receipt13, schemas, validator,
builders and regressions. Recompute hashes where useful. Do not trust this narrative over the
candidate source. Do not access Gmail, GitHub remotes, Secrets, protected Oracles, production
workflows, deployment or publication.

Return one UTF-8 JSON object conforming to
`machine/stages/S6/schemas/review-reply-v2.schema.json`, with:

- target baseline `2b8625a83e69093b9dce989f4eb964556e1b5fa2`;
- target candidate `3054a409ec3e4064a6dc0827c9cf3415ce5798ef`;
- target tree `357258dbea6482767eb16af22b754603388f0c2c`;
- this request's exact SHA-256;
- `review_mode=READ_ONLY_INDEPENDENT`;
- exactly the four dimensions `SCOPE`, `EVIDENCE_QUALITY`, `FAILURE_HONESTY`, `ROLLBACK`;
- the complete applicable finding chain, including an explicit disposition for
  `RMD05-CLOSURE-009`;
- honest limitations and false protected/production claims.

Required verdict rule: return `PASS` only if all four dimensions PASS, every applicable finding is
`RESOLVED`, the exact authority materialization design is genuinely fail closed, and no new OPEN
finding exists. Otherwise return `FAIL` and include each OPEN finding with a concrete required fix.

## Scope limitations that must remain explicit

This review proves only local immutable Git objects, exact post-candidate artifacts, deterministic
code paths and local synthetic gates. It does not prove protected Oracles, real Gmail, a private
repository, real Secrets, production health, a production workflow, deployment, publication,
RMD-06, RMD-07 or final AC-033.
