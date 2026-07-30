# Run Contract — `RUN-X2N-S03-A008`

## Identity and authorization

- Task: `TSK.x2n.adapters.008`
- Phase: `PH.X2N.3.7`
- Stage: `STG.X2N.3`
- Task base: `a088ea8787acf5b4b2f358317135b089054f1160`
- Branch: `codex/xhs-douyin-2notion-v0001-s03-adapters008`
- Run kind: one DAG Task only

The Task base is the local final commit of `TSK.x2n.adapters.007`. This Run
pins that predecessor verifier and reads its facts from fixed Git blobs. It
uses a dedicated MetaDatabase worktree and does not absorb `main`, other
projects or other x2n worktrees. `TSK.x2n.adapters.005/.009`, Stage 3 Review,
`G3` and remote upload are outside this Run.

## Official capability and cost conclusion

Weibo's first-party Open Platform documentation currently exposes
`GET /2/favorites.json` for the current logged-in user's favorites. The page
documents OAuth `access_token`, application interface permission, page/count
parameters, ordinary-interface frequency limits and a default count of 50.
This contract deliberately selects only page 1 and 20 sanitized items. It does
not infer likes, accept a cursor or claim full-list completion.

The endpoint page is legacy documentation even though it remains reachable.
The current x2n application entitlement, public canonical route, price, plan
and quota have not been independently attested or approved. The Owner-approved
budget is zero. First-party guidance also limits user/IP frequency, rejects
non-user-triggered robot collection and restricts third-party server storage of
user data. Therefore production requests stay disabled and storage is local
SQLite only. A fresh application-scoped authorization, price/quota probe and
Owner approval are mandatory before any real Canary.

## Objective and bounded scope

1. Add a credential-free App/OAuth/cost/quota capability receipt. CI synthetic
   mapping makes zero requests; Owner Runtime blocks on zero budget, unknown
   price/quota, exhausted quota, excessive projected cost, missing approval or
   authorization, revoked authorization, unattested local-only storage or
   canonical route, and finally the disabled production flag.
2. Add `WeiboSelectedIterator`, accepting one strict sanitized page: explicit
   Owner action, page 1, size 20, no cursor, automatic pagination, scroll,
   retry, proxy rotation, arbitrary URL transport or account-state mutation.
3. Reject unknown/missing fields recursively. Raw response fields, image/video
   addresses, user objects, counters, credentials and cursors are neither
   accepted nor persisted; CI accepts only visibly synthetic status IDs.
4. Atomically map 1–20 official-favorites observations to SQLite Content,
   scan-confirmed `favorited` UserRelation, `selected_collection`
   SourceObservation and a durable versioned Checkpoint. The local Owner
   selection ID is checkpoint identity only and never a platform collection.
5. Keep `source_collection_id` and `full_scan_id` null. Never infer `liked` or
   `saved_current`, remove a historical relation, create a tombstone, classify
   content, mutate taxonomy or physically delete content.
6. Handle HTTP 429 only as an injected sanitized contract: require canonical
   `Retry-After` delay/date, persist a bounded hold without advancing the item
   checkpoint or writing Canonical data, issue no automatic request, and permit
   resume only after the hold and a new explicit Owner batch.
7. Provide a deterministic 20-item non-executing Canary plan and public
   synthetic acceptance covering exact mapping/replay, cost gates, eight
   blocked states, RFC `Retry-After` and 50 abrupt process kills.

This Run may change the Weibo selected-collection Companion Adapter,
non-executing CLI plan, public synthetic policy/fixture, A007/A008 verifier,
evidence and required project state/docs. It must not add a production network
or OAuth client, browser list extractor, Chrome permission, Native Messaging
action, secret/Cookie/Profile input, real request/account/media/Notion/model
execution, automatic purchase/plan upgrade/retry/pagination/scroll, proxy
rotation, remote collection server, full-list claim, deletion executor,
another DAG Task or remote upload.

## Acceptance

- `ACC.x2n.wb.001`: a public 20-item synthetic analogue maps exactly 20/20
  identified items (`100%`, threshold `>=95%`), 20 Content, 20 scan-confirmed
  `favorited` Relations and 20 Observations. Fake liked/saved-current relations,
  raw responses, network/platform requests, credentials/media URLs, removed/
  tombstone/delete/taxonomy writes are `0`. Budget remains `0`; price/quota are
  `UNKNOWN_NOT_APPROVED`; Owner Canary is `NOT_RUN`.
  The scoped result is `PASS_CI_SYNTH_SCOPED`, never real-list acceptance.
- `ACC.x2n.wb.002`: 50 deterministic abrupt process exits across item and
  checkpoint points cause zero checkpoint advance, lost ID or duplicate side
  effect. Auth/OAuth/budget/Policy kills affect only that scan. One HTTP 429
  requires `Retry-After=120`, blocks an early resume and makes zero automatic
  retry, proxy rotation, request or Canonical write.
- `ACC.x2n.batch.001`: all eight non-authoritative outcomes remove zero
  historical relations. OAuth revocation emits one authorization-cleanup
  receipt and allows zero new requests. Two-complete-scan reconciliation stays
  owned by `TSK.x2n.adapters.005`.

## Verification commands

```bash
PYTHONPATH=apps/companion/src:packages/contracts/src \
  .venv/bin/python -B scripts/run_adapters_008_acceptance.py
.venv/bin/python -B scripts/verify_adapters_008.py \
  --verify-worktree --allow-external-main-dirty
.venv/bin/python -B scripts/ci/run_lane.py --lane full --repetitions 2 \
  --reports-dir build/s03-adapters008-final
.venv/bin/python -B scripts/verify_adapters_008.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/s03-adapters008-final/software-lane.json --write-evidence
.venv/bin/python -B scripts/verify_adapters_008.py \
  --verify-worktree --allow-external-main-dirty --skip-external \
  --lane-report build/s03-adapters008-final/software-lane.json --require-evidence
```

Any real request, unknown/stale scope or cost receipt, request with zero budget,
automatic purchase/retry/proxy, premature 429 resume, cursor/pagination, raw or
credential/media persistence, false relation/full-list claim, silent loss,
checkpoint advance across a kill, unauthorized historical mutation, private
Runtime material, Task overlap or upload fails this Run closed.

## Risk, rollback and stop conditions

- Risk: legacy capability documentation, current entitlement/price/quota drift,
  route uncertainty, limit response variation, raw-response leakage and false
  list/relation completeness.
- Rollback: disable `weibo_selected_collection`, revert this local Task commit,
  preserve Canonical history and retain the current-page fallback.
- Stop: current price, quota, application permission, OAuth, local-only storage
  or canonical route is unknown/unapproved; cost exceeds the approved budget;
  the source requires crawling/bypass/automatic pagination; or completion needs
  a real account, another Task, Stage Gate or upload.
