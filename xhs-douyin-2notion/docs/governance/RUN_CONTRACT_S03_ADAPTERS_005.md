# Run Contract — Stage 3 Adapters005

## Identity

- Task: `TSK.x2n.adapters.005`
- Run: `RUN-X2N-S03-A005`
- Phase: `PH.X2N.3.9`
- Branch: `codex/xhs-douyin-2notion-v0001-s03-adapters005`
- Fixed predecessor: `8c6442a251f73e645e292a4e77dd03448d153b64`
- Parent / child: `LinzeColin/MetaDatabase` / `xhs-douyin-2notion`
- Result class: `PASS_CI_SYNTH_SCOPED`; Owner Alpha is `OWNER_ALPHA_NOT_RUN`; Stage Review, `G3_NOT_RUN`, and remote upload remain not run.

## One-Task Scope

This Run implements only durable relation reconciliation and batch completion receipts:

1. SQLite `run_record` is the exact event ledger and a private SQLite `checkpoint` cursor is the reconciliation truth;
2. scope is the exact tuple of source adapter, platform, hashed account reference, and relation type;
3. the only currently authoritative full-scan sources are completed `xhs_favorites` and `xhs_likes` scans whose Run, checkpoint, receipt, relation set, observation set, count, platform, and active state agree exactly;
4. each accepted source scan must be distinct and its checkpoint time strictly newer than the preceding accepted source scan;
5. the conservative state machine is `active -> unknown -> tombstone_candidate` across two distinct consecutive complete missing scans;
6. observed relations return to `active`; existing `removed` relations are preserved; this component has no path to `removed` and no physical delete statement;
7. auth expiry, HTTP failure, platform change, empty response, and partial scan clear the pending-missing chain without changing any relation;
8. public receipts contain counts and hashed references, never relation keys, account hashes, source IDs, local paths, credentials, media addresses, or private manifests.

This Run does not enter Stage 3 Review, G3, upload, Stage 4, any real Owner Profile or platform account, Notion, models, media processing, or release execution.

## Full-Scan Proof Boundary

`complete_success` is accepted only when all of these conditions hold atomically:

- the adapter is allowlisted for the requested platform and relation type;
- the source checkpoint is `complete`, uses `authoritative_visible_end`, has confidence `1.0`, and names a source full-scan Run;
- the source Run kind matches the adapter, is `succeeded`, and has a completion timestamp;
- the checkpoint ID, full-scan Run ID, and source receipt ID have the expected adapter-specific identity relationship;
- the exact source-receipt relation set equals the submitted immutable relation manifest;
- distinct observed content keys equal both the source checkpoint count and submitted count;
- source relation content keys equal observation content keys and all source relations are active on the requested platform;
- the source is non-empty, distinct from the previous accepted full scan, and strictly newer.

The current Douyin sidecar has no authoritative full-scan receipt. Bilibili, Kuaishou, Weibo, and Taobao adapters are bounded selection/capability contracts. None may claim full-scan completion in this Run.

## State and Recovery Invariants

- first consecutive complete absence: `active -> unknown`;
- second distinct consecutive complete absence: `unknown -> tombstone_candidate`;
- later absence: remain `tombstone_candidate`;
- any non-authoritative outcome: clear pending chain, relation writes 0;
- exact event replay: return `replayed`, preserve the event's source reference, new writes 0;
- same event ID with a different input hash: fail closed;
- same source scan under a different event ID: fail closed;
- missing durable checkpoint for a succeeded reconciliation Run, corrupted private cursor, incomplete provenance, backwards event time, cross-platform scope, or over-limit scope: fail closed;
- process exit before SQLite commit: relation, Run, and checkpoint mutations all roll back.

The rollback is to disable `relation_reconciliation` and retain every Canonical row. The schema is unchanged, so rollback requires no migration and never deletes Content or Relation records.

## Acceptance

### `ACC.x2n.batch.001`

- first complete missing scan creates 10 `unknown`; second distinct complete missing scan creates exactly 10 `tombstone_candidate`;
- auth, HTTP, platform-change, empty, and partial outcomes produce relation writes 0 and removed writes 0;
- relabelling one source full scan as a second scan is blocked;
- 50 abrupt child-process exits must include before reconciliation, observed rows, missing rows, both sides of the checkpoint update, and pre-commit; they yield partial writes 0 and checkpoint advances 0;
- the synthetic `0600` chaos manifest is removed before the acceptance report; residual files are 0. This is not the Owner Alpha private 80-item Manifest, which remains `NOT_CREATED`;
- removed relations 0, physical deletes 0, Content automatic deletes 0.

### `ACC.x2n.data.002`

- the same 80 synthetic Canonical inputs run twice;
- 100 concurrent copies of one reconciliation event all replay safely;
- duplicate Content, Relation, Artifact, Markdown, and Notion Page counts are 0;
- SQLite integrity is `ok` and orphan relations are 0;
- Markdown and Notion mock idempotency already passed their prior scoped acceptance; this reconciliation Run does not execute real Notion.

### `ACC.x2n.rel.006`

- fixed non-executing tooling describes 20 XHS favorites, 20 XHS likes, 20 Douyin favorites, and 20 Douyin likes;
- the public plan contains relation keys 0 and platform calls 0;
- Owner Profile login, private 80-item Manifest, real Canonical/Artifact/Markdown/Notion comparison, and Owner Alpha execution are all `NOT_RUN`;
- therefore this Run claims tooling readiness only and does not declare Alpha PASS.

## Verification

```bash
.venv/bin/python -B scripts/run_adapters_005_acceptance.py
.venv/bin/python -B -m unittest apps.companion.tests.test_relation_reconciliation tests.test_adapters_005 tests.test_adapters_009 -v
.venv/bin/python -B scripts/verify_adapters_005.py --verify-worktree --allow-external-main-dirty
.venv/bin/python -B scripts/ci/run_lane.py --lane full --repetitions 2 --reports-dir build/s03-adapters005-final
.venv/bin/python -B scripts/verify_adapters_005.py --verify-worktree --allow-external-main-dirty --lane-report build/s03-adapters005-final/software-lane.json --write-evidence
.venv/bin/python -B scripts/verify_adapters_005.py --verify-worktree --allow-external-main-dirty --skip-external --lane-report build/s03-adapters005-final/software-lane.json --require-evidence
```

All acceptance inputs are public synthetic fixtures. Expected external counters are platform calls 0, network calls 0, real accounts 0, model calls 0, and media processing 0.

## Stop Conditions

Fail closed if any error/empty/partial outcome can change a relation, if one source scan can count twice, if full-scan completeness cannot be proven, if the state machine can write `removed`, if any physical delete path exists, if process-kill recovery is not atomic, or if a receipt exposes a private identity or path.
