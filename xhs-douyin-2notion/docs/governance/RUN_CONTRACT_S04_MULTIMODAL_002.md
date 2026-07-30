# Run Contract — `RUN-X2N-S04-M002`

## Identity

- Task: `TSK.x2n.multimodal.002`
- Phase / Stage: `PH.X2N.4.2` / `STG.X2N.4`
- Task base: `db902304` (Task001 evidence pin)
- Branch: `codex/xhs-douyin-2notion-v0001-s03-review-resume`
- Run kind: one ordinary DAG Task and its two declared Acceptance contributions

## Objective and bounded scope

Implement a local-first ASR boundary over Task001's existing ephemeral audio artifact. The concrete adapter follows
the documented `whisper.cpp` local CLI form, but this Task neither downloads, installs nor silently enables a model.
The executable and model must be Owner-managed private files under the approved Runtime model directory.

Only the following are in scope:

1. versioned local-provider descriptor, fixed invocation fingerprint, input/model/prompt hashes and opaque
   ephemeral transcript artifact receipt;
2. M4A-to-bounded-PCM-WAV chunk normalization using the existing sandboxed FFmpeg runner, then `whisper-cli`
   JSON output validation; no shell, inherited secret environment or network client;
3. session-local same-input cache, bounded chunk/provider-call/audio/timeout budget and a hard cloud kill switch;
4. CER/WER/omission/hallucination/failure evaluator plus `x2n eval asr --dataset <id>` equivalent, which reads an
   Owner-provisioned `0600` private Gold Set and emits aggregate hashes/metrics only;
5. synthetic no-speech, malformed-output, timeout, rate/budget, cache, provenance, private-path and temporary
   cleanup tests, including a temporary synthetic FFmpeg normalization smoke.

This Run does not install a model, provision a Keychain secret, call a cloud provider, evaluate an Owner Gold Set,
call a platform, Chrome/Profile, Notion or a real model, persist a transcript/raw media/CDN URL, write Canonical
SQLite, execute OCR/Vision/Fusion/Classification, upload Stage 3, deploy or publish.

## Acceptance contribution and evidence

- `ACC.x2n.ai.001`: the evaluator enforces at least 20 clear-Mandarin cases plus noise/music/dialect/mixed-language/
  no-speech strata, provenance on every private row, median CER and zero no-speech hallucinations. No Owner Gold Set
  was provided or run in this Task, so the ASR feature remains disabled and this Acceptance is explicitly
  `PENDING_PRIVATE_GOLD_ASR_DISABLED_CI_CONTRACT_PASS`, not a quality-pass claim.
- `ACC.x2n.ai.007`: CI verifies Provider/Model/Snapshot/Prompt/Input hash handling, same-version cache without extra
  provider calls, versioned artifact identity, zero cloud budget and blocked cloud route. It contributes
  `PASS_CI_SYNTH_PROVENANCE_CACHE_BUDGET_CLOUD_ZERO` only.

The public receipt is `evidence/models/TSK.x2n.multimodal.002.json`. It contains no private dataset text, local
path, model file, media, CDN URL, credential or account data. The local CLI syntax is based on the upstream
[`whisper.cpp` CLI documentation](https://github.com/ggml-org/whisper.cpp/blob/master/examples/cli/README.md); no
upstream code, binary or model is vendored or fetched by this Task.

## Verification

```bash
.venv/bin/python -B scripts/run_multimodal_002_acceptance.py
.venv/bin/python -B scripts/verify_multimodal_002.py --verify-worktree --run-acceptance
PYTHONPATH=apps/companion/src:packages/contracts/src \
  .venv/bin/python -B -m unittest apps.companion.tests.test_asr -v
```

When an Owner later provides a private Gold Set, the equivalent local-only oracle is:

```bash
x2n eval asr --dataset <owner-private-dataset-id>
```

Only an actual private evaluation may change the ASR quality state. A `low_quality` output keeps ASR disabled or
suggestion-only; it never becomes a synthetic pass.

## Rollback and stop conditions

- Rollback: keep the existing text-only flow, disable the ASR route and discard session cache; Task001 temporary
  media cleaner remains responsible for lease artifacts.
- Stop: a provider would upload audio without explicit authorization, store a secret outside the OS Keychain,
  persist transcript/raw media/CDN URL, escape the private workspace, bypass cache/budget, or cannot clean its
  normalized audio. Each case fails closed.
- This Task does not alter the direct-MVP policy: no Alpha/Beta, fixed health observation or soak; final deploy,
  run and online smoke remain solely in Stage 6 `assurance.005` after the DAG gates pass.
