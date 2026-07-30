# Run Contract — `RUN-X2N-S04-M001`

## Identity

- Task: `TSK.x2n.multimodal.001`
- Phase / Stage: `PH.X2N.4.1` / `STG.X2N.4`
- Task base: `f0018ec5` (`G3=PASS_CI_SYNTH` independent recheck)
- Branch: `codex/xhs-douyin-2notion-v0001-s03-review-resume`
- Run kind: one ordinary DAG Task and its three declared Acceptance contributions

## Objective and bounded scope

Implement a local-only media preprocessing boundary that receives an existing temporary media lease and, while
that lease remains active, performs bounded FFprobe inspection, optional audio extraction, representative-frame
sampling, near-duplicate suppression and final cleanup.

Only the following are in scope:

1. `MediaProcessingPolicy`: maximum 64 MiB input, 120 minutes, 50 candidate frames, decoded-pixel, output,
   CPU/file-size/open-file, wall-time and FFmpeg allocation budgets;
2. `MediaToolchain`: exact local `ffmpeg`/`ffprobe`, argument construction without a shell, no inherited
   credential environment, new process group and timeout kill;
3. lease-derived `0700` workspace and crash-recoverable cleaner support for audio/frame/probe residues;
4. non-serializable ephemeral result handles plus public-safe hashes/counts/receipt only;
5. synthetic corrupt/oversize/false-MIME/image-bomb/hang/120-minute/50-frame/near-duplicate/cleanup-race tests.

This Run must not execute `TSK.x2n.multimodal.002` (ASR), `.003` (OCR/Vision), `.004` (fusion), taxonomy or
classification; it must not call a platform, Chrome/Profile, Notion or a model, persist media/CDN URL/credential,
change Canonical data, upload Stage 3, deploy or publish.

## Acceptance contribution and evidence

- `ACC.x2n.media.002`: source and all derived media are reconciled through the Lease DB; success, failure,
  expired residue, active-lease race and deletion failure stay fail-closed.
- `ACC.x2n.media.004`: malformed/false-MIME/oversize/image-bomb/hang output blocks the processor with stable
  error codes; child process limits and cleanup apply before a result can be yielded.
- `ACC.x2n.rel.004`: this Task contributes only the media-capacity portion—120-minute media samples at most
  50 candidates and dedup stays bounded. It does not claim the downstream 1k metadata or 10k Markdown checks.

The public receipt is `evidence/multimodal/TSK.x2n.multimodal.001.json`. It contains no local paths, source
media, platform URL, credential or runtime artifact. Local FFmpeg is exercised only with a temporary synthetic
fixture; this is not a real-platform media execution claim.

## Verification

```bash
.venv/bin/python -B scripts/run_multimodal_001_acceptance.py
.venv/bin/python -B scripts/verify_multimodal_001.py --verify-worktree --run-acceptance
.venv/bin/python -B -m unittest apps.companion.tests.test_media_safety \
  apps.companion.tests.test_media_preprocessing
```

## Rollback and stop conditions

- Rollback: disable the media processor and preserve existing text-only flow; lease cleaner continues to remove
  already-created temporary files.
- Stop: any parser cannot be bounded, a subprocess cannot be terminated, an active lease can be deleted, a
  derivative cannot be cleaned, or any public boundary scan finds runtime data/CDN URL/credential/path.
- This Task does not alter the direct-MVP policy: no Alpha/Beta, fixed health observation or soak; final deploy,
  run and online smoke remain solely in Stage 6 `assurance.005` after the DAG gates pass.
