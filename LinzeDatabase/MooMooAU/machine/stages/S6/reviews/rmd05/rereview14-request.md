# MooMooAU RMD-05 final independent rereview request (attempt 15)

## Immutable target

- Baseline commit: `2b8625a83e69093b9dce989f4eb964556e1b5fa2`
- Review candidate anchor: `85fffeb6b43e8867b2b070d727d6401d465402ae`
- Execution candidate parent: `a4cae6b6cc4dddbb635764b484bfb5220588c0b8`
- Shared candidate tree: `953360aefea09618457fe341821e174eea6a706b`
- Candidate-bound receipt: `machine/stages/S6/reviews/rmd05/execution-receipt14.json`
- Receipt SHA-256: `798811aa1304fa1aa9739b825009a6a1e273656093caf882c860e4b6b2a55a15`
- Scope: `LOCAL_SYNTHETIC_ONLY`

The anchor has exactly one parent, the anchor and its parent resolve to the same tree, and its
commit message contains exactly one execution-candidate trailer and exactly one receipt-digest
trailer. Treat the anchor, parent, tree, this request and receipt as immutable review inputs. The
receipt is intentionally outside the immutable candidate tree until the post-review materialization
phase.

## Preserved attempt-14 result

Attempt 14 is not a closure. Its exact independent replies are preserved byte-for-byte:

- Sol: `machine/stages/S6/reviews/rmd05/final10/gpt-5.6-sol.reply.json`
  - SHA-256 `8c45c439e15be5007aef16979dcf35bd5f62928dcfde531e16e3ab6d476449f6`
  - verdict `FAIL`
- Terra: `machine/stages/S6/reviews/rmd05/final10/gpt-5.6-terra.reply.json`
  - SHA-256 `30c35c5f2ad73239250ed354def34dbfaf35b115635402eb885cec68734ecfbe`
  - verdict `FAIL`
- Shared request: `machine/stages/S6/reviews/rmd05/rereview13-request.md`
  - SHA-256 `a696eab139532fde20e1712e4058b8208463d9be82be095956ffc824780b2dcd`
- Shared receipt: `machine/stages/S6/reviews/rmd05/execution-receipt13.json`
  - SHA-256 `3d961beba530ddc416b70d6b3c1116f7d2016f99e630ce752b36ed75612a7f78`

Both current provenance records therefore contain exactly 14 ordered attempts, 28 distinct Codex
platform task IDs and `closure_status=BLOCKED`. Attempt 14 is
`REREVIEW_PUBLIC_CLOSURE_ADVERSE`. Attempt 15 may become `REREVIEW_FINAL` only if both new replies
are independently PASS and close the complete finding history.

## Findings to verify

Both attempt-14 reviewers kept `RMD05-CLOSURE-009` OPEN, for different concrete reasons:

1. Sol found that the request overstated integration coverage. The old test directly supplied a
   Git diff, monkeypatched every builder and replaced the 60-file authority set with a small set. It
   did not route the real delta through `_validate_git_subject(...,
   allow_post_review_authorities=True)` into `_validate_post_review_authorities`, nor exercise
   `evaluate_assurance_reviews(..., verify_git=True)` or the delivery-status validator.
2. Terra found that Acceptance `observed_at_utc` and `remediation_base_commit` came from the mutable
   post-review HEAD summary. A descendant could select different valid inputs, rebuild all 35
   Acceptance files and obtain another internally valid authority set.

The dual FAIL result remains preserved. No v1.0.5 closure output was accepted from attempt 14.

## Remediation under review

### 1. Acceptance inputs are candidate-bound

`_validate_post_review_authorities` now reads the exact
`evidence/acceptance/latest.json` blob from the reviewed candidate commit through Git. It accepts
only that blob's `observed_at_utc` and `remediation_base_commit` as deterministic builder inputs.
The complete 35-file Acceptance bundle is rebuilt from those frozen inputs against the final Stage
6 evidence and every observed file must be byte-equal to the result. Missing or invalid candidate
blobs, alternate valid timestamps, alternate ancestor commits, missing files or non-canonical bytes
all block closure.

### 2. The real public Git closure path is exercised without monkeypatches

`tests/remediation/test_rmd05.py` now constructs an exact
`LinzeDatabase/MooMooAU` project layout in a clean local Git repository descending from the frozen
Stage 5 baseline. It creates an execution candidate, receipt, same-tree Git anchor, two final review
records, Stage 6 v2 evidence and all deterministic closure authorities. It does not monkeypatch the
authority set, builders, Git subject validator, assurance evaluator or delivery validator.

`test_rmd05_public_closure_uses_real_git_and_the_full_authority_set` requires:

- the production 60-file authority set;
- `evaluate_assurance_reviews(root, repository, verify_git=True)` PASS with no errors; and
- `validate_delivery_status.validate(root)` PASS.

This public call necessarily obtains candidate-to-HEAD paths from
`_validate_git_subject(..., allow_post_review_authorities=True)` and passes them to the real
`_validate_post_review_authorities` implementation.

### 3. Synchronized descendant attacks are covered through the public entrypoint

`test_rmd05_public_closure_blocks_forbidden_paths_with_a_synchronized_manifest` starts from the
valid committed closure, separately changes each of the following and rebuilds the canonical
manifest before committing:

- `machine/acceptance/evidence.py`;
- `machine/acceptance/schemas/acceptance-summary-v1.schema.json`;
- `machine/facts/metrics.json`;
- an extra `evidence/acceptance/AC-999-unexpected.json`; and
- an extra Acceptance Oracle descendant.

For every case, the public `verify_git=True` evaluator is BLOCKED with the reviewed-surface drift
error and the delivery-status validator is FAIL.

`test_rmd05_public_closure_freezes_acceptance_inputs_to_the_review_candidate` then substitutes a
different valid UTC timestamp and a different valid ancestor commit, synchronously rebuilds all 35
Acceptance files, the CLOSED status, all governance facts and the canonical manifest, and commits
the result. The public evaluator is still BLOCKED specifically because the Acceptance authority no
longer matches the candidate-bound inputs; the delivery-status validator is FAIL.

The older private/unit-level tests remain as additional diagnostics, but they are no longer the
basis for the public-closure claim.

### 4. Exact authority and protocol limits remain fail closed

- Authority paths remain the exact 60 builder outputs; broad facts or Acceptance prefixes are not
  accepted.
- The only non-authority post-review paths are the exact 12 final-output files for receipt14,
  request14, final11 replies, provenance wrappers and v1.0.5 human documentation.
- Every other source, workflow, dependency, test, validator, schema, unexpected facts, extra
  Acceptance or Oracle path remains protected.
- Schema and validator permit exactly 14 attempts only with `closure_status=BLOCKED`, and exactly
  15 attempts only with `closure_status=PASS`.
- Attempt 14's dual FAIL replies, request13 and receipt13 are hash pinned.
- Attempt 15 must use two new distinct platform task IDs, this shared request14, two distinct
  final11 replies, receipt14 and the same anchor/tree.
- A final reply must make all four dimensions PASS, contain no OPEN finding, and explicitly resolve
  the complete history through `RMD05-CLOSURE-009`.

## Candidate-bound local gates

Receipt14 records exactly 19 distinct commands, all with exit code zero. Its schema validates and
every sanitized stdout/stderr digest is recomputable. Recorded outcomes include:

- Ruff format: 86 files; Ruff lint PASS;
- strict mypy: 72 source files;
- Stage 6 task tests: `55 passed`;
- affected Stage 7 runtime regressions: `37 passed`;
- RMD-05 remediation regressions: `32 passed`, including the three real public Git scenarios;
- assurance history integrity PASS with 14 attempts per model and 28 distinct task IDs while
  closure remains honestly BLOCKED;
- Stage 6 `REVIEW_INPUT` PASS and exact v1.0.4 PRE_CLOSURE delivery status PASS;
- 13 governance facts match;
- dependency audit, reproducible SBOM, secret scan and publication scan PASS;
- pinned shared Governance validation PASS;
- local container build, network-none/read-only smoke, cleanup and local package build PASS.

Receipt14 records `sensitive_data_observed=false`,
`production_or_protected_executed=false`, `remote_service_writes=0` and
`ephemeral_local_outputs_removed=true`. The candidate checkout remained clean.

## Required independent review method

Review read-only and independently. Inspect the exact Git objects, receipt14, schemas, validator,
builders and regressions. Recompute hashes and run read-only local checks where useful. Do not trust
this narrative over candidate source. Do not access Gmail, GitHub remotes, Secrets, protected
Oracles, production workflows, deployment or publication.

Return one UTF-8 JSON object conforming to
`machine/stages/S6/schemas/review-reply-v2.schema.json`, with:

- target baseline `2b8625a83e69093b9dce989f4eb964556e1b5fa2`;
- target candidate `85fffeb6b43e8867b2b070d727d6401d465402ae`;
- target tree `953360aefea09618457fe341821e174eea6a706b`;
- this request's exact SHA-256;
- `review_mode=READ_ONLY_INDEPENDENT`;
- exactly the four dimensions `SCOPE`, `EVIDENCE_QUALITY`, `FAILURE_HONESTY`, `ROLLBACK`;
- the complete applicable finding chain, including an explicit disposition for
  `RMD05-CLOSURE-009`;
- honest limitations and false sensitive/protected/production claims.

Required verdict rule: return `PASS` only if all four dimensions PASS, every applicable finding is
`RESOLVED`, both attempt-14 required fixes are genuinely closed, and no new OPEN finding exists.
Otherwise return `FAIL` and include every OPEN finding with a concrete required fix.

## Scope limitations that must remain explicit

This review proves only local immutable Git objects, deterministic post-candidate authority paths
and local synthetic gates. It does not prove protected Oracles, real Gmail, a private repository,
real Secrets, production health, a production workflow, deployment, publication, RMD-06, RMD-07
or final AC-033.
