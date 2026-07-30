# Run Contract — Stage 3 Adapters010

## Identity

- Task: `TSK.x2n.adapters.010`
- Run: `RUN-X2N-S03-A010`
- Phase: `PH.X2N.3.10`
- Branch: `codex/xhs-douyin-2notion-v0001-s03-review-resume`
- Parent / child: `LinzeColin/MetaDatabase` / `xhs-douyin-2notion`
- Result class: `PASS_CI_SYNTH_SCOPED`; this is not a live-platform activation, Stage 3 upload, Stage 4 start, deployment, Alpha, Beta, or release decision.

## One-Task Scope

This Run closes only the two remaining Stage 3 technical blockers:

1. The exact eight `scope_id` values traverse a strict Side Panel → Extension service worker → Native Host → verified Adapter binding route. A dispatch creates a durable SQLite job and a deterministic zero-platform-call synthetic receipt; it never supplies a browser batch, scrolls, changes an account, retries, or calls a platform.
2. A failed dispatch creates `run_record.state=failed` and exactly one sanitized `run_failure` row. `FALLBACK_AVAILABLE` is derived only when the row is `fallback_eligible=1`; it is not a run state. A second, user-clicked current-page capture uses a new request ID and carries `fallback_from_job_id`; nothing starts it automatically.

The exact scope matrix is:

| Scope | Platform | Relation |
| --- | --- | --- |
| `xiaohongshu_favorites` | `xiaohongshu` | `favorited` |
| `xiaohongshu_likes` | `xiaohongshu` | `liked` |
| `douyin_favorites` | `douyin` | `favorited` |
| `douyin_likes` | `douyin` | `liked` |
| `bilibili_selected_collection` | `bilibili` | `saved_current` |
| `kuaishou_selected_collection` | `kuaishou` | `saved_current` |
| `weibo_selected_collection` | `weibo` | `favorited` |
| `taobao_selected_collection` | `taobao` | `saved_current` |

`START_SYNC` is a discriminated, versioned contract. The three `saved_current` selected-collection scopes require Owner selection ID, manifest SHA-256, source identity, and a bounded `max_items`; the Weibo selected collection is held to the same Owner-evidence requirement. `CAPTURE_CURRENT` remains a separate single-item `saved_current` action.

## Runtime Authority and Gates

- `capability_gate_outcome` is the only restart-safe runtime capability snapshot. Registries are inputs only.
- A valid snapshot contains exactly one row for every scope. A source-digest change atomically replaces the whole snapshot; partial data is never served.
- `BLOCKED_TECHNICAL` is a global veto. It wins before every external reason, deletes affected stale rows, creates no terminal outcome, and returns `X2N_CAPABILITY_TECHNICAL_BLOCKED`.
- When technical is false, precedence is fixed: `UNKNOWN_DISABLED`, `BLOCKED_POLICY`, `BLOCKED_AUTH`, `BLOCKED_BUDGET`, `BLOCKED_CAPABILITY`, then `CI_SYNTH_READY`.
- Only the `ci_synthetic_only` flag may execute the Task010 synthetic route. `READY_FOR_MVP_ACTIVATION` is a technical readiness terminal, never a live-support claim.

## Compatibility, Privacy, and Recovery

- The legacy empty `GET_CAPABILITIES` request and pre-Task010 Native response vector remain readable; the typed capability result is additive and versioned.
- Pydantic, error registry, JSON Schema, generated TypeScript, Extension consumer, migration, and tests change together.
- The migration is reversible through the existing verified SQLite backup/downgrade/restore path.
- No platform media CDN URL, credential, cookie, browser state, raw media, private manifest, local absolute path, or runtime database enters Git or Task evidence.
- Failed `GET_JOB` is rejected with its original `job_id`, `X2N_ADAPTER_FAILED_FALLBACK_AVAILABLE`, and `next_action=capture_current`. Accepted responses never carry an error.

## Acceptance

`ACC.x2n.batch.002`, `ACC.x2n.ext.003`, and `ACC.x2n.batch.001` are satisfied only when all of these hold:

- all eight exact dispatches pass Extension E2E with zero platform calls;
- invalid cross-products, unknown scopes, malformed selection evidence, disabled gates, unknown actions, duplicate-ID conflicts, and non-synthetic activation flags fail closed;
- capability cardinality, precedence, technical-veto invalidation, stale-digest replacement, restart reads, and migration down/restore pass;
- a forced adapter failure is atomic, preserves the job ID across a fresh Store instance, and requires a separate explicit current-page action;
- generated contracts, Python tests, TypeScript check, Extension self-test, and E2E pass;
- automatic fallback, real accounts, real platform calls, model calls, media processing, stage upload, Stage 4, deployment, Alpha, and Beta are all `0` / `NOT_RUN`.

## Verification

```bash
PYTHONPATH=apps/companion/src:packages/contracts/src \
  .venv/bin/python -B scripts/run_adapters_010_acceptance.py
PYTHONPATH=apps/companion/src:packages/contracts/src \
  .venv/bin/python -B scripts/verify_adapters_010.py --verify-worktree
PYTHONPATH=apps/companion/src:packages/contracts/src \
  .venv/bin/python -B -m unittest \
  apps.companion.tests.test_adapter_dispatch \
  packages.contracts.tests.test_adapter_dispatch_contracts \
  tests.test_adapters_010 -v
npm run test:e2e --workspace @x2n/extension
```

After this task passes, the next independent Run is the Stage 3 Review Resume recheck. It alone may decide whether `G3` passes; no upload or Stage 4 work is authorized by this Run itself.
