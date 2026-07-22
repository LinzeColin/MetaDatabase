# Run Contract — `RUN-X2N-S02-S009`

## Identity

- Task: `TSK.x2n.skeleton.009`
- Phase: `PH.X2N.2.6`
- Stage: `STG.X2N.2`
- Task base: `7e8a3dbf3c4c27643330489353ed162130fba506`
- Branch: `codex/xhs-douyin-2notion-v0001-s02-skeleton009`
- Run kind: one DAG Task only

## Objective and bounded scope

Implement Taobao current-item-page capture as a public-safe `ENV-CI-SYNTH` capability behind official OAuth/API-first, application approval, data-scope and retention gates. The Run may add the Taobao detector/extractor, public synthetic item fixtures, explicit policy/retention rejection, undocumented MTop/Cookie-signature rejection, Side Panel/Native/SQLite E2E, verifier, compact evidence and required state documentation.

The Run must not enter temporary media, URL scrubber, Taobao lists/collections, adapters, download/media, ASR/OCR, classification, Notion, real accounts, Owner Chrome/Profile, real Taobao pages, OAuth/TOP API calls, paid API use or a real Canary. It must not modify the Extension Manifest, Native v1.0 action contract, lockfiles or dependency set.

## Official-first and retention decision

Current first-party evidence documents `taobao.item.get` as an authorized value-added API with `num_iid` and an `item.htm?id=...` detail URL. TOP documents OAuth for private goods/order/favorites data, application credentials and an official signed API protocol. Platform privacy rules require purpose/scope disclosure, deletion on withdrawal/end/retention expiry and prohibit crawling platform data. The application has no approved AppKey, OAuth grant, item API permission, paid plan, field scope, retention/deletion receipt or Owner Canary.

Therefore:

- `taobao_current_page=ci_synth_only` and real pages remain `UNKNOWN_DISABLED`;
- production TOP API/OAuth transport, credentials, Cookie/Profile input and DOM fallback remain disabled/not run;
- documented TOP API signing is a future Local Companion-only route and is not implemented in this Run;
- undocumented browser MTop/Cookie signing, signature-material input and non-item query keys are rejected before execution at 100%;
- page observation verifies the first-party-proven semantic `id`, then persists that value only as `content_id=num_iid`; Canonical URL retains the official Host/Path with Query/Fragment 0, preserving the existing Native v1 contract;
- public route fixtures are explicit unverified assumptions and do not establish production readiness.

## Acceptance

- `ACC.x2n.capture.006`: 8 synthetic DOM cases, 14 policy cases, 4 ready, 4 `platform_changed`, 2 scope/retention-blocked real-shaped cases, 16/16 undocumented-signature rejects and 7 schema-drift rejects; stable synthetic `num_iid` and canonical Host/Path 100%; Query/Fragment, media/raw DOM and production network persistence/calls 0.
- `ACC.x2n.ext.001`: actual Side Panel click through Native Messaging to isolated SQLite; action-before-grant rejection 2; 100 Service Worker restarts; lost/duplicate/wrong jobs 0.
- Real two-item Canary: `NOT_RUN` because application approval, OAuth, paid API authorization, field scope, retention/deletion design and independent authorization are absent.

The only permitted completion status is `PASS_CI_SYNTH_SCOPED`; `G2=NOT_RUN` and Stage 2 remote upload remains forbidden.

## Verification commands

```bash
npm run self-test --workspace @x2n/extension
npm run test:taobao-fixtures --workspace @x2n/extension
npm run test:taobao-extension --workspace @x2n/extension
.venv/bin/python -B scripts/verify_skeleton_008.py --verify-worktree --allow-external-main-dirty --skip-external --require-evidence
.venv/bin/python -B scripts/verify_skeleton_009.py --verify-worktree --allow-external-main-dirty --lane-report build/s02-skeleton009-final3/software-lane.json --write-evidence
.venv/bin/python -B scripts/verify_skeleton_009.py --verify-worktree --allow-external-main-dirty --skip-external --lane-report build/s02-skeleton009-final3/software-lane.json --require-evidence
.venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'
```

Final full-lane validation runs twice in a fresh isolated runtime. Any skip outside the existing three Owner-private optional inputs per repetition, any real network/account/OAuth/TOP/MTop execution, any Cookie or signature material, any query/fragment persistence, any sensitive/CDN/runtime artifact, or any flaky/failed blocking Gate fails the Run.

## Risk, rollback and stop conditions

- Risk: item route or DOM assumptions drift; paid API eligibility/price, application scope or retention obligations change; an undocumented browser-signature surface is introduced accidentally.
- Rollback: set `taobao_current_page=false`, remove the adapter dispatch and keep only registered synthetic fixtures/evidence.
- Stop: a real route requires Cookie/session extraction, MTop reverse engineering, an undocumented endpoint, crawler behavior, automatic scrolling/pagination, paid capability without approval, retention without deletion/revocation or any access-control bypass.
