# Run Contract — `RUN-X2N-S03-A002`

## Identity and authorization

- Task: `TSK.x2n.adapters.002`
- Phase: `PH.X2N.3.2`
- Stage: `STG.X2N.3`
- Task base: `ea44053528a6cdec342fff946a35a525e8daf385`
- Branch: `codex/xhs-douyin-2notion-v0001-s03-adapters002`
- Run kind: one DAG Task only

The Task base is the local final commit of `TSK.x2n.adapters.001`. This Run reads
that predecessor from its fixed commit and does not absorb unrelated `main` or
other worktree changes. Stage 3 remains local until all Adapter Tasks, independent
Stage Review, fixes, re-acceptance and `G3` complete.

## Objective and bounded scope

Implement the clean-room Xiaohongshu favorites path for one Owner-triggered,
visible, bounded batch:

1. an isolated-world extractor that accepts at most 20 visible cards only after an
   explicit action and returns stable IDs, canonical page URLs, sanitized facts and
   collection mapping;
2. an atomic SQLite Adapter that persists `Content`, `favorited` `UserRelation`,
   `selected_collection` `SourceObservation` and a durable versioned Checkpoint;
3. strict successor sequencing, exact-last-batch replay, partial/error evidence,
   bounded-scope versus full-scan separation and authoritative-end completion;
4. a fixed 20-item Canary plan which performs no login, browser or platform action;
5. public synthetic DOM layouts plus 100-item/50-process-kill recovery acceptance.

This Run may change the Xiaohongshu favorites Extension/Companion modules, CLI
non-executing Canary plan, public synthetic fixtures, Task policy, verifier,
evidence and required project-state documentation. It must not enter
`TSK.x2n.adapters.003`, wire a production Side Panel action, alter Native Messaging
v1, add host permission/static content scripts, call an endpoint, read Cookie or
Profile data, automate scrolling/pagination/login/verification, change account
state, process/download media, call Notion/models, run an Owner Profile or real
Canary, reconcile missing relations, delete data, upload GitHub, or contact shared
authentication material.

## Evidence-backed policy boundary

Official materials reviewed on 2026-07-23 document user-visible self-management and
merchant/share developer surfaces, but the reviewed sources did not expose an
official personal-favorites read API. This is a scoped research result, not a claim
that no such API can exist. Therefore `xhs_favorites` remains production-disabled;
the implemented path only consumes sanitized visible DOM facts under temporary
`activeTab`, and performs no network request or private endpoint/signature work.

An empty page without an authoritative visible end is `empty_unverified`. Partial,
expired-login, verification and platform-change results preserve identified
observations and error evidence where applicable, but never advance the batch,
complete a scan, remove a relation or delete Content. A 20-item Canary may complete
only its bounded scope; it is never recorded as a full scan. Full scan completion
requires an authoritative visible end and never derives from item count alone.

## Acceptance

- `ACC.x2n.xhs.001`: CI synthetic layouts identify every controlled card or emit a
  stable per-card error, map two synthetic collections, and provide fixed 20-item
  Canary tooling. The required ENV-OWNER-ALPHA manual 20-item/private-gold execution
  is explicitly `NOT_RUN`, so this Run claims only `PASS_CI_SYNTH_SCOPED`.
- `ACC.x2n.xhs.003`: 100 deterministic items are applied in five Owner-bounded
  actions. Ten real subprocess exits per action, 50 total, occur inside random
  transaction points. Reopen resumes from the durable Checkpoint; final ID set is
  exact, lost IDs/duplicate side effects/infinite loops/automatic scrolls are `0`.
- `ACC.x2n.batch.001`: auth, verification, platform-change, unverified empty and
  partial results create removed relations `0`; this Task creates neither
  `tombstone_candidate` nor physical/Content deletion. Cross-scan reconciliation
  remains owned by `TSK.x2n.adapters.005`.

Completion status is only `PASS_CI_SYNTH_SCOPED`. Owner Profile login, real page,
real account, platform calls and Canary are `NOT_RUN`; `G3=NOT_RUN` and remote upload
remains forbidden.

## Verification commands

```bash
.venv/bin/python -B scripts/run_adapters_002_acceptance.py
.venv/bin/python -B scripts/verify_adapters_002.py \
  --verify-worktree --allow-external-main-dirty
.venv/bin/python -B scripts/ci/run_lane.py --lane full --repetitions 2 \
  --reports-dir build/s03-adapters002-final
.venv/bin/python -B scripts/verify_adapters_002.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/s03-adapters002-final/software-lane.json --write-evidence
.venv/bin/python -B scripts/verify_adapters_002.py \
  --verify-worktree --allow-external-main-dirty --skip-external \
  --lane-report build/s03-adapters002-final/software-lane.json --require-evidence
.venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python -B -m unittest discover -s apps/companion/tests -p 'test_*.py'
```

Any real external call, automatic scroll, unknown completion promoted to full scan,
silent card loss, replay mismatch, kill-induced loss/duplicate, collection mapping
without provenance, removed/deleted record, Owner execution claim, private Runtime
or media address in public output, task overlap or premature upload fails this Run.

## Risk, rollback and stop conditions

- Risk: DOM drift, login/verification mistaken for empty, duplicate responsive cards,
  collection label ambiguity, cursor incompatibility and false full-scan completion.
- Rollback: keep `xhs_favorites` disabled, revert this local Task commit and retain
  accepted current-page capture plus all pre-existing Canonical data.
- Stop: two real adaptation iterations remain below 90% identification; any route
  needs verification bypass, credential/browser-state access, undocumented endpoint,
  automatic scrolling/account mutation, unresolved silent loss/deletion ambiguity,
  another DAG Task, Owner execution without authorization or remote upload.
