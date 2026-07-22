# Run Contract — `RUN-X2N-S02-S006`

## Identity

- Task: `TSK.x2n.skeleton.006`
- Phase: `PH.X2N.2.3`
- Stage: `STG.X2N.2`
- Task base: `2a91efbc899aaaf3f6191ba3fb93ac825e3a9a0d`
- Branch: `codex/xhs-douyin-2notion-v0001-s02-skeleton006`
- Run kind: one DAG Task only

## Objective and bounded scope

Implement Bilibili current-page capture as a public-safe `ENV-CI-SYNTH` capability. The Run may add the Bilibili detector/extractor, synthetic video/article fixtures, policy-disabled states, Side Panel/Native/SQLite E2E, verifier, compact evidence and required state documentation.

The Run must not enter Kuaishou, list capture, adapters, download/media, ASR/OCR, classification, Notion, real accounts, Owner Chrome/Profile, real Bilibili pages, OAuth/API calls or a real Canary. It must not modify the Extension Manifest, Native v1.0 action contract, lockfiles or dependency set.

## Official-first decision

Current Bilibili first-party evidence establishes OAuth plus authorized uploader video/article management, and distinguishes BVID from CID. It does not establish an arbitrary current-page, likes or favorites read capability. First-party agreements also do not establish that user-gesture DOM extraction is exempt from restrictions on automated scripts. The public article `/read/cv…` route is not proven by the current Open Platform documentation.

Therefore:

- `bilibili_current_page=ci_synth_only`;
- real pages, API use and Owner Canary remain `UNKNOWN_DISABLED/NOT_RUN`;
- article-route fixtures are an explicit unverified assumption and do not establish production readiness;
- `?p=<n>` is Fail Closed because the v1 Canonical Contract cannot retain semantic Query state without collapsing a selected part into the top-level video.

## Acceptance

- `ACC.x2n.capture.003`: 10 synthetic DOM cases, 8 policy cases, 5 ready and 5 `platform_changed`; stable Content ID and canonical Host/Path 100%; Query/Fragment persistence 0; unknown fields explicit; crawler/automatic pagination 0.
- `ACC.x2n.ext.001`: actual Side Panel click through Native Messaging to isolated SQLite; action-before-grant rejection 2; 100 Service Worker restarts; lost/duplicate/wrong jobs 0.
- Real two-item Canary: `NOT_RUN` because it lacks independent authorization and policy capability proof.

The only permitted completion status is `PASS_CI_SYNTH_SCOPED`; `G2=NOT_RUN` and Stage 2 remote upload remains forbidden.

## Verification commands

```bash
npm run self-test --workspace @x2n/extension
npm run test:bilibili-fixtures --workspace @x2n/extension
npm run test:bilibili-extension --workspace @x2n/extension
python3 -B scripts/verify_skeleton_002.py --verify-worktree --allow-external-main-dirty --require-evidence
python3 -B scripts/verify_skeleton_006.py --verify-worktree --allow-external-main-dirty --lane-report build/s02-skeleton006-final3/software-lane.json --write-evidence
python3 -B scripts/verify_skeleton_006.py --verify-worktree --allow-external-main-dirty --skip-external --lane-report build/s02-skeleton006-final3/software-lane.json --require-evidence
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

Final full-lane validation runs twice in a fresh isolated runtime. Any skip outside the existing three Owner-private optional inputs per repetition, any real network/account execution, any sensitive/CDN/runtime artifact, or any flaky/failed blocking Gate fails the Run.

## Risk, rollback and stop conditions

- Risk: public article route or page identity changes; policy/API authorization is narrower than product intent; semantic part selection is lost.
- Rollback: set `bilibili_current_page=false`, remove the adapter dispatch and keep only registered synthetic fixtures/evidence.
- Stop: a real route requires crawler behavior, automatic scrolling/pagination, undocumented endpoints, Cookie/session extraction, bypass, or a capability claim not supported by first-party evidence.
