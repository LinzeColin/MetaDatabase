# Run Contract — `RUN-X2N-S04-M005`

## Identity

- Task: `TSK.x2n.multimodal.005`
- Phase / Stage: `PH.X2N.4.5` / `STG.X2N.4`
- Task base: `0c2eb423` (Task004 evidence pin)
- Branch: `codex/xhs-douyin-2notion-v0001-s03-review-resume`
- Run kind: one ordinary DAG Task and its three declared Acceptance contributions

## Objective and bounded scope

Implement the Owner-governed taxonomy and classification boundary that turns existing multimodal artifacts into
recoverable, reviewable category suggestions. The Owner Registry alone can create, rename, disable or merge a
top-level category. It records an append-only revision for every effective change. The deterministic classifier only
receives a frozen taxonomy snapshot and in-memory artifact text; it has no Store, registry, network, model, tool,
credential, configuration or platform capability.

Only the following are in scope:

1. SQLite migration v4 for append-only Owner taxonomy revisions, stable category IDs, disabled/unknown category
   rejection, non-deleting taxonomy history and classification FK/version checks;
2. deterministic local lexical rule selection over Owner names, aliases and positive/negative examples; bounded
   session cache, model/snapshot/ruleset/input provenance, versioned suggestion identity and no persistent source text;
3. calibrated private Gold Set evaluator and `x2n eval classify --dataset <id>` oracle that emits hashes and aggregate
   metrics only; a matching private `>=100` case evaluation with high-confidence precision `>=90%`, reported 95% CI,
   representative enabled categories and Macro-F1 reference `>=0.80` is required before an auto-accept gate can exist;
4. suggestion-only default, Owner confirmation/correction append-only Classification revisions, synthetic
   unknown/disabled/rename/merge/cache/provenance/low-quality/CLI/private-path tests and public aggregate receipt.

This Run does not supply an Owner taxonomy or Owner Gold Set; enable automatic classification; create a category from
AI output; persist a fusion summary, transcript, OCR, Vision text, raw media or media CDN URL; call a real model,
cloud provider, platform, Chrome/Profile, Notion or real account; read a credential; use a shared Token; upload Stage
3; deploy or publish. It also does not execute G4; the independent G4 review is the next run.

## Acceptance contribution and evidence

- `ACC.x2n.ai.005`: CI synthetic tests prove Owner-only top-level registry semantics, stable IDs on rename,
  append-only revisions, disabled/unknown category rejection and Owner review correction. It contributes
  `PASS_CI_SYNTH_OWNER_TAXONOMY_REGISTRY_REVISION_REVIEW_SUGGESTION_ONLY`.
- `ACC.x2n.ai.006`: the private evaluator and calibration/gate path exist, but no Owner taxonomy or Gold Set was
  provided or run. Therefore the only active disposition is suggestion-only and this status is
  `PENDING_PRIVATE_GOLD_CLASSIFICATION_SUGGESTION_ONLY_CI_CONTRACT_PASS`, not an accuracy claim.
- `ACC.x2n.ai.007`: CI proves deterministic Processor/Model/Snapshot/Ruleset/Input provenance, same-input cache,
  changed-version identity, zero model/network/cloud budgets and zero AI taxonomy mutation. It contributes only
  `PASS_CI_SYNTH_TASK005_PROVENANCE_CACHE_BUDGET_CLOUD_ZERO`.

The public receipt is `evidence/models/TSK.x2n.multimodal.005.json`. It contains no category examples, content text,
private Gold data, local path, credential, raw media or CDN URL. Any Owner Gold Set remains a `0600` private-runtime
file below the fixed diagnostics root and is read only by the explicit local evaluator.

## Verification

```bash
.venv/bin/python -B scripts/run_multimodal_005_acceptance.py
.venv/bin/python -B scripts/verify_multimodal_005.py --verify-worktree --run-acceptance
PYTHONPATH=apps/companion/src:packages/contracts/src \
  .venv/bin/python -B -m unittest apps.companion.tests.test_taxonomy -v
```

When the Owner later provides a private taxonomy and Gold Set, the only local oracle is:

```bash
x2n eval classify --dataset <owner-private-dataset-id>
```

`LOW_QUALITY`, a stale snapshot/fingerprint, insufficient strata/coverage, or any unknown/disabled category keeps
`auto_classify=false`; it never routes content automatically.

## Rollback and stop conditions

- Rollback: keep `auto_classify=false`, discard classifier cache/calibration gate and retain the Unclassified Inbox
  plus Owner review. No category or historical classification is deleted.
- Stop: a classifier can mutate taxonomy; a category is accepted when unknown or disabled; private Gold metrics enable
  routing without a matching snapshot/provenance receipt; high-confidence precision remains below 85% after
  calibration while auto routing is on; any source text, credential, media/CDN URL or local path reaches public code
  or evidence. Each case fails closed.
- This Task does not alter the direct-MVP policy: no Alpha/Beta, fixed health observation or soak; final deploy, run
  and online smoke remain solely in Stage 6 `assurance.005` after the DAG gates pass.
