# MooMooAU RMD-05 final independent rereview request (attempt 13)

## Immutable target

- Baseline commit: `2b8625a83e69093b9dce989f4eb964556e1b5fa2`
- Review candidate anchor: `e465aa6fc88ba021b5dd0f172a5d2fa5bad1724b`
- Execution candidate parent: `05baf008394b745a41b3e115bfcc460f5566fb11`
- Shared candidate tree: `6d38399c14ea2e831964df87875575e72dcb1b62`
- Candidate-bound receipt: `machine/stages/S6/reviews/rmd05/execution-receipt12.json`
- Receipt SHA-256: `1bfe12fcbf5f2ec0ffadf38ee67d8adf9b8dbfada8d23f914c4e3ac50fcb3b0b`
- Scope: `LOCAL_SYNTHETIC_ONLY`

The anchor has exactly one parent, the anchor and its parent resolve to the same tree, and its
commit message contains exactly one execution-candidate trailer and exactly one receipt-digest
trailer. Treat the anchor, parent, tree, request and receipt as immutable review inputs.

## Preserved attempt-12 result

Attempt 12 is not a closure. Its exact independent replies are preserved without normalization or
reinterpretation:

- Sol: `machine/stages/S6/reviews/rmd05/final8/gpt-5.6-sol.reply.json`
  - SHA-256 `bb53e04b892adb4105313493899d5a9b0c7b3d8e10535de7e92a9e5cb0715c03`
  - verdict `PASS`
- Terra: `machine/stages/S6/reviews/rmd05/final8/gpt-5.6-terra.reply.json`
  - SHA-256 `9dd51f76944b2817afa7add5437481a2034211382d36d47bed16cd3cc6bc7011`
  - verdict `FAIL`
- Shared request: `machine/stages/S6/reviews/rmd05/rereview11-request.md`
  - SHA-256 `83d5c3efddc95259a3d6f700a3c4fda3a1a9d2410f5d94fa2ad466980edef109`
- Shared receipt: `machine/stages/S6/reviews/rmd05/execution-receipt11.json`
  - SHA-256 `ba180e358e2b067fa6cedeb6dcefa11aff1c59eac9998f5f403eb1abe59295c8`

Both current provenance records therefore contain exactly 12 ordered attempts, 24 distinct Codex
platform task IDs and `closure_status=BLOCKED`. Attempt 12 is
`REREVIEW_AUTHORITY_DRIFT_ADVERSE`; attempt 13 may become `REREVIEW_FINAL` only if both new replies
are independently PASS and close the complete finding history.

## Finding to verify

Terra opened `RMD05-CLOSURE-009`:

> Post-review drift protection did not cover evidence, status or package authorities, so a
> descendant delivery commit could rewrite those authorities without the Git-bound review guard
> rejecting it.

Sol did not report this finding, but the code confirmed Terra's observation. The mixed result was
therefore treated as FAIL and no v1.0.5 closure outputs were generated from attempt 12.

## Remediation under review

### 1. Authority paths are now explicit and fail closed by default

`machine/tools/validate_assurance_reviews.py` defines exact post-review authority paths and prefixes
for:

- `evidence/stage6/latest.json`;
- `evidence/tasks/T0601.json` through `T0608.json`;
- every `evidence/acceptance/` record and summary;
- `machine/status/latest.json`;
- generated `machine/facts/` governance facts;
- `taskpack/SOURCE_PROVENANCE.v1.0.5.json`;
- `taskpack/PACKAGE_MANIFEST.v1.0.5.json`.

The broader `evidence/` surface is protected. Any non-authorized evidence path, source, test,
workflow, dependency, schema, contract, validator or effect surface changed after review remains an
unconditional blocker. Direct `_validate_git_subject` use rejects authority changes by default.

### 2. The final deterministic materialization window is narrow and mechanically checked

Only a provenance state already containing two attempt-13 PASS replies may request the authority
materialization allowance. Even then, `_validate_git_subject` returns the exact changed authority
paths and `_validate_post_review_authorities` must independently validate all of the following:

1. Stage 6 v2 evidence has the exact receipt12 binding, command mapping, execution candidate, tree
   and immutable same-tree anchor.
2. AC-001 through AC-034 records and the blocked 0/34 summary match the deterministic Acceptance
   bundle and still claim zero protected or production execution.
3. `machine/status/latest.json` exactly equals a deterministic CLOSED rebuild supplied with the
   already-verified PASS assurance result; this breaks recursion without weakening transition
   semantics.
4. Every generated governance fact exactly equals `build_governance_facts.py` output.
5. v1.0.5 source provenance passes its fixed identity, immutable predecessor and semantic-delta
   validator.
6. v1.0.5 package manifest exactly equals the canonical manifest builder output. The reviewed
   builder hashes the full selected package tree except the manifest itself, so post-manifest file
   drift is rejected.
7. The delivery worktree is clean.

Missing authority materialization is also rejected. `verify_git=False` remains available only for
the deterministic builder phase after the two PASS replies exist; final acceptance uses
`verify_git=True`, which runs all checks above against the clean committed delivery tree.

### 3. Negative regressions cover every requested authority class

`tests/remediation/test_rmd05.py` now commits post-review mutations for each of these paths and
requires the Git-bound guard to reject them:

- `machine/status/latest.json`;
- `evidence/stage6/latest.json`;
- `evidence/tasks/T0601.json`;
- `taskpack/PACKAGE_MANIFEST.v1.0.5.json`;
- `taskpack/SOURCE_PROVENANCE.v1.0.5.json`;
- `machine/facts/status.json`.

A second regression exercises the deterministic materialization helper and independently forces
Stage 6 evidence, Acceptance evidence, status, governance facts, source provenance and package
manifest validation failures. Every forced mismatch must produce its category-specific blocker.

### 4. The review protocol is non-circular and preserves failure history

- Schema and validator permit exactly 12 attempts only with `closure_status=BLOCKED`.
- They permit exactly 13 attempts only with `closure_status=PASS`.
- Attempt 12's mixed exact replies, request11 and receipt11 are hash pinned.
- Attempt 13 must add two new and distinct platform task IDs, a shared request12, two distinct
  final9 reply artifacts, receipt12 and the same immutable candidate anchor/tree.
- A final reply must have all four required dimensions PASS, no OPEN finding, and explicitly close
  the full history through `RMD05-CLOSURE-009`.
- Package/provenance semantics derive 13 attempts and 19 gate commands from shared code constants.
- User-visible Stage 6 help honestly says `twelve-attempt rejected history`.
- Closed governance wording honestly says `十三次不可变尝试链`.

## Candidate-bound local gates

Receipt12 records exactly 19 distinct commands, all with exit code zero. Every sanitized stdout and
stderr SHA-256 is independently recomputable from the receipt payload. Recorded outcomes include:

- Stage 6 task tests: `55 passed`;
- affected Stage 7 runtime regressions: `37 passed`;
- RMD-05 remediation regressions: `26 passed`;
- Ruff format and lint PASS;
- strict mypy PASS over 72 source files;
- assurance history integrity PASS with 12 attempts per model and 24 distinct task IDs while
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

Receipt12 also records `sensitive_data_observed=false`,
`production_or_protected_executed=false`, `remote_service_writes=0` and
`ephemeral_local_outputs_removed=true`.

## Required independent review method

Review read-only and independently. Inspect the exact Git objects, receipt12, schemas, validator,
builders and regressions. Recompute hashes where useful. Do not trust this narrative over the
candidate source. Do not access Gmail, GitHub remotes, Secrets, protected Oracles, production
workflows, deployment or publication.

Return one UTF-8 JSON object conforming to
`machine/stages/S6/schemas/review-reply-v2.schema.json`, with:

- target baseline `2b8625a83e69093b9dce989f4eb964556e1b5fa2`;
- target candidate `e465aa6fc88ba021b5dd0f172a5d2fa5bad1724b`;
- target tree `6d38399c14ea2e831964df87875575e72dcb1b62`;
- this request's exact SHA-256;
- `review_mode=READ_ONLY_INDEPENDENT`;
- exactly the four dimensions `SCOPE`, `EVIDENCE_QUALITY`, `FAILURE_HONESTY`, `ROLLBACK`;
- the complete applicable finding chain, including an explicit disposition for
  `RMD05-CLOSURE-009`;
- honest limitations and false protected/production claims.

Required verdict rule: return `PASS` only if all four dimensions PASS, every applicable finding is
`RESOLVED`, the authority materialization design is genuinely fail closed, and no new OPEN finding
exists. Otherwise return `FAIL` and include each OPEN finding with a concrete required fix.

## Scope limitations that must remain explicit

This review proves only local immutable Git objects, exact post-candidate artifacts, deterministic
code paths and local synthetic gates. It does not prove protected Oracles, real Gmail, a private
repository, real Secrets, production health, a production workflow, deployment, publication,
RMD-06, RMD-07 or final AC-033.
