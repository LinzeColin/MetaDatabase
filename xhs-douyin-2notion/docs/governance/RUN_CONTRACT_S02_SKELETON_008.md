# Run Contract — `RUN-X2N-S02-S008`

## Identity

- Task: `TSK.x2n.skeleton.008`
- Phase: `PH.X2N.2.5`
- Stage: `STG.X2N.2`
- Task base: `17f1988b309fe62071c273369f7088b7f6cc6046`
- Branch: `codex/xhs-douyin-2notion-v0001-s02-skeleton008`
- Run kind: one DAG Task only

## Objective and bounded scope

Implement Weibo current-page capture as a public-safe `ENV-CI-SYNTH` capability behind the official API/CLI-first and budget-zero gate. The Run may add the Weibo detector/extractor, public synthetic status fixtures, explicit budget/policy rejection, arbitrary-URL and Redirect-SSRF rejection, Side Panel/Native/SQLite E2E, verifier, compact evidence and required state documentation.

The Run must not enter Taobao, Weibo lists/collections, adapters, download/media, ASR/OCR, classification, Notion, real accounts, Owner Chrome/Profile, real Weibo pages, OAuth/API/CLI calls, paid tiers or a real Canary. It must not modify the Extension Manifest, Native v1.0 action contract, lockfiles or dependency set.

## Official-first and budget decision

Current Weibo first-party evidence documents OAuth and `statuses/show`, but the queried status must be authored by the authorized user. It also documents application/user/IP frequency controls, possible paid capacity, credential protection and restrictions on robot-like collection. It does not establish arbitrary public current-page read, personal likes/favorites read, an automated DOM exemption, or an approved price/scope/quota for this application. The official CLI exists but is not installed or executed in this Run.

Therefore:

- `weibo_current_page=ci_synth_only`;
- the application budget is 0 and real-shaped pages return `weibo_budget_zero_quota_unknown_disabled`;
- production API/CLI transport, OAuth/token/secret input, Cookie/Profile input, DOM fallback and Owner Canary remain disabled/not run;
- arbitrary URL preview/proxy and redirect following have no implementation surface and are rejected before execution;
- public route fixtures are explicit unverified assumptions and do not establish production readiness.

## Acceptance

- `ACC.x2n.capture.005`: 8 synthetic DOM cases, 12 policy cases, 4 ready, 4 `platform_changed`, 2 budget-blocked real-shaped cases, 16/16 arbitrary-URL/Redirect-SSRF rejects and 7 schema-drift rejects; stable synthetic `mid` and canonical Host/Path 100%; Query/Fragment, media/raw DOM and production network persistence/calls 0.
- `ACC.x2n.ext.001`: actual Side Panel click through Native Messaging to isolated SQLite; action-before-grant rejection 2; 100 Service Worker restarts; lost/duplicate/wrong jobs 0.
- Real two-item Canary: `NOT_RUN` because application approval, budget, scope, quota, route mapping and independent authorization are absent.

The only permitted completion status is `PASS_CI_SYNTH_SCOPED`; `G2=NOT_RUN` and Stage 2 remote upload remains forbidden.

## Verification commands

```bash
npm run self-test --workspace @x2n/extension
npm run test:weibo-fixtures --workspace @x2n/extension
npm run test:weibo-extension --workspace @x2n/extension
.venv/bin/python -B scripts/verify_skeleton_007.py --verify-worktree --allow-external-main-dirty --skip-external --require-evidence
.venv/bin/python -B scripts/verify_skeleton_008.py --verify-worktree --allow-external-main-dirty --lane-report build/s02-skeleton008-final3/software-lane.json --write-evidence
.venv/bin/python -B scripts/verify_skeleton_008.py --verify-worktree --allow-external-main-dirty --skip-external --lane-report build/s02-skeleton008-final3/software-lane.json --require-evidence
.venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'
```

Final full-lane validation runs twice in a fresh isolated runtime. Any skip outside the existing three Owner-private optional inputs per repetition, any real network/account/OAuth/CLI execution, any arbitrary URL/redirect transport, any sensitive/CDN/runtime artifact, or any flaky/failed blocking Gate fails the Run.

## Risk, rollback and stop conditions

- Risk: public route assumptions drift; API price, application scope or quota changes; a redirect/preview surface is introduced accidentally.
- Rollback: set `weibo_current_page=false`, remove the adapter dispatch and keep only registered synthetic fixtures/evidence.
- Stop: a real route requires an arbitrary URL proxy, unapproved paid tier, crawler behavior, automatic scrolling/pagination, undocumented endpoints, Cookie/session extraction, credential persistence, redirect following or any bypass.
