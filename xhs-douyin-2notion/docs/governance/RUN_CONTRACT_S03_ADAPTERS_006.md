# Run Contract — `RUN-X2N-S03-A006`

## Identity and authorization

- Task: `TSK.x2n.adapters.006`
- Phase: `PH.X2N.3.5`
- Stage: `STG.X2N.3`
- Task base: `37ec58cb51d5720bdbe16a67a6e4ea82107c3eb0`
- Branch: `codex/xhs-douyin-2notion-v0001-s03-adapters006`
- Run kind: one DAG Task only

The Task base is the local final commit of `TSK.x2n.adapters.004`. This Run
first pins that predecessor verifier to its final commit and reads historical
facts from Git blobs. It uses a dedicated worktree and does not absorb `main`,
other projects or other x2n worktrees. `TSK.x2n.adapters.005/.007`, the Stage 3
Review, `G3` and remote upload are outside this Run.

## Official capability conclusion

Current Bilibili first-party documents establish an Open Platform application
and OAuth model, associated-uploader authorization, and an `ARC_BASE` endpoint
for querying the authorized user's own video-manuscript list. The developer
agreement also forbids robot, spider, crawler, automatic program or script access
without Bilibili written consent. The reviewed documents do not establish an
arbitrary personal favorites/likes list or article selected-list capability.
That is a bounded finding as of 2026-07-23, not a claim of nonexistence.

Therefore this Task implements exactly one source contract:
`authorized_uploader_video_manuscripts`. Production remains disabled because x2n
does not have an approved Bilibili application, associated-uploader Owner grant,
`ARC_BASE` grant, written automation permission, attested sanitized transport,
revocation/delete route or Owner Canary. A DOM/crawler fallback is not permitted.

## Objective and bounded scope

1. Add a credential-free capability receipt. CI synthetic mapping is allowed,
   but platform requests remain zero. Owner Runtime is blocked for every missing
   prerequisite and remains blocked by the production Feature Flag even when a
   fully eligible synthetic capability receipt is constructed.
2. Add `BilibiliSelectedIterator`, which accepts one strict sanitized page only:
   page number `1`, page size `20`, one explicit Owner action, no page token,
   automatic pagination/scroll/retry or transport. `has_more` never causes a
   second request and never becomes a full-source-list completion claim.
3. Reject unknown/missing fields recursively at the item/capability/manifest
   boundaries. Raw Open API fields such as cover, filename, share/iframe address,
   CID, media address, credentials and token material are never accepted or
   persisted. Canonical Bilibili video page addresses are derived locally from
   a validated BVID.
4. Atomically map an exact Owner-selected manifest of 1–20 video manuscripts to
   SQLite Content, Owner-confirmed `saved_current` UserRelation,
   `selected_collection` SourceObservation and a versioned durable Checkpoint.
   `source_collection_id` is a local x2n Owner-selection identity, not a Bilibili
   collection. This Task never claims the items were liked or favorited on
   Bilibili.
5. Treat ready as completion of only the selected local Manifest. `full_scan_id`
   remains null and `source_list_complete=false`. Partial/empty/platform-changed
   input produces difference evidence but no Canonical writes or completion.
   Auth, Policy and CAPTCHA invalidate only that Bilibili scan. No failure removes
   or downgrades historical relations.
6. Provide deterministic 20-item Canary planning without execution and a public
   synthetic acceptance covering strict policy/schema failures, 20-item exact
   mapping, exact replay, six blocked states and 50 abrupt process kills.

This Run may change the Bilibili Companion Adapter, non-executing CLI plan,
public synthetic fixture/policy, A004/A006 verifier, evidence and required project
state/docs. It must not add a production network client, browser list extractor,
Chrome permission, Native Messaging action, API secret, Cookie/Profile read,
real request/account/media/Notion/model execution, automatic pagination/scroll,
account-state mutation, full-list/deletion claim, Classification/Taxonomy write,
physical delete, another DAG Task or remote upload.

## Acceptance

- `ACC.x2n.bili.001`: a 20-item public synthetic private-manifest analogue maps
  exactly 20/20 identified items (`100%`, threshold `>=95%`), 20 Content,
  20 Owner-confirmed `saved_current` Relations and 20 Observations. Silent loss,
  fake liked/favorited relations, raw API responses, media/credential persistence,
  removed/tombstone/physical/Content delete and taxonomy writes are all `0`.
  Owner Canary/private Manifest is `NOT_RUN`, so this is
  `PASS_CI_SYNTH_SCOPED`, not real-list acceptance.
- `ACC.x2n.bili.002`: 50 deterministic random abrupt process exits across all
  item/checkpoint transaction points leave durable checkpoint advances, lost IDs
  and duplicate side effects at `0`; recovery then commits once and exact replay
  adds no side effect. Auth, Policy and CAPTCHA each invalidate one Bilibili scan;
  automatic pagination/scroll and platform calls remain `0`.
- `ACC.x2n.batch.001`: auth, Policy/CAPTCHA, empty, partial and platform-change
  outcomes remove `0` historical relations. This Task creates no
  `tombstone_candidate`, physical delete or Content delete. Two-complete-scan
  reconciliation remains owned by `TSK.x2n.adapters.005`.

## Verification commands

```bash
PYTHONPATH=apps/companion/src:packages/contracts/src \
  .venv/bin/python -B scripts/run_adapters_006_acceptance.py
.venv/bin/python -B scripts/verify_adapters_006.py \
  --verify-worktree --allow-external-main-dirty
.venv/bin/python -B scripts/ci/run_lane.py --lane full --repetitions 2 \
  --reports-dir build/s03-adapters006-final
.venv/bin/python -B scripts/verify_adapters_006.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/s03-adapters006-final/software-lane.json --write-evidence
.venv/bin/python -B scripts/verify_adapters_006.py \
  --verify-worktree --allow-external-main-dirty --skip-external \
  --lane-report build/s03-adapters006-final/software-lane.json --require-evidence
```

Any real platform/API/DOM request, unsupported personal-list mapping, missing or
stale scope/policy receipt, implicit pagination, unknown Schema acceptance,
credential/raw-response/media-address persistence, false like/favorite/full-list
claim, silent loss, checkpoint advance across kill, duplicate side effect,
historical relation mutation/deletion, private Runtime material in public output,
task overlap or premature upload fails this Run closed.

## Risk, rollback and stop conditions

- Risk: personal-list scope mismatch, authorization revocation, API/schema drift,
  raw response leakage, false completion and accidental crawler behavior.
- Rollback: disable `bilibili_selected_collection`, revert this local Task commit,
  retain the existing current-page fallback and preserve all Canonical history.
- Stop: written/official authorization cannot support the selected source, the
  required source would need crawling/bypass/automatic pagination, sanitization
  cannot exclude raw/media/credential material, or completion would require a
  real account, another DAG Task, Stage Gate or upload.
