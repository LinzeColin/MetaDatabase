# Run Contract — `RUN-X2N-S03-A007`

## Identity and authorization

- Task: `TSK.x2n.adapters.007`
- Phase: `PH.X2N.3.6`
- Stage: `STG.X2N.3`
- Task base: `5b6564d289ab3d188015265faf55cceb13fd577a`
- Branch: `codex/xhs-douyin-2notion-v0001-s03-adapters007`
- Run kind: one DAG Task only

The Task base is the local final commit of `TSK.x2n.adapters.006`. This Run
pins that predecessor verifier to its final commit and reads predecessor facts
from Git blobs. It uses a dedicated MetaDatabase worktree and does not absorb
`main`, other projects or other x2n worktrees. `TSK.x2n.adapters.005/.008/.009`,
the Stage 3 Review, `G3` and remote upload are outside this Run.

## Official capability conclusion

Kuaishou first-party Open Platform documentation establishes an OAuth 2.0
authorization-code flow and `GET /openapi/photo/list` / `queryVideoList`
under scope `user_video_info` for the OAuth-authorized user's own published
videos. The API defaults to 20 results and exposes a cursor, but this Task does
not accept the cursor or make a second request. The reviewed documents do not
establish an arbitrary personal favorites or likes list. That is a bounded
finding as of 2026-07-23, not a claim that such capability cannot exist.

Kuaishou's first-party application rules require application approval,
minimum-necessary scope, clear disclosure and dynamic user consent. Its platform
protocol restricts unauthorized automated collection and requires authorized
data deletion after consent withdrawal, service termination or a platform/user
request. Therefore this Task implements only a sanitized
`authorized_user_published_videos` contract. It does not implement OAuth,
network transport or deletion execution. Production remains disabled until the
application, consent, scope, sanitized transport, canonical public route,
retention/delete route, policy recheck and Owner Canary are independently
attested. The public `/short-video/{photo_id}` route remains a CI-only
synthetic assumption.

## Objective and bounded scope

1. Add a credential-free capability receipt. CI synthetic mapping is allowed
   with zero requests. Owner Runtime fails closed for a missing application,
   consent, `user_video_info`, sanitized transport, canonical route or
   retention/delete route, and remains blocked by the production Feature Flag
   even when all prerequisite booleans are synthetically asserted.
2. Model consent withdrawal explicitly. A revoked receipt permits zero new
   requests and requires a retention/delete action. It cannot be combined with
   active consent.
3. Add `KuaishouSelectedIterator`, which accepts one strict sanitized page
   only: page 1, size 20, one explicit Owner action, no cursor, automatic
   pagination/scroll/retry or transport. `has_more` never causes a request and
   never becomes a full-source-list completion claim.
4. Reject unknown/missing fields recursively at the capability, manifest and
   item boundaries. Raw Open API fields such as cover/play address, metrics,
   pending state, cursor, credential, token and app secret are never accepted or
   persisted. CI accepts only visibly synthetic photo identities.
5. Atomically map an exact Owner-selected manifest of 1–20 videos to SQLite
   Content, Owner-confirmed `saved_current` UserRelation,
   `selected_collection` SourceObservation and a versioned durable Checkpoint.
   The local selection identity is not a Kuaishou collection, like or favorite.
6. Complete only the selected local manifest. `full_scan_id` remains null and
   `source_list_complete=false`. Partial/empty/platform-change input produces
   evidence but no Canonical writes. Auth, revoked scope, Policy and CAPTCHA
   invalidate only the affected scan. Revocation adds a delete-required marker
   while preserving historical rows until an authorized deletion route exists.
7. Provide a deterministic 20-item non-executing Canary plan and public
   synthetic acceptance covering exact mapping/replay, seven blocked states,
   consent withdrawal and 50 abrupt process kills.

This Run may change the Kuaishou selected-collection Companion Adapter,
non-executing CLI plan, public synthetic fixture/policy, A006/A007 verifier,
evidence and required project state/docs. It must not add a production network
client, browser list extractor, Chrome permission, Native Messaging action,
OAuth endpoint, API secret, Cookie/Profile read, real request/account/media/
Notion/model execution, automatic pagination/scroll, account-state mutation,
full-list/deletion-complete claim, Classification/Taxonomy write, physical
delete, another DAG Task or remote upload.

## Acceptance

- `ACC.x2n.ks.001`: a public 20-item synthetic private-manifest analogue maps
  exactly 20/20 identified items (`100%`, threshold `>=95%`), 20 Content,
  20 Owner-confirmed `saved_current` Relations and 20 Observations. Silent
  loss, fake liked/favorited relations, raw API responses, platform/network
  requests, media/credential persistence, removed/tombstone/physical/Content
  delete and taxonomy writes are all `0`. Owner Canary is `NOT_RUN`; the result
  is `PASS_CI_SYNTH_SCOPED`, not a real-list acceptance.
- `ACC.x2n.ks.002`: 50 deterministic abrupt process exits across item and
  checkpoint transaction points leave checkpoint advances, lost IDs and
  duplicate side effects at `0`; recovery commits exactly once and replay is
  idempotent. Scope withdrawal causes zero new requests, invalidates only that
  scan and emits exactly one delete-required receipt.
- `ACC.x2n.batch.001`: auth, revoked scope, Policy/CAPTCHA, empty, partial and
  platform-change outcomes remove zero historical relations. This Task creates
  no `tombstone_candidate`, physical delete or Content delete. Two-complete-
  scan reconciliation remains owned by `TSK.x2n.adapters.005`.

## Verification commands

```bash
PYTHONPATH=apps/companion/src:packages/contracts/src \
  .venv/bin/python -B scripts/run_adapters_007_acceptance.py
.venv/bin/python -B scripts/verify_adapters_007.py \
  --verify-worktree --allow-external-main-dirty
.venv/bin/python -B scripts/ci/run_lane.py --lane full --repetitions 2 \
  --reports-dir build/s03-adapters007-final
.venv/bin/python -B scripts/verify_adapters_007.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/s03-adapters007-final/software-lane.json --write-evidence
.venv/bin/python -B scripts/verify_adapters_007.py \
  --verify-worktree --allow-external-main-dirty --skip-external \
  --lane-report build/s03-adapters007-final/software-lane.json --require-evidence
```

Any real platform/API/DOM request, unsupported personal-list mapping, missing or
stale scope/consent/policy receipt, request after revocation, implicit
pagination, unknown schema acceptance, credential/raw-response/media-address
persistence, false like/favorite/full-list/deletion-complete claim, silent loss,
checkpoint advance across a kill, duplicate side effect, unauthorized historical
mutation/deletion, private Runtime material in public output, Task overlap or
premature upload fails this Run closed.

## Risk, rollback and stop conditions

- Risk: capability/scope mismatch, consent withdrawal, API/schema drift,
  unverified canonical route, incomplete deletion handling, raw response leakage
  and false completion.
- Rollback: disable `kuaishou_selected_collection`, revert this local Task
  commit, retain the existing current-page fallback and preserve Canonical
  history plus any outstanding delete-required marker.
- Stop: official authorization cannot support this source; collection would
  require crawling, bypass or automatic pagination; sanitization cannot exclude
  raw/media/credential material; revocation cannot stop new requests; or
  completion would require a real account, another Task, Stage Gate or upload.
