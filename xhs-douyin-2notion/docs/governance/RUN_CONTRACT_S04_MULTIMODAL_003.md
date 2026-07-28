# Run Contract — `RUN-X2N-S04-M003`

## Identity

- Task: `TSK.x2n.multimodal.003`
- Phase / Stage: `PH.X2N.4.3` / `STG.X2N.4`
- Task base: `60f03caa` (Task002 evidence pin)
- Branch: `codex/xhs-douyin-2notion-v0001-s03-review-resume`
- Run kind: one ordinary DAG Task and its three declared Acceptance contributions

## Objective and bounded scope

Implement a local-first OCR/Vision boundary over Task001's existing ephemeral image/keyframe artifacts. The concrete
adapter is an owner-managed local JSON protocol; this Task neither downloads, installs nor silently enables a model.
The executable and model must be Owner-managed private files below the approved Runtime model directory.

Only the following are in scope:

1. versioned local-provider descriptor, capability discovery, fixed invocation fingerprint, input/model/prompt hashes
   and opaque short-lived OCR/Vision artifact receipts;
2. JPEG/keyframe validation and a fixed offline, visible-only local JSON protocol; no shell, inherited secret
   environment, URL, credential, arbitrary prompt, arbitrary command or network client;
3. session-local same-input cache, bounded image/provider-call/timeout budget and a hard cloud kill switch;
4. OCR CER/order/duplication/no-text evaluator plus Vision visible-content/rubric/refusal evaluator, and
   `x2n eval ocr|vision --dataset <id>` equivalents that read Owner-provisioned `0600` private Gold Sets and emit
   aggregate hashes/metrics only;
5. synthetic malformed-output, timeout, cache, provenance, private-path, sensitive/unsupported-refusal, budget,
   cloud-block and cleanup tests.

This Run does not install a model, provision a Keychain secret, call a cloud provider, evaluate an Owner Gold Set,
call a platform, Chrome/Profile, Notion or a real model, persist OCR text, Vision description, raw media or media
CDN URL, write Canonical SQLite, execute fusion/classification, upload Stage 3, deploy or publish.

## Acceptance contribution and evidence

- `ACC.x2n.ai.002`: the private OCR evaluator requires at least 50 cases including at least 20 clear cases plus
  low-resolution, rotated, subtitle, watermark, table and no-text strata; median CER must be at most 12%, text order
  must be correct and duplication/no-text hallucination must be zero. No Owner Gold Set was provided or run, so OCR
  remains disabled and this Acceptance is explicitly `PENDING_PRIVATE_GOLD_OCR_DISABLED_CI_CONTRACT_PASS`, not a
  quality-pass claim.
- `ACC.x2n.ai.003`: the private Vision evaluator requires at least 40 cases, two reviewers per case, at least 80%
  major-visible-content correctness, no material hallucination or sensitive-attribute inference, and structured
  unsupported/sensitive refusal. No Owner Gold Set was provided or run, so Vision remains disabled and this
  Acceptance is explicitly `PENDING_PRIVATE_GOLD_VISION_DISABLED_CI_CONTRACT_PASS`, not a quality-pass claim.
- `ACC.x2n.ai.007`: CI verifies Provider/Model/Snapshot/Prompt/Input provenance, same-version cache without extra
  provider calls, versioned artifact identity, zero cloud budget and blocked cloud routes. It contributes
  `PASS_CI_SYNTH_TASK003_PROVENANCE_CACHE_BUDGET_CLOUD_ZERO` only.

The public receipt is `evidence/models/TSK.x2n.multimodal.003.json`. It contains no private dataset text, local
path, model file, media, CDN URL, credential or account data. The local JSON provider executable is deliberately
not supplied by this repository; it is a fixed protocol boundary, not a vendored or fetched model implementation.

## Verification

```bash
.venv/bin/python -B scripts/run_multimodal_003_acceptance.py
.venv/bin/python -B scripts/verify_multimodal_003.py --verify-worktree --run-acceptance
PYTHONPATH=apps/companion/src:packages/contracts/src \
  .venv/bin/python -B -m unittest apps.companion.tests.test_ocr_vision -v
```

When an Owner later provides a private Gold Set, the local-only oracles are:

```bash
x2n eval ocr --dataset <owner-private-dataset-id>
x2n eval vision --dataset <owner-private-dataset-id>
```

Only actual private evaluations may change OCR or Vision quality states. A `low_quality` output keeps the relevant
feature disabled or suggestion-only; it never becomes a synthetic pass.

## Rollback and stop conditions

- Rollback: disable Vision first, then OCR if required, discard session cache and preserve existing ASR/text-only
  flow; Task001 temporary-media cleaner remains responsible for lease artifacts.
- Stop: a provider would require a raw platform URL, upload media without explicit authorization, store a secret
  outside the OS Keychain, persist OCR/Vision output/raw media/CDN URL, escape the private workspace, bypass
  cache/budget, make a sensitive inference or cannot clean its output. Each case fails closed.
- This Task does not alter the direct-MVP policy: no Alpha/Beta, fixed health observation or soak; final deploy,
  run and online smoke remain solely in Stage 6 `assurance.005` after the DAG gates pass.
