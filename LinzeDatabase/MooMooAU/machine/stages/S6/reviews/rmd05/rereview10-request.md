# RMD-05 eleventh independent read-only review request

Review only the immutable Git objects and exact post-candidate artifacts identified below. Do not
use Gmail, GitHub remotes, Secrets, protected Oracles, production workflows, deployment or
publication. Return exactly one UTF-8 JSON object conforming to
`machine/stages/S6/schemas/review-reply-v2.schema.json`; do not wrap it in Markdown.

## Exact target

- Baseline commit: `2b8625a83e69093b9dce989f4eb964556e1b5fa2`
- Final review anchor: `8097b9b0b30590b29bcd8839cd67888b75819856`
- Executed parent candidate: `4c60dd977250f94218730f335b8fdd06665fcbde`
- Shared candidate tree: `27dfadaa1328c2ff0e2648c78a914c176a74f4ff`
- Candidate receipt: `machine/stages/S6/reviews/rmd05/execution-receipt10.json`
- Receipt SHA-256: `e712331a41d1755c6b8c7f6c29348252cabfc9d3ec4b563db588dd259cdfb978`
- Candidate checkout: `/private/tmp/moomooau-rmd05-worktree17.1cSUdb/repository`
- Review mode: `READ_ONLY_INDEPENDENT`
- Scope: `LOCAL_SYNTHETIC_ONLY`

The reply target must use the baseline, final review anchor, shared tree and SHA-256 of this exact
request. The receipt subject intentionally names the executed parent, while the reply names its
empty same-tree child anchor.

## Why the tenth PASS pair is superseded

The tenth Sol and Terra reviews both returned PASS for anchor
`3cd4a4122016ce9b3af8d42901d6d0c968ae981a`. The post-review mechanical closure then found that
`machine/tools/validate_evidence.py` required T0606 to bind five receipt commands while
`machine/stages/S6/tools/validate_stage6.py` independently accepted only `stage6-task-tests`.
No Stage 6 v2 evidence bundle could satisfy both validators. The two PASS replies are preserved
byte-for-byte as a superseded closure-path attempt; they are not treated as current authority.

The candidate removes that duplicate truth source: Stage 6 imports and uses the shared
`STAGE6_TASK_COMMAND_IDS`, and a focused regression rejects reintroduction of a local duplicate.
The final receipt/evidence path advances to receipt10. The secret gate continues structured
sensitive-pattern inspection of every receipt while excluding their legitimate SHA-256 fields
from generic high-entropy detection. Treat this newly discovered incompatibility as
`RMD05-CLOSURE-007`; return PASS only if it is genuinely RESOLVED.

## Non-circular two-phase protocol

This immutable target is the review input, not a fabricated post-review output. The current
eleventh-attempt replies cannot exist until each reviewer returns them. Therefore their `final7`
files, eleven-attempt `closure_status=PASS` provenance records, receipt10-bound Stage 6 v2
evidence, v1.0.5 delivery status and closed governance facts are intentionally absent from this
candidate tree. Do not fail solely because those necessarily post-review artifacts are absent.

The reviewed code must make that boundary fail closed:

1. Ten completed attempts are materialized before this review. Both provenance records contain
   exactly ten ordered attempts and 20 distinct task IDs. The tenth attempt is
   `REREVIEW_CLOSURE_PATH_SUPERSEDED`, binds request9, receipt9 and anchor
   `3cd4a4122016ce9b3af8d42901d6d0c968ae981a`, preserves both PASS replies exactly, and the
   top-level record remains `closure_status=BLOCKED`.
2. `validate_assurance_reviews.py --history-only` exits zero only when that blocked history has
   `history_integrity=PASS`, `pending_final_review=true`, no integrity errors, two model families
   and 20 distinct task IDs. Normal assurance remains `BLOCKED` until a schema-valid eleventh pair
   is appended and both verdicts are PASS.
3. `validate_stage6.py --cumulative-final --review-input` validates the v1 pre-final evidence and
   materialized history without claiming closure. Its output must say `validation_mode=REVIEW_INPUT`,
   `final_review_pending=true`, `materialized_review_passes=2`, zero protected/production effects
   and status PASS for the review-input validation itself.
4. The deterministic delivery validator passes only with package v1.0.4, the
   `RMD-05_ASSURANCE_PROVENANCE_PENDING` blocker and production readiness BLOCKED. The governance
   facts check must match that honest pre-closure authority.
5. After two current PASS replies exist, the same schema/validator requires eleven ordered
   attempts, 22 distinct task IDs, two distinct final7 replies, receipt10/anchor binding, complete
   finding closure through `RMD05-CLOSURE-007` and `closure_status=PASS`. Only then may
   deterministic post-review builders emit v1.0.5 CLOSED outputs. Any FAIL keeps PRE_CLOSURE and
   must be preserved as another adverse history.

## Required verdict rule

Return `PASS` only if all four dimensions are `PASS`, every applicable prior finding is explicitly
`RESOLVED` including `RMD05-CLOSURE-006` and `RMD05-CLOSURE-007`, the two-phase protocol above is
mechanically fail closed, and no new finding is open. Otherwise return `FAIL`, preserve every prior
finding ID and add the smallest actionable open finding.

## Invariants to verify

1. The review anchor has exactly one parent, that parent is the executed candidate, both resolve to
   the supplied tree, and the anchor contains exactly one candidate trailer and one receipt-digest
   trailer with the supplied values.
2. Receipt10 has the supplied digest and exact baseline/executed-parent/tree subject. It contains
   exactly 19 unique zero-exit commands with recomputable sanitized-output digests. In addition to
   Ruff, strict mypy, 55 Stage 6 tests, 37 affected Stage 7 tests, 22 remediation tests, dependency
   audit, reproducible SBOM, zero secret/publication findings, pinned Governance, container
   build/smoke/cleanup and package build, it records the four pre-final validators described above.
3. Receipt10 remains `LOCAL_SYNTHETIC_ONLY`, with protected/production execution false, remote
   writes zero, sensitive data false and ephemeral outputs removed.
4. The exact tenth replies are present and hash-pinned:
   - Sol: `9a7ce284b6ce71106b4b6ff3a5337c67887e8647b0db13d4b77f6a79e6da24a7`
   - Terra: `d5cb77bd8292de829ba213c5daad079c8157e351d6840754006cac4f7b9e24d2`
   Both remain PASS in the historical files, but their attempt phase and top-level BLOCKED state
   make clear that the later command-binding incompatibility superseded them.
5. The provenance schema permits exactly ten attempts only with `closure_status=BLOCKED` and
   exactly eleven only with `closure_status=PASS`. The validator preserves the tenth PASS pair,
   requires the eleventh pair to close the full finding history, and never treats history-integrity
   PASS as closure PASS.
6. Stage 6 final v2 evidence, both evidence validators and the delivery transition require
   receipt10 and the same shared task-command mapping. The synchronized replacement regression
   still accepts a real same-tree anchor first, then rejects a replacement receipt even when every
   mutable task, aggregate and provenance digest is rewritten.
7. Post-review protected drift covers production/effect code, all workflows, dependencies,
   schemas, tests, evidence/status/package authorities, gate capture, assurance, Stage 6 and
   governance-facts validation. Documentation-only final outputs remain intentionally writable.
8. The closed governance changelog and package semantics require a truthful eleven-attempt chain,
   but that closed line is not emitted while the delivery authority is pre-closure.
9. All protected Oracle, real Gmail, private repository, Secret, production workflow, deployment,
   remote write and publication counters remain zero or `NOT_RUN`. RMD-06, RMD-07 and final AC-033
   remain outside this review.

## Preserved history and output requirements

Do not delete, rewrite or reinterpret any prior request, receipt or reply. In the reply, retain the
complete applicable finding chain through `RMD05-CLOSURE-007`; mark 007 RESOLVED only if the shared
command-binding source, receipt10 path, negative regressions, 19-command receipt and non-circular
final transition genuinely resolve it. Include explicit limitations for protected Oracles, real
Gmail/private repository behavior, production, deployment, publication, RMD-06, RMD-07 and final
AC-033. Set `sensitive_data_observed=false` and `production_or_protected_claimed=false`.
