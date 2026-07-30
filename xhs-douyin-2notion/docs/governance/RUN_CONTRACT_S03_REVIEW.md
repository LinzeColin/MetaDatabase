# Run Contract — Stage 3 Review

## Identity

- Review: `STG.X2N.3.REVIEW`
- Run: `RUN-X2N-S03-REVIEW`
- Branch: `codex/xhs-douyin-2notion-v0001-s03-review`
- Stage base: `ee5d251ca30eab226c4df75c53965f312c2d9b05`
- Review base / sync target: `a67ba091239297b5c9c38a349e0a839680d1c411`
- Parent / child: `LinzeColin/MetaDatabase` / `xhs-douyin-2notion`
- Expected decision: `REVIEW_COMPLETE / G3_BLOCKED_TECHNICAL_AND_OWNER_CLARIFICATION`
- Required next run: `STG.X2N.3.REVIEW.RESUME`

This is a Stage Review exception that executes no new DAG Task. It may repair defects
inside completed Stage 3 scope, re-run all nine task acceptances, and emit a gate
decision. It may not invent a tenth Task, wire a production batch path prohibited by
an earlier one-Task Run Contract, run real accounts, authorize Stage 4, or upload.

## Scope

The Review takes the union of:

1. all outputs, tests, evidence and Stop Conditions of
   `TSK.x2n.adapters.001–004,006–009,005`;
2. the 19 unique Acceptance IDs referenced by those Tasks;
3. all four Taskpack G3 conditions;
4. the Roadmap eight-by-twenty sample, completeness, silent-loss, duplicate,
   incremental, expiry, checkpoint and privacy oracles;
5. public repository and Stage 3 history privacy.

External shared authentication material remains outside x2n. This Run does not read,
use, display, persist, rotate, delete or modify it, and does not treat its external
existence as a G3 blocker.

## Allowed Review Fixes

- make explicit Owner removal terminal at the Canonical write boundary and preserve it
  in exact full-scan proof;
- harden XHS extension/Python envelope validation;
- add real child-process kill coverage to the Douyin Canonical adapter;
- persist a private batch comparison and emit public aggregate incremental evidence;
- replace unexercised zero claims with an 80-row
  Adapter→Canonical→Artifact→Markdown→Notion Mock/Outbox E2E;
- align versioned XHS checkpoint policies and pin historical A005 verification.

No fix may persist CDN URLs, credentials, profiles or raw media; automatically scroll,
change an account state, create an Owner top-level category, weaken exact replay, or
rewrite historical Task Evidence.

## G3 Decision Rules

`G3=PASS` requires all of the following simultaneously:

- the nine Task receipts and 19-Acceptance union are valid;
- all eight relation/list canaries are `PASS` under their independent policy and
  authorization gates;
- checkpoint/resume and empty-response deletion protection pass;
- batch failure exposes an executable `FALLBACK_AVAILABLE` state and current-page
  capture occurs only after a second explicit Owner action;
- the public/private/history scan is zero;
- no blocker remains.

The current implementation cannot satisfy that rule:

- Chrome and Native Host have no executable relation/list dispatch; `START_SYNC`
  remains `native_sync_skeleton`;
- batch failure→current-page is text, not an executable state or E2E;
- all eight real canaries and private manifests are `NOT_RUN`;
- the contract does not say whether a conditionally authorized or
  `UNKNOWN_DISABLED` canary can legally complete G3;
- full `ACC.x2n.data.002` / `ACC.x2n.rel.006` spans Stage 4–6 and Owner Alpha, while
  A005 only owns a Stage 3 contribution.

Therefore the only honest decision is
`BLOCKED_TECHNICAL_AND_OWNER_CLARIFICATION`. `BLOCKED_*` is not `PASS`.

## Verification

```bash
.venv/bin/python -B scripts/run_stage_3_review_acceptance.py
.venv/bin/python -B scripts/verify_stage_3_review.py \
  --verify-worktree --allow-external-main-dirty --run-acceptance
.venv/bin/python -B scripts/ci/run_lane.py \
  --lane full --repetitions 2 --reports-dir build/s03-review
.venv/bin/python -B scripts/verify_stage_3_review.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/s03-review/software-lane.json --require-evidence
```

## Stop and Resume

Stage 3 upload and Stage 4 remain forbidden. Resume requires an Owner-versioned
decision that:

1. authorizes a new relation/list orchestration Task with strict Native dispatch and
   explicit, non-automatic current-page fallback;
2. defines the legal terminal state for every one of the eight canaries;
3. splits the Stage 3 CI-synthetic contribution from full Stage 6
   `ACC.x2n.rel.006` Owner Alpha;
4. independently authorizes only the real canaries whose Policy/Auth/Technical gates
   are then satisfied.

Private Manifest content remains outside Git. A Resume must re-run the full Review and
sign a new G3 decision; it must not edit this blocked evidence into PASS.
