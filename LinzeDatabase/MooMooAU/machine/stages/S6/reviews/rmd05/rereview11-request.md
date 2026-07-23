# RMD-05 twelfth independent read-only review request

Review only the immutable Git objects and exact post-candidate artifacts identified below. Do not
use Gmail, GitHub remotes, Secrets, protected Oracles, production workflows, deployment or
publication. Return exactly one UTF-8 JSON object conforming to
`machine/stages/S6/schemas/review-reply-v2.schema.json`; do not wrap it in Markdown.

## Exact target

- Baseline commit: `2b8625a83e69093b9dce989f4eb964556e1b5fa2`
- Final review anchor: `7e6dd9fe600dbdb51c4cd3eceaa26cbf74dc9670`
- Executed parent candidate: `6ad2d84efe47295075c955f66ad79ae7ad433d00`
- Shared candidate tree: `863d454cdd4827f744bb05b0e86a4b7e91b1df1d`
- Candidate receipt: `machine/stages/S6/reviews/rmd05/execution-receipt11.json`
- Receipt SHA-256: `ba180e358e2b067fa6cedeb6dcefa11aff1c59eac9998f5f403eb1abe59295c8`
- Candidate checkout: `/private/tmp/moomooau-rmd05-worktree19.eBvI5g/repository`
- Review mode: `READ_ONLY_INDEPENDENT`
- Scope: `LOCAL_SYNTHETIC_ONLY`

The reply target must use the baseline, final review anchor, shared tree and SHA-256 of this exact
request. The receipt subject intentionally names the executed parent, while the reply names its
empty same-tree child anchor. Receipt11 and this request are exact post-candidate artifacts and are
not members of the immutable candidate tree.

## Why the eleventh pair is rejected

Both eleventh reviewers returned FAIL for anchor
`8097b9b0b30590b29bcd8839cd67888b75819856`. Their replies are preserved byte-for-byte in
`final7`, and both independently used the finding ID `RMD05-CLOSURE-008` for two distinct truth
drifts:

1. Terra found that the user-visible `validate_stage6.py --review-input --help` text still said
   `nine-attempt history` although the pre-final protocol required ten completed attempts.
2. Sol found that the protected v1.0.5 package authority still encoded ten review attempts and
   fifteen candidate-bound gate commands although the then-current intended closure required
   eleven attempts and receipt10 already contained nineteen commands.

Do not rewrite or renumber either historical reply. For this twelfth review, treat
`RMD05-CLOSURE-008` as the consolidated closure requirement and mark it RESOLVED only if both
branches are genuinely fixed. The protocol necessarily advances the truthful final chain to twelve
attempts; it must not freeze the superseded eleven-attempt expectation reported before the FAIL
pair existed.

## Candidate remediation

The immutable candidate is expected to provide all of the following:

1. The Stage 6 `--review-input` help now describes the materialized `eleven-attempt rejected
   history`; a subprocess regression checks the rendered `--help` output and rejects the stale
   nine-attempt wording.
2. `validate_assurance_reviews.py` preserves the exact eleventh FAIL pair as
   `REREVIEW_FINAL_REJECTED`, permits exactly eleven attempts only with `closure_status=BLOCKED`,
   permits exactly twelve only with `closure_status=PASS`, requires 22 distinct task IDs while
   blocked and 24 when closed, and requires a twelfth pair to close the full finding history through
   `RMD05-CLOSURE-008`.
3. The v1.0.5 package builder derives its scope from
   `FINAL_REVIEW_ATTEMPTS_PER_MODEL=12`. The package validator derives
   `review_attempts_per_model_family` from the same constant and
   `candidate_bound_local_gate_commands` from `len(EXPECTED_COMMAND_IDS)=19`. Negative regressions
   reject either stale semantic count, and the fixture is self-contained rather than relying on an
   unmaterialized final package draft.
4. Stage 6 final v2 evidence advances to receipt11 while both evidence validators continue sharing
   the sole `STAGE6_TASK_COMMAND_IDS` mapping. The structured secret gate covers receipts 1 through
   11 and excludes only their legitimate receipt SHA fields from generic high-entropy detection.
5. Closed governance wording advances to a truthful twelve-attempt immutable chain, but that line
   is not emitted while delivery authority remains v1.0.4 PRE_CLOSURE.

## Non-circular two-phase protocol

This immutable target is the review input, not a fabricated post-review output. The twelfth replies
cannot exist until each reviewer returns them. Therefore their `final8` files, twelve-attempt
`closure_status=PASS` provenance records, receipt11-bound Stage 6 v2 evidence, v1.0.5 delivery
status, final package manifest and closed governance facts are intentionally absent from the
candidate tree. Do not fail solely because those necessarily post-review artifacts are absent.

The reviewed code must make the boundary fail closed:

1. Eleven completed attempts are materialized before this review. Both provenance records contain
   exactly eleven ordered attempts and 22 distinct task IDs. The eleventh attempt is
   `REREVIEW_FINAL_REJECTED`, binds request10, receipt10 and anchor
   `8097b9b0b30590b29bcd8839cd67888b75819856`, preserves both FAIL replies exactly, retains
   `RMD05-CLOSURE-008` OPEN, and the top-level record remains `closure_status=BLOCKED`.
2. `validate_assurance_reviews.py --history-only` exits zero only when that blocked history has
   `history_integrity=PASS`, `pending_final_review=true`, no integrity errors, two model families,
   22 distinct task IDs and two preserved rejected-final replies. Normal assurance remains BLOCKED
   until a schema-valid twelfth pair is appended and both verdicts are PASS.
3. `validate_stage6.py --cumulative-final --review-input` validates the v1 pre-final evidence and
   materialized history without claiming closure. Its output must say `validation_mode=REVIEW_INPUT`,
   `final_review_pending=true`, `materialized_review_passes=2`, zero protected/production effects
   and status PASS for the review-input validation itself.
4. The deterministic delivery validator passes only with package v1.0.4, the
   `RMD-05_ASSURANCE_PROVENANCE_PENDING` blocker and production readiness BLOCKED. Governance facts
   must match that honest pre-closure authority.
5. After two current PASS replies exist, the schema and validator require twelve ordered attempts,
   24 distinct task IDs, two distinct final8 replies, receipt11/anchor binding, complete finding
   closure through `RMD05-CLOSURE-008` and `closure_status=PASS`. Only then may deterministic
   post-review builders emit v1.0.5 CLOSED outputs. Any FAIL must remain PRE_CLOSURE and be
   preserved as another adverse history.

## Required verdict rule

Return `PASS` only if all four dimensions are `PASS`, every applicable prior finding is explicitly
`RESOLVED` including `RMD05-CLOSURE-006`, `RMD05-CLOSURE-007` and the consolidated two-branch
`RMD05-CLOSURE-008`, the two-phase protocol above is mechanically fail closed, and no new finding
is open. Otherwise return `FAIL`, preserve every prior finding ID and add the smallest actionable
open finding.

## Invariants to verify

1. The review anchor has exactly one parent, that parent is the executed candidate, both resolve to
   the supplied tree, and the anchor contains exactly one candidate trailer and one receipt-digest
   trailer with the supplied values.
2. Receipt11 has the supplied digest and exact baseline/executed-parent/tree subject. It is
   schema-valid and contains exactly 19 unique zero-exit commands with recomputable sanitized-output
   digests. It records 55 Stage 6 task tests, 37 affected Stage 7 tests and 25 remediation tests,
   plus Ruff, strict mypy, dependency audit, reproducible SBOM, zero secret/publication findings,
   pinned Governance, container build/smoke/cleanup, package build and the four pre-final validators.
3. Receipt11 remains `LOCAL_SYNTHETIC_ONLY`, with protected/production execution false, remote
   writes zero, sensitive data false and ephemeral outputs removed.
4. The exact eleventh replies are present and hash-pinned:
   - Sol: `b929f694b224fadc5f3391a766260a1dff49705ffe1c24ee7a0b6cb663231b73`
   - Terra: `f6acbffbffd146430423bd3e4c87814a084603fbac7b99b18e50d1cefac2d79d`
   Their shared request10 hash is
   `fe0e48fb0042f63ab599b7f49935493d21a3766cda79cd1d986faf2f54f13a88`, and receipt10 remains
   hash-pinned as `e712331a41d1755c6b8c7f6c29348252cabfc9d3ec4b563db588dd259cdfb978`.
5. The provenance schema permits exactly eleven attempts only with `closure_status=BLOCKED` and
   exactly twelve only with `closure_status=PASS`. The validator preserves the eleventh FAIL pair,
   requires the twelfth pair to close the full history, and never treats history-integrity PASS as
   closure PASS.
6. Stage 6 final v2 evidence, both evidence validators and the delivery transition require receipt11
   and the shared task-command mapping. The synchronized replacement regression still accepts a
   real same-tree anchor first, then rejects a replacement receipt even when every mutable task,
   aggregate and provenance digest is rewritten.
7. The package manifest scope, source-provenance semantic delta and negative regressions share the
   same final attempt and 19-command truth. A stale 11-attempt or 18-command value must fail.
8. Post-review protected drift covers production/effect code, all workflows, dependencies, schemas,
   tests, evidence/status/package authorities, gate capture, assurance, Stage 6 and governance-facts
   validation. Documentation-only final outputs remain intentionally writable.
9. All protected Oracle, real Gmail, private repository, Secret, production workflow, deployment,
   remote write and publication counters remain zero or `NOT_RUN`. RMD-06, RMD-07 and final AC-033
   remain outside this review.

## Preserved history and output requirements

Do not delete, rewrite or reinterpret any prior request, receipt or reply. In the reply, retain the
complete applicable finding chain through `RMD05-CLOSURE-008`. Because the two eleventh reviewers
used the same ID for different defects, a single resolved 008 entry is acceptable only when its
resolution and evidence cover both the rendered Stage 6 help and the package/provenance 12/19
truth. Include explicit limitations for protected Oracles, real Gmail/private repository behavior,
production, deployment, publication, RMD-06, RMD-07 and final AC-033. Set
`sensitive_data_observed=false` and `production_or_protected_claimed=false`.
