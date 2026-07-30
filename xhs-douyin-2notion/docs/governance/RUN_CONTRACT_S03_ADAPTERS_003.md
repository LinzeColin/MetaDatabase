# Run Contract — `RUN-X2N-S03-A003`

## Identity and authorization

- Task: `TSK.x2n.adapters.003`
- Phase: `PH.X2N.3.3`
- Stage: `STG.X2N.3`
- Task base: `050ec0c93ff4b1d6020a5c8e12f79320fc401f53`
- Branch: `codex/xhs-douyin-2notion-v0001-s03-adapters003`
- Run kind: one DAG Task only

The Task base is the local final commit of `TSK.x2n.adapters.002`. This Run reads
that predecessor from its fixed commit and does not absorb unrelated `main` or
other worktree changes. Stage 3 remains local until all Adapter Tasks, independent
Stage Review, fixes, re-acceptance and `G3` complete.

## Objective and bounded scope

Implement the clean-room Xiaohongshu likes path for one Owner-triggered, visible,
bounded batch:

1. an isolated-world extractor that accepts at most 20 visible cards only after an
   explicit action and returns stable IDs, canonical page URLs and sanitized facts;
2. an atomic SQLite Adapter that reuses the platform Content key, persists an
   independent `liked` UserRelation, SourceObservation and versioned Checkpoint;
3. strict successor sequencing, exact-last-batch replay, partial/error evidence,
   bounded-scope versus full-scan separation and authoritative-end completion;
4. a conservative Inbox policy: new low-intent likes remain `unclassified`, create
   no Classification or Taxonomy row, and never overwrite an existing Owner decision;
5. a fixed 20-item Canary plan which performs no login, browser or platform action;
6. public synthetic DOM layouts plus 100-item/50-process-kill recovery acceptance,
   including 20 items already carrying `favorited` Relations.

This Run may change the Xiaohongshu likes Extension/Companion modules, CLI
non-executing Canary plan, public synthetic fixtures, Task policy, verifier,
evidence and required project-state documentation. It must not enter
`TSK.x2n.adapters.004`, wire a production Side Panel action, alter Native Messaging
v1, add host permission/static content scripts, call an endpoint, read Cookie or
Profile data, automate scrolling/pagination/login/verification, execute like/unlike,
change account state, auto-file or create taxonomy, process/download media, call
Notion/models, run an Owner Profile or real Canary, reconcile missing relations,
delete data, upload GitHub, or contact shared authentication material.

## Evidence-backed policy boundary

The official privacy material reviewed on 2026-07-23 documents an interactive
Owner path for `我-笔记/收藏/赞过`. Reviewed official Open Platform and Mini Program
materials expose merchant/application authorization surfaces but did not expose a
personal-likes read API. This is a scoped research result, not a claim that no such
API can exist. Therefore `xhs_likes` remains production-disabled; the implemented
path consumes only sanitized visible DOM facts under temporary `activeTab`, with no
network request or private endpoint/signature work.

An empty page without an authoritative visible end is `empty_unverified`. Partial,
expired-login, verification and platform-change results preserve identified facts
and error evidence where applicable, but never advance the batch, complete a scan,
remove a relation or delete Content. A 20-item Canary completes only bounded scope;
it is never a full scan. Full scan completion requires an authoritative visible end.

## Acceptance

- `ACC.x2n.xhs.002`: public CI fixtures identify every controlled visible card or
  emit stable per-card evidence; every item creates `liked`, remains conservative
  Inbox/unclassified, and creates Classification/Taxonomy mutations `0`. Required
  ENV-OWNER-ALPHA 20-item/private-gold execution is `NOT_RUN`, so completion is only
  `PASS_CI_SYNTH_SCOPED`.
- `ACC.x2n.xhs.003`: 100 deterministic likes are applied in five Owner-bounded
  actions. Ten real subprocess exits per action, 50 total, occur inside random
  transaction points. Reopen resumes from SQLite Checkpoint; lost IDs, duplicate
  side effects, infinite loops and automatic scrolls are `0`.
- Duplicate identity: 20 of the 100 likes are pre-existing favorited Content. Final
  Content rows remain exactly 100 while 100 `liked` and 20 `favorited` Relations
  coexist; neither signal overwrites the other.
- `ACC.x2n.batch.001`: auth, verification, platform-change, unverified empty and
  partial results create removed relations `0`; this Task creates neither
  `tombstone_candidate` nor physical/Content deletion. Cross-scan reconciliation
  remains owned by `TSK.x2n.adapters.005`.

Owner Profile login, real page, real account, platform calls and Canary are
`NOT_RUN`; `G3=NOT_RUN` and remote upload remains forbidden.

## Verification commands

```bash
.venv/bin/python -B scripts/run_adapters_003_acceptance.py
.venv/bin/python -B scripts/verify_adapters_003.py \
  --verify-worktree --allow-external-main-dirty
.venv/bin/python -B scripts/ci/run_lane.py --lane full --repetitions 2 \
  --reports-dir build/s03-adapters003-final
.venv/bin/python -B scripts/verify_adapters_003.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/s03-adapters003-final/software-lane.json --write-evidence
.venv/bin/python -B scripts/verify_adapters_003.py \
  --verify-worktree --allow-external-main-dirty --skip-external \
  --lane-report build/s03-adapters003-final/software-lane.json --require-evidence
```

Any real external call, automatic scroll, account mutation, unknown completion
promoted to full scan, silent card loss, Content duplication, relation overwrite,
replay mismatch, kill-induced loss/duplicate, automatic filing/taxonomy mutation,
removed/deleted record, Owner execution claim, private Runtime or media address in
public output, task overlap or premature upload fails this Run.

## Risk, rollback and stop conditions

- Risk: DOM drift, login/verification mistaken for empty, duplicate responsive
  cards, likes volume instability, cursor incompatibility and low-intent auto-filing.
- Rollback: keep `xhs_likes` disabled, revert this local Task commit and retain
  accepted current-page/favorites capture plus all pre-existing Canonical data.
- Stop: two real adaptation iterations remain below 90% identification; any route
  needs verification bypass, credential/browser-state access, undocumented endpoint,
  automatic scrolling/account mutation/unlike, unresolved silent loss/deletion or
  classification ambiguity, another DAG Task, Owner execution without authorization,
  or remote upload.
