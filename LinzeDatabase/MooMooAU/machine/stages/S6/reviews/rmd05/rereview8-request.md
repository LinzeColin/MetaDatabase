# RMD-05 ninth independent read-only review request

Review only the immutable Git objects and the exact post-candidate artifacts identified below. Do
not use Gmail, GitHub remotes, Secrets, protected Oracles, production workflows, deployment or
publication. Return exactly one UTF-8 JSON object conforming to
`machine/stages/S6/schemas/review-reply-v2.schema.json`; do not wrap it in Markdown.

## Exact target

- Baseline commit: `2b8625a83e69093b9dce989f4eb964556e1b5fa2`
- Final review anchor: `1c4bb44f2eb67fc21b75d493ca0782dbccda0d8e`
- Executed parent candidate: `b5c5a7bfed564a98e34718edd7bd190ff2484ef5`
- Shared candidate tree: `f3fcc45a1216104c61ae4c3c65d2025079f57bcf`
- Final candidate receipt: `machine/stages/S6/reviews/rmd05/execution-receipt8.json`
- Final receipt SHA-256: `e349452dae4ec5dd1ac613046d81f1fad0ad2fadaa08f5bb2568a496237795ef`
- Candidate repository clone: `/private/tmp/moomooau-rmd05-candidate9.bG7HLm/repository`
- Review mode: `READ_ONLY_INDEPENDENT`
- Scope: `LOCAL_SYNTHETIC_ONLY`

The reply target must use the baseline, final review anchor, shared tree and SHA-256 of this exact
request. The receipt subject intentionally names the executed parent candidate, while the reply
names its empty same-tree child review anchor.

## Required verdict rule

Return `PASS` only if all four dimensions are `PASS`, every applicable prior finding in this
reviewer's complete nine-attempt history is explicitly `RESOLVED`, no new finding is open, and the
limitations do not imply production or protected success. Otherwise return `FAIL`, retain every
prior finding ID and add the smallest actionable open finding.

## Invariants to verify

1. The review anchor has exactly one parent, that parent is the executed candidate, and both commits
   resolve to the exact shared tree.
2. The anchor commit message has exactly one
   `MooMooAU-Execution-Candidate: b5c5a7bfed564a98e34718edd7bd190ff2484ef5`
   trailer and exactly one
   `MooMooAU-Execution-Receipt-SHA256: e349452dae4ec5dd1ac613046d81f1fad0ad2fadaa08f5bb2568a496237795ef`
   trailer.
3. Receipt8 has the supplied digest, exact baseline/executed-parent/tree subject, exactly 15 unique
   zero-exit commands, sanitized output digests, `LOCAL_SYNTHETIC_ONLY`, no protected execution and
   zero remote writes. It records Stage 6 `53 passed`, affected Stage 7 `37 passed`, RMD-05
   remediation `20 passed`, Ruff, strict mypy, dependency audit, reproducible SBOM, zero secret and
   publication findings, pinned Governance, container build/smoke/cleanup and package build.
4. `validate_stage6_receipt_anchor`, the Stage 6 candidate bundle validator, assurance validator,
   delivery-status builder/validator and Stage 6 validator all require receipt8 and the immutable
   anchor for CLOSED state.
5. The synchronized replacement regression first accepts a genuine same-tree anchor, then replaces
   receipt8 and synchronously rewrites all task, aggregate and provenance receipt hashes; validation
   must still fail because the immutable trailer digest differs.
6. The provenance schema and validator require nine exact ordered attempts per model family and 18
   distinct platform task IDs. Attempts one through seven retain their original mixed history.
7. The eighth Sol/Terra PASS pair, request7, receipt7 and anchor
   `d257042ab16347d75c23db145b24f24b0306d56f` remain byte-identical, hash-pinned and explicitly
   nonfinal under phase `REREVIEW_GOVERNANCE_FACTS_SUPERSEDED`.
8. The ninth/final attempt uses new task IDs `/root/rmd05_sol_rereview8` and
   `/root/rmd05_terra_rereview8`, request8, receipt8 and two distinct final5 reply artifacts.
9. `build_governance_facts.py` now emits the truthful closed changelog statement “九次不可变尝试链”;
   it no longer emits the stale “五次” wording that caused the prior otherwise-PASS anchor to be
   superseded. Package provenance and manifest validation likewise require nine attempts.
10. PRE_CLOSURE still requires all eight Stage 6 task records to be v1. CLOSED requires all eight to
    be receipt8-bound v2 plus the exact aggregate. Neither state may be crossed.
11. Post-review protected drift still covers production/effect code, every workflow, dependencies,
    schemas, tests, evidence/status/package authorities, capture tools, assurance validation and the
    governance-facts builder. Documentation-only output remains intentionally post-review writable.
12. All protected Oracle, real Gmail, private repository, Secret, production workflow, deployment,
    remote write and publication counters remain zero or `NOT_RUN`. RMD-06, RMD-07 and final AC-033
    remain outside this review.

## Preserved history

Do not delete, rewrite or reinterpret the prior request, receipt or reply artifacts. Confirm their
exact hashes through `machine/tools/validate_assurance_reviews.py`. In particular, preserve the
seventh mixed result (Sol PASS, Terra FAIL) and the eighth dual PASS that was superseded only because
the protected governance-facts generator still contained stale attempt-count wording.

## Minimum output content

- `schema_version`: `moomooau.independent-review-reply.v2`
- `review_mode`: `READ_ONLY_INDEPENDENT`
- one result for each dimension: `SCOPE`, `EVIDENCE_QUALITY`, `FAILURE_HONESTY`, `ROLLBACK`
- the complete applicable finding closure chain, including `RMD05-CLOSURE-005`
- explicit limitations for protected Oracles, real Gmail/private repository behavior, production,
  deployment, publication, RMD-06, RMD-07 and final AC-033
- `sensitive_data_observed: false`
- `production_or_protected_claimed: false`
