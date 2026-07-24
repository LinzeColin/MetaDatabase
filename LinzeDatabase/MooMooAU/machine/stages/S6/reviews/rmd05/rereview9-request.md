# RMD-05 tenth independent read-only review request

Review only the immutable Git objects and exact post-candidate artifacts identified below. Do not
use Gmail, GitHub remotes, Secrets, protected Oracles, production workflows, deployment or
publication. Return exactly one UTF-8 JSON object conforming to
`machine/stages/S6/schemas/review-reply-v2.schema.json`; do not wrap it in Markdown.

## Exact target

- Baseline commit: `2b8625a83e69093b9dce989f4eb964556e1b5fa2`
- Final review anchor: `3cd4a4122016ce9b3af8d42901d6d0c968ae981a`
- Executed parent candidate: `21d465ba4eab32affdf8d42121aaa577a4f7b81d`
- Shared candidate tree: `1926d2517a9ed3a2a8b4191b0eba8206d5e8af4f`
- Candidate receipt: `machine/stages/S6/reviews/rmd05/execution-receipt9.json`
- Receipt SHA-256: `2814dcca4c0d8a52e255760ed7b414a78e02a21f89745547f03986113ced7f68`
- Candidate checkout: `/private/tmp/moomooau-rmd05-worktree11.O2uo88/repository`
- Review mode: `READ_ONLY_INDEPENDENT`
- Scope: `LOCAL_SYNTHETIC_ONLY`

The reply target must use the baseline, final review anchor, shared tree and SHA-256 of this exact
request. The receipt subject intentionally names the executed parent, while the reply names its
empty same-tree child anchor.

## Non-circular two-phase protocol

This immutable target is the **review input**, not a fabricated post-review output. The current
tenth-attempt Sol/Terra replies cannot exist until each reviewer returns them. Therefore their
`final6` files, the ten-attempt `closure_status=PASS` provenance records, receipt9-bound Stage 6 v2
evidence, v1.0.5 delivery status and closed governance facts are intentionally absent from this
candidate tree. Do not fail solely because those necessarily post-review artifacts are absent.

The reviewed code must make that boundary fail closed:

1. Nine completed attempts are materialized before this review. Both provenance records contain
   exactly nine ordered attempts and 18 distinct task IDs, bind the ninth attempt to request8,
   receipt8 and anchor `1c4bb44f2eb67fc21b75d493ca0782dbccda0d8e`, preserve Sol PASS and
   Terra FAIL exactly, and state `closure_status=BLOCKED`.
2. `validate_assurance_reviews.py --history-only` exits zero only when that blocked history has
   `history_integrity=PASS`, `pending_final_review=true`, no integrity errors, two model families
   and 18 distinct task IDs. Normal assurance remains `BLOCKED` until a schema-valid tenth pair is
   appended and both verdicts are PASS.
3. `validate_stage6.py --cumulative-final --review-input` validates the v1 pre-final evidence and
   materialized history without claiming closure. Its output must say `validation_mode=REVIEW_INPUT`,
   `final_review_pending=true`, `materialized_review_passes=1`, zero protected/production effects
   and status PASS for the review-input validation itself.
4. The deterministic delivery validator passes only with package v1.0.4, the
   `RMD-05_ASSURANCE_PROVENANCE_PENDING` blocker and production readiness BLOCKED. The governance
   facts check must match that honest pre-closure authority.
5. After two current PASS replies exist, the same schema/validator requires ten ordered attempts,
   20 distinct task IDs, two distinct final6 replies, receipt9/anchor binding, complete finding
   closure and `closure_status=PASS`. Only then may deterministic post-review builders emit v1.0.5
   CLOSED outputs. Any FAIL keeps PRE_CLOSURE and must be preserved as another adverse history.

## Required verdict rule

Return `PASS` only if all four dimensions are `PASS`, every applicable prior finding is explicitly
`RESOLVED` including `RMD05-CLOSURE-006`, the two-phase protocol above is mechanically fail closed,
and no new finding is open. Otherwise return `FAIL`, preserve every prior finding ID and add the
smallest actionable open finding.

## Invariants to verify

1. The review anchor has exactly one parent, that parent is the executed candidate, both resolve to
   the supplied tree, and the anchor contains exactly one candidate trailer and one receipt-digest
   trailer with the supplied values.
2. Receipt9 has the supplied digest and exact baseline/executed-parent/tree subject. It contains
   exactly 19 unique zero-exit commands with recomputable sanitized-output digests. In addition to
   Ruff, strict mypy, 54 Stage 6 tests, 37 affected Stage 7 tests, 21 remediation tests, dependency
   audit, reproducible SBOM, zero secret/publication findings, pinned Governance, container
   build/smoke/cleanup and package build, it records the four pre-final validators described above.
3. Receipt9 remains `LOCAL_SYNTHETIC_ONLY`, with protected/production execution false, remote writes
   zero, sensitive data false and ephemeral outputs removed.
4. The exact ninth replies are present and hash-pinned:
   - Sol: `df7ecfdd37d47b4ba3455768ea2e0b981a1d73263df3891e2ae50ed20bcda0a1`
   - Terra: `0e3b9af0e69036ff518fe9ccad03b26e9b6fb9090d2cd8a0e1510fd6dca1509c`
   Terra's `RMD05-CLOSURE-006` remains visibly OPEN in that historical reply; it is not rewritten.
5. The provenance schema permits exactly nine attempts only with `closure_status=BLOCKED` and
   exactly ten only with `closure_status=PASS`. The validator preserves the ninth mixed verdict,
   requires the tenth pair to close the full finding history, and never treats history-integrity
   PASS as closure PASS.
6. Stage 6 final v2 evidence, its validator and the delivery transition require receipt9. The
   synchronized replacement regression still accepts a real same-tree anchor first, then rejects a
   replacement receipt even when every mutable task, aggregate and provenance digest is rewritten.
7. Post-review protected drift covers production/effect code, all workflows, dependencies,
   schemas, tests, evidence/status/package authorities, gate capture, assurance, Stage 6 and
   governance-facts validation. Documentation-only final outputs remain intentionally writable.
8. The closed governance changelog and package semantics require a truthful ten-attempt chain, but
   that closed line is not emitted while the delivery authority is pre-closure.
9. All protected Oracle, real Gmail, private repository, Secret, production workflow, deployment,
   remote write and publication counters remain zero or `NOT_RUN`. RMD-06, RMD-07 and final AC-033
   remain outside this review.

## Preserved history and output requirements

Do not delete, rewrite or reinterpret any prior request, receipt or reply. In the reply, retain the
complete applicable finding chain through `RMD05-CLOSURE-006`; mark 006 RESOLVED only if the
materialized blocked history, four pre-final validators, 19-command receipt and non-circular final
transition above genuinely resolve it. Include explicit limitations for protected Oracles, real
Gmail/private repository behavior, production, deployment, publication, RMD-06, RMD-07 and final
AC-033. Set `sensitive_data_observed=false` and `production_or_protected_claimed=false`.
