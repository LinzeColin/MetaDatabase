# Run Contract — Stage 3 Adapters009

## Identity

- Task: `TSK.x2n.adapters.009`
- Run: `RUN-X2N-S03-A009`
- Phase: `PH.X2N.3.8`
- Branch: `codex/xhs-douyin-2notion-v0001-s03-adapters009`
- Fixed predecessor: `a0f4a34675d4b2b8b02c9195976a787d2fbf9c59`
- Parent / child: `LinzeColin/MetaDatabase` / `xhs-douyin-2notion`
- Result class: `PASS_CI_SYNTH_SCOPED`; G3 and remote upload remain `NOT_RUN`.

## One-Task Scope

This Run implements only a bounded Taobao Owner-selection contract:

1. the Owner supplies an explicit local manifest of at most 20 `num_iid` values;
2. a future independently authorized transport may hydrate each ID only through the documented `taobao.item.get` capability;
3. this Run accepts only the minimal sanitized item shape `num_iid + title`;
4. canonical identity URL is derived as `https://item.taobao.com/item.htm` without query or fragment;
5. SQLite writes `saved_current`, confirmed by `owner`, because the local selection does not prove a Taobao favorite or like;
6. one durable checkpoint, exact replay, difference evidence, 50 process-kill recovery, a retention receipt, and non-executing 20-item Canary tooling are included.

The Run does not enter `TSK.x2n.adapters.005`, Stage 3 Review, G3, upload, real Owner Profile, a real account, a real API, Notion, model, media, or release execution.

## Official Evidence Decision

First-party Alibaba pages reviewed on 2026-07-23 establish that:

- `taobao.item.get` is documented, requires authorization, is a value-added API, takes `num_iid`, and supports an explicit `fields` request;
- platform rules prohibit obtaining platform data through unauthorized crawling methods;
- processing must stay necessary and inside authorization scope;
- authorization must be traceable;
- disclosure, retention expiry, withdrawal, user deletion, service-end deletion, and cooperation-end deletion controls are required;
- user information storage or transfer requires encryption or de-identification.

The reviewed current first-party navigation did not establish a supported buyer personal-favorites-list endpoint for this product. This is an `UNKNOWN_DISABLED` finding, not a claim that such an endpoint does not exist. Therefore the supported shape is Owner-explicit item IDs plus `taobao.item.get`, not automatic favorites enumeration.

Evidence URLs are versioned in `machine/policy/taobao_selected_collection_policy.json`. No credential, Cookie, session, signing value, account data, raw response, or platform media URL was collected for research or fixtures.

## Capability and Retention Gates

Real execution requires all of the following to be independently attested in a later authorized Run:

- approved Taobao application;
- active Owner OAuth and minimum `taobao.item.get` field scope;
- approved value-added API plan, current pricing and quota snapshot, and nonzero Owner budget;
- official TOP transport and a separate sanitized-contract boundary;
- local-only storage and canonical route attestation;
- approved purpose/scope disclosure and retention period;
- working delete/revoke flow and deletion receipt;
- current policy review, private gold manifest, visible stop control, and Owner Canary authorization.

Budget zero, unknown price/quota, missing retention controls, missing authorization, revocation, feature disabled, or any unknown gate permits zero platform requests. OAuth revocation yields a cleanup-required receipt. This Run does not implement the cleanup executor or delete historical canonical knowledge.

## Transport and Input Denylist

There is no network client, OAuth client, official SDK client, browser iterator, proxy, retry loop, or signing implementation in this Run. Exact schemas reject unknown fields, including:

- Cookie, session, access token, application secret;
- `sign`, `sign_method`, `_m_h5_tk`, `_m_h5_tk_enc`, `h5st`, `x-sign`, `x-mini-wua`, `x-sgext`, `x-umt`;
- undocumented `api` or `data` transport inputs;
- cursor or next-page tokens;
- raw `detail_url`, pictures, video, price, seller, description, SKU, or other commerce fields.

HTTP 429 requires a valid bounded `Retry-After`. The checkpoint remains active with zero canonical writes. There is no automatic retry or proxy rotation; a later explicit Owner action may resume only after the hold.

## Acceptance

### `ACC.x2n.tb.001`

- 20/20 synthetic Owner-selected item IDs identified;
- 20 `Content`, 20 Owner-confirmed `saved_current`, and 20 `SourceObservation` rows;
- fake `liked` or `favorited` relations: 0;
- persisted fields outside the sanitized minimum contract: 0;
- classification and taxonomy writes: 0;
- Owner Canary and real transport: `NOT_RUN`.

### `ACC.x2n.tb.002`

- Cookie/signing reverse engineering and undocumented endpoint usage: 0;
- account-state changes, automatic scrolling, pagination, retry, or proxy rotation: 0;
- 50 abrupt child-process exits recover from the durable checkpoint with lost IDs 0 and duplicate side effects 0;
- auth, OAuth revocation, budget, retention, and policy kills are scoped to the Taobao scan;
- early resume before `Retry-After=120` is blocked.

### `ACC.x2n.batch.001`

- nine non-authoritative outcomes write no removals or tombstones;
- historical relation deletion, physical content deletion, and content auto-deletion: 0;
- full-source-list completion remains false;
- two-successful-scan reconciliation remains downstream in `TSK.x2n.adapters.005`.

## Verification

```bash
.venv/bin/python -B scripts/run_adapters_009_acceptance.py
.venv/bin/python -B -m unittest apps.companion.tests.test_taobao_selected tests.test_adapters_009 -v
.venv/bin/python -B scripts/verify_adapters_009.py --verify-worktree --allow-external-main-dirty
.venv/bin/python -B scripts/ci/run_lane.py --lane full --repetitions 2 --reports-dir build/s03-adapters009-final
.venv/bin/python -B scripts/verify_adapters_009.py --verify-worktree --allow-external-main-dirty --skip-external --lane-report build/s03-adapters009-final/software-lane.json --write-evidence
.venv/bin/python -B scripts/verify_adapters_009.py --verify-worktree --allow-external-main-dirty --skip-external --lane-report build/s03-adapters009-final/software-lane.json --require-evidence
```

Every acceptance command runs with public synthetic fixtures only. The expected external counters are: platform calls 0, network calls 0, real accounts 0, model calls 0.

## Stop and Rollback

Fail closed if an implementation requires unofficial MTop Cookie signing, undocumented endpoints, excess retention, unapproved cost/scope, credential persistence, raw responses, platform media CDN persistence, automatic browsing, or an account-state change.

Rollback is to disable `taobao_selected_collection` and retain the separately gated current-page fallback and canonical data. No schema migration or physical delete is part of this Run.
