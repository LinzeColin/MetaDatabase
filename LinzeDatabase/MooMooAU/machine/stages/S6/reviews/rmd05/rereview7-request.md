# RMD-05 final independent re-review request after immutable receipt anchoring

Review exactly the immutable Git anchor candidate, its identical executed tree, and the
candidate-bound local receipt below. This is a read-only independent review. Do not edit files,
execute protected Oracles, invoke production workflows, access Gmail or any private repository,
request Secrets, publish, push, or infer remote or production success from local evidence.

## Immutable target and two-commit anchor

- Repository baseline: `2b8625a83e69093b9dce989f4eb964556e1b5fa2`
- Executed candidate commit: `65b91c8094481f18026a90b6b7778716df8f708e`
- Final review anchor commit: `d257042ab16347d75c23db145b24f24b0306d56f`
- Shared candidate tree: `3a3296c7e68b8c1ad811e6c8e2b6ca03046f848c`
- Final candidate receipt: `machine/stages/S6/reviews/rmd05/execution-receipt7.json`
- Receipt SHA-256: `820b18a3c45891db7ab05d2ed95fed2593f81546dcb7031ce5fc96d707386b1d`
- Receipt scope: `LOCAL_SYNTHETIC_ONLY`; 15 unique zero-exit commands; protected/production
  execution false; remote writes zero; ephemeral image removed.

The anchor commit must have exactly one parent, the executed candidate above, and both commits
must resolve to the exact same tree. The anchor commit message must contain exactly these trailers:

```text
MooMooAU-Execution-Candidate: 65b91c8094481f18026a90b6b7778716df8f708e
MooMooAU-Execution-Receipt-SHA256: 820b18a3c45891db7ab05d2ed95fed2593f81546dcb7031ce5fc96d707386b1d
```

This avoids an impossible self-reference: local gates execute the complete tree first, then an
empty child commit with the same tree immutably pins the resulting receipt digest. The receipt and
this request are intentionally post-execution inputs. The invocation supplies the SHA-256 of this
exact request. Bind the reply target to the baseline, final review anchor commit, shared tree, and
request hash above; do not bind the reply target to the executed parent commit.

## Required review dimensions

Return one result for each exact ID: `SCOPE`, `EVIDENCE_QUALITY`, `FAILURE_HONESTY`, and
`ROLLBACK`. A final `PASS` is permitted only if all four dimensions pass and every finding in this
reviewer's complete eight-attempt history is explicitly `RESOLVED`. Otherwise return `FAIL` and at
least one `OPEN` finding with a concrete required fix.

## Preserved history to verify

The repository must preserve all earlier artifacts byte-for-byte and implement eight ordered
attempts per model family with sixteen distinct platform task IDs across the two families:

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
   under `final2/`, superseded after output integration exposed `RMD05-CLOSURE-004`.
6. `REREVIEW_EVIDENCE_COUPLING_ADVERSE`: candidate
   `c9ebf210e3397cd1626faa959aed3b3ddfdc66a1`, tree
   `ddd43a4837bb1766ae4b3c6f8b3ae262edeae151`, request5 SHA-256
   `45e531415d8176d599f7573f22770b5110211a41c724f524fccd9dbc590dc2d7`, receipt5 SHA-256
   `407519737d85e754ad6b4b9fdc4cbb0f2a182b5c60d9f9b90bd8a71db8525465`, Sol FAIL and Terra
   PASS under `rereview5/`. Sol opened `RMD05-CLOSURE-005` for the v1/CLOSED crossing.
7. `REREVIEW_RECEIPT_ANCHOR_ADVERSE`: candidate
   `f459d504b62d4a528858dcc3321a58f8218b160f`, tree
   `2bf05a0209738a97c73535292f30aa1882a1f372`, request6 SHA-256
   `4f3a7f841691095985649545f09ecbf531a7bb9908bfbc6d318d541cdd396d78`, receipt6 SHA-256
   `9c1b087a4d24f49069305b1892553f6ab7d579892cc71bfa77ff0e102d143650`, Sol PASS and Terra
   FAIL under `final3/`. Preserve this mixed verdict exactly. Terra kept
   `RMD05-CLOSURE-005` OPEN because all post-candidate receipt/evidence/provenance outputs could be
   synchronously replaced without an immutable digest anchor.
8. `REREVIEW_FINAL`: this request, receipt7, and the fresh independent reply targeting the final
   review anchor commit.

The final reply must cover its model family's complete history and explicitly include
`RMD05-CLOSURE-002`, `RMD05-CLOSURE-003`, `RMD05-CLOSURE-004`, and
`RMD05-CLOSURE-005` as `RESOLVED` for a PASS. Do not erase, relabel as final, or reinterpret any
prior FAIL/PASS record.

## Root defect and repair to inspect adversarially

The seventh Terra review correctly found that the previous immutable candidate did not pin the
exact final receipt digest. An attacker could replace receipt6 and synchronize all allowed
post-review evidence, provenance and status outputs. The new design must close that path without
pretending a post-execution receipt can be embedded in the commit that generated it.

Verify all of the following:

- `validate_stage6_receipt_anchor` requires the review anchor to resolve to the declared tree, have
  exactly one parent equal to the receipt's executed candidate, require that parent's tree and the
  receipt subject tree to equal the review tree, and require exactly one matching execution
  candidate trailer and exact receipt SHA-256 trailer.
- `validate_stage6_candidate_bundle` invokes this Git anchor when used by CLOSED delivery status;
  `build_delivery_status.py`, `validate_delivery_status.py`, and the Stage 6 validator supply the
  real repository root rather than using the unanchored synthetic-test mode.
- `validate_assurance_reviews.py` independently enforces the anchor for status construction even
  before the final output commit, validates receipt7 against the executed parent/tree, targets
  final replies at the anchor commit/tree, and still applies protected post-review drift checks
  from the anchor to the delivery HEAD.
- The regression `test_rmd05_git_anchor_rejects_synchronized_receipt_bundle_replacement` first
  proves a valid same-tree anchor, then replaces receipt7 and synchronizes every task binding,
  aggregate binding, and top/final provenance receipt hash; validation must still fail on the
  immutable trailer digest.
- The v1/v2 transition fix remains intact: PRE_CLOSURE requires all eight Stage 6 task records to
  be v1; CLOSED requires receipt7-bound v2 task records plus the aggregate, exact command subsets,
  local-only observations and zero/NOT_RUN counters.
- The provenance schema and validator require eight exact ordered attempts, sixteen distinct task
  IDs, exact historical hashes/verdicts including both mixed attempts, the same final anchor
  candidate/request/receipt, two distinct final replies, full finding closure, and no protected
  code changes after the anchor.
- Package validation records eight attempts per family. The secret gate still rejects sensitive
  patterns while allowing deterministic Git/artifact hashes.
- Protected Oracles, Gmail, the private repository, production workflows, external writes, remote
  publication, RMD-06, RMD-07, and final AC-033 remain unexecuted and unclaimed.

The final top-level provenance wrappers, v2 task/aggregate evidence, v1.0.5 status and taskpack are
deterministic post-review outputs. Look for any alternative receipt that can pass with the fixed
anchor, any changed-tree anchor, parent ambiguity, duplicated/omitted trailer, unanchored CLOSED
builder path, lost history, post-review protected-code mutation path, or production overclaim. Any
such path is blocking.

## Reply contract

Return only one UTF-8 JSON object followed by one LF, conforming to
`machine/stages/S6/schemas/review-reply-v2.schema.json`. Use the requested model family exactly.
The reply must contain:

- the exact baseline/final-anchor/tree/request SHA-256 target;
- `review_mode: READ_ONLY_INDEPENDENT`;
- one verdict and exactly the four required dimensions with evidence references and rationale;
- all applicable historical and newly found findings, each `RESOLVED` or `OPEN` as required;
- honest limitations that local evidence does not prove protected Oracles, real Gmail/private
  repository behavior, production health, deployment, publication, RMD-06, RMD-07, or final
  AC-033;
- `sensitive_data_observed: false` and `production_or_protected_claimed: false` unless the review
  actually observed otherwise, in which case fail closed without reproducing sensitive content.
