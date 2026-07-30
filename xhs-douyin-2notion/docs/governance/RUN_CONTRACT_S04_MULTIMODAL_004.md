# Run Contract — `RUN-X2N-S04-M004`

## Identity

- Task: `TSK.x2n.multimodal.004`
- Phase / Stage: `PH.X2N.4.4` / `STG.X2N.4`
- Task base: `85e26fb3` (Task003 evidence pin)
- Branch: `codex/xhs-douyin-2notion-v0001-s03-review-resume`
- Run kind: one ordinary DAG Task and its two declared Acceptance contributions

## Objective and bounded scope

Implement a local-only fusion safety boundary over the existing short-lived text, ASR, OCR and Vision artifacts.
Every source and any future model response is untrusted data. The active path is deliberately a deterministic extractive
renderer followed by the exact strict parser that a later model integration must also pass. It has no provider callback,
file operation, network client, credential reader, configuration writer or action bridge.

Only the following are in scope:

1. versioned processor/model-snapshot/prompt/input/output provenance, session-local same-input cache and versioned
   artifact identity;
2. ephemeral source adapters for text, ASR, OCR and Vision, explicit missing modality reporting, source-attributed
   extractive facts, non-actionable source-divergence markers, search text and summary;
3. fixed prompt-data isolation template, Unicode/Bidi/control rejection, hostile instruction and secret-shaped-content
   rejection, and a strict JSON parser that accepts only grounded deterministic schema output;
4. synthetic normal/conflicting/missing/malicious caption-OCR-subtitle/Unicode-long-input/parser/cache/provenance/
   serialization tests and public aggregate receipt.

This Run does not provision, install or invoke a real model; call a cloud provider; read files; access a network; read a
secret; modify configuration; create or mutate any category; persist fusion/search text; write Canonical SQLite; call a
platform, Chrome/Profile, Notion or a real account; upload Stage 3; deploy or publish.

## Acceptance contribution and evidence

- `ACC.x2n.ai.004`: CI synthetic tests cover strict schema acceptance/rejection, malicious caption/OCR/subtitle,
  Unicode/Bidi, overlong input, missing/conflicting modalities and zero action surfaces. It contributes only
  `PASS_CI_SYNTH_FUSION_SCHEMA_INJECTION_ISOLATION_MODEL_NOT_RUN`; it is not a claim that a real model was evaluated or
  released.
- `ACC.x2n.ai.007`: CI verifies Processor/Model/Snapshot/Prompt/Input provenance, same-version cache without model
  calls, new-version artifact identity, zero side-effect budgets and disabled cloud. It contributes only
  `PASS_CI_SYNTH_TASK004_PROVENANCE_CACHE_BUDGET_CLOUD_ZERO`.

The public receipt is `evidence/models/TSK.x2n.multimodal.004.json`. It contains no source text, summary, search text,
private path, media, media CDN URL, credential, model output or account data. Raw outputs are intentionally not written
by this Task; any later private evaluation must retain its own raw artifacts outside the public repository.

## Verification

```bash
.venv/bin/python -B scripts/run_multimodal_004_acceptance.py
.venv/bin/python -B scripts/verify_multimodal_004.py --verify-worktree --run-acceptance
PYTHONPATH=apps/companion/src:packages/contracts/src \
  .venv/bin/python -B -m unittest apps.companion.tests.test_fusion -v
```

## Rollback and stop conditions

- Rollback: disable and discard the Fusion session/cache; retain the individual text, ASR, OCR and Vision artifacts.
- Stop: a model path gains tool, secret, file, network or configuration access; an output cannot pass strict grounding;
  hostile content can escape the data boundary; a source would be persisted without its governing sink Task. Each case
  fails closed.
- This Task does not alter the direct-MVP policy: no Alpha/Beta, fixed health observation or soak; final deploy, run and
  online smoke remain solely in Stage 6 `assurance.005` after the DAG gates pass.
