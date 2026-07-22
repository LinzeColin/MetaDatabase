# Run Contract — `RUN-X2N-S02-S004`

## Identity

- Task: `TSK.x2n.skeleton.004`
- Phase: `PH.X2N.2.8`
- Stage: `STG.X2N.2`
- Task base: `d5f61f30657ac6aa1bc7be3f7942d4b77df5b8ae`
- Branch: `codex/xhs-douyin-2notion-v0001-s02-skeleton004`
- Run kind: one DAG Task only

## Objective and bounded scope

Move the six already-sanitized `capture_current` inputs through one durable Canonical Store walking path: request ledger, running Run, SourceObservation, Content, Owner-confirmed `saved_current` Relation, resume checkpoint, URL-free artifact placeholder, completed Run and reproducible redacted evidence receipt.

The Run may change the Companion orchestration/Store/Native Host path, synthetic six-platform fixtures, state/duplicate/kill/provenance tests, current-page completion messaging, verifier, machine facts and compact evidence. It must not enter `TSK.x2n.skeleton.005`, list/favorites adapters, classification, Markdown/Notion projection, real platform or media network calls, Owner Chrome/Profile, real accounts, credentials, cookies, automatic scrolling, account-state mutation, ASR/OCR/key-frame/FFmpeg execution, Stage review or remote upload.

## Durable state and privacy decisions

- Keep SQLite Schema v2. No migration is needed: the existing `request_ledger`, `run_record`, `checkpoint`, `content`, `user_relation`, `source_observation` and `artifact` tables already express every scoped durable boundary.
- Transaction 1 atomically creates or replays the request identity, running Run, canonical entities, append-only observation and `canonical_committed` checkpoint. A kill inside it leaves no partial row.
- Transaction 2 appends or reuses a deterministic `search_text` placeholder with no private payload, then marks the checkpoint complete and Run succeeded in the same transaction. A kill before/inside it leaves Transaction 1 replayable; a kill after it returns the existing completed Job.
- The external Native Job remains a UUID. Its deterministic internal Run uses a contract-safe opaque reference and is linked by the request ledger plus deterministic identity; recovery never needs the original request payload.
- The per-platform account reference is a deterministic local Owner-library namespace hash, not a platform account, device fingerprint, credential or browser-state value.
- Persist only the canonical query/fragment-free page URL and sanitized page facts already admitted by the strict Contract. Persist no media URL, raw DOM, credential, Cookie, browser state, raw media, arbitrary path or caller-supplied category.
- Receipts expose counts, states, hashes and downstream status only. Classification, renderer, Markdown, Notion and real media processing are explicitly `DOWNSTREAM_NOT_RUN`.

## Acceptance

- `ACC.x2n.data.001`: `PASS_CI_SYNTH_SCOPED` for Schema v2 FK/Unique/append-only integrity across Run, Content, Relation, Observation, Checkpoint and placeholder Artifact.
- `ACC.x2n.data.002`: `PASS_CI_SYNTH_SCOPED` for 80 deterministic inputs replayed twice and 100 concurrent copies of one request, with no duplicate scoped entities or side effects. Markdown and Notion are `DOWNSTREAM_NOT_RUN`.
- `ACC.x2n.data.003`: `PASS_CI_SYNTH_SCOPED` for the canonical provenance segment from completed Run to Observation/Adapter, Content, Relation and placeholder Artifact. Classification, renderer and sinks are `DOWNSTREAM_NOT_RUN`.
- `ACC.x2n.ops.001`: `PASS_CI_SYNTH_SCOPED` for kill-before-transaction, kill-inside-transaction, kill-after-canonical and kill-after-completion replay. Media processing, classification and sink kill points are owned downstream and remain `DOWNSTREAM_NOT_RUN`.

Real accounts, Owner Runtime/Chrome, platform calls, media processors, Markdown, Notion and Stage 2 Gate remain `NOT_RUN`. The only permitted Task status is a scoped CI-synthetic pass.

## Verification commands

```bash
.venv/bin/python -B scripts/run_skeleton_004_acceptance.py
.venv/bin/python -B scripts/verify_skeleton_004.py --verify-worktree --allow-external-main-dirty --skip-external --write-evidence
.venv/bin/python -B scripts/verify_skeleton_004.py --verify-worktree --allow-external-main-dirty --skip-external --require-evidence
.venv/bin/python -B -m unittest discover -s apps/companion/tests -p 'test_*.py'
.venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'
```

The final software lane must also run dependency audit, release-artifact verification and historical Stage 0–2 verifiers twice. Any duplicate durable entity, non-replayable state, receipt without a SQLite backing row, sensitive/CDN/runtime value in repository evidence, undeclared skip, flaky Blocking Gate or downstream-scope completion claim fails the Run.

## Risk, rollback and stop conditions

- Risk: Job and internal Run identity diverge; a kill leaves canonical rows without a resumable checkpoint; replay updates immutable evidence; concurrent duplicates create more than one entity; a placeholder is mistaken for processed knowledge.
- Rollback: disable `capture_current` execution and retain the prior queued skeleton path. No database restore or migration rollback is required because Schema v2 is unchanged and the new rows are valid canonical append/upsert history.
- Stop: any state cannot replay idempotently, recovery needs the original payload, a persistent layer needs a media URL/credential/raw media, a category must be created, or implementation requires entering Skeleton005 or another Task.
