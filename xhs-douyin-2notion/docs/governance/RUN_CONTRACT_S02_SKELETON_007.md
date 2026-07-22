# Run Contract — `RUN-X2N-S02-S007`

## Identity

- Task: `TSK.x2n.skeleton.007`
- Phase: `PH.X2N.2.4`
- Stage: `STG.X2N.2`
- Task base: `a314a1d049998eae6a052ea8900aa5ac448cb2ca`
- Branch: `codex/xhs-douyin-2notion-v0001-s02-skeleton007`
- Run kind: one DAG Task only

## Objective and bounded scope

Implement Kuaishou current-page capture as a public-safe `ENV-CI-SYNTH` capability behind an OAuth/API-first gate. The Run may add the Kuaishou detector/extractor, synthetic video fixtures, explicit `BLOCKED_AUTH` states, Side Panel/Native/SQLite E2E, verifier, compact evidence and required state documentation.

The Run must not enter Weibo, list capture, adapters, download/media, ASR/OCR, classification, Notion, real accounts, Owner Chrome/Profile, real Kuaishou pages, OAuth/API calls or a real Canary. It must not modify the Extension Manifest, Native v1.0 action contract, lockfiles or dependency set.

## Official-first decision

Current Kuaishou first-party evidence establishes OAuth, application registration, dynamic consent and the `user_video_info` scope. That scope exposes an authorized user's published work list and `photoId` details. It does not establish arbitrary public current-page access, likes/favorites access, or permission for automated DOM collection. The public `/short-video/<id>` route is not proven by the current Open Platform documentation.

Therefore:

- `kuaishou_current_page=ci_synth_only`;
- real-shaped pages return `BLOCKED_AUTH` while scope is absent;
- production API transport, Access Token input, Cookie/Profile input and Owner Canary remain disabled/not run;
- route fixtures are an explicit unverified assumption and do not establish production readiness.

## Acceptance

- `ACC.x2n.capture.004`: 8 synthetic DOM cases, 10 policy cases, 4 ready, 4 `platform_changed`, 2 `BLOCKED_AUTH`; stable `photoId` and canonical Host/Path 100%; Query/Fragment persistence 0; unknown fields explicit; Cookie reads and crawler/automatic pagination 0.
- `ACC.x2n.ext.001`: actual Side Panel click through Native Messaging to isolated SQLite; action-before-grant rejection 2; 100 Service Worker restarts; lost/duplicate/wrong jobs 0.
- Real two-item Canary: `NOT_RUN` because approved application/scope, route mapping and independent authorization are absent.

The only permitted completion status is `PASS_CI_SYNTH_SCOPED`; `G2=NOT_RUN` and Stage 2 remote upload remains forbidden.

## Verification commands

```bash
npm run self-test --workspace @x2n/extension
npm run test:kuaishou-fixtures --workspace @x2n/extension
npm run test:kuaishou-extension --workspace @x2n/extension
python3 -B scripts/verify_skeleton_006.py --verify-worktree --allow-external-main-dirty --skip-external --require-evidence
python3 -B scripts/verify_skeleton_007.py --verify-worktree --allow-external-main-dirty --lane-report build/s02-skeleton007-final/software-lane.json --write-evidence
python3 -B scripts/verify_skeleton_007.py --verify-worktree --allow-external-main-dirty --skip-external --lane-report build/s02-skeleton007-final/software-lane.json --require-evidence
python3 -B -m unittest discover -s tests -p 'test_*.py'
```

Final full-lane validation runs twice in a fresh isolated runtime. Any skip outside the existing three Owner-private optional inputs per repetition, any real network/account/OAuth execution, any sensitive/CDN/runtime artifact, or any flaky/failed blocking Gate fails the Run.

## Risk, rollback and stop conditions

- Risk: public route assumptions drift; OAuth scope is unavailable or narrower than product intent; consent/revocation requirements change.
- Rollback: set `kuaishou_current_page=false`, remove the adapter dispatch and keep only registered synthetic fixtures/evidence.
- Stop: a real route requires crawler behavior, automatic scrolling/pagination, undocumented endpoints, Cookie/session extraction, signature/bypass, or any capability outside approved `user_video_info` consent.
