# Run Contract — Stage 2 Skeleton005

## Identity

- Task: `TSK.x2n.skeleton.005`
- Run: `RUN-X2N-S02-S005`
- Phase: `PH.X2N.2.9`
- Base commit: `36bd12133f402321b160292ea13ca51272c63e93`
- Branch: `codex/xhs-douyin-2notion-v0001-s02-skeleton005`
- Repository/project: `LinzeColin/MetaDatabase` / `xhs-douyin-2notion/`

## Goal and minimum scope

Complete the first recoverable derived projection from Schema v2 Canonical facts without making either sink a source of truth:

1. Render deterministic Canonical Markdown at `runtime/library/content/<platform>/<content_id>.md` and write it with same-directory atomic replace, file/directory fsync and owner-only permissions.
2. Seed the generated `runtime/library/categories/unclassified/INDEX.md` fallback without creating a taxonomy row or allowing AI to create a level-one category.
3. Define the current Notion `2026-03-11` Data Source/Page minimal Items/Categories projection, additive-only schema reconciliation and content-key upsert semantics.
4. Drive Markdown and an in-process Notion Mock through the existing SQLite Outbox, lease, append-only Sink Receipt and private Notion Mapping tables.
5. Add durable retry/dead-letter scheduling, `Retry-After` handling, two-requests-per-second rate control and success-before-receipt reconciliation.

The Notion Mock is a deterministic transport double, not a network server and not a claim that an Owner Workspace, credential, API capability or real page has been tested.

Official Notion basis rechecked on 2026-07-22:

- API version and Data Source migration: <https://developers.notion.com/guides/get-started/upgrade-guide-2025-09-03>
- Request limits and integer `Retry-After`: <https://developers.notion.com/reference/request-limits>
- 429/529 error semantics: <https://developers.notion.com/reference/status-codes>
- Current Data Source creation limitations, including no view customization in this endpoint: <https://developers.notion.com/reference/create-a-data-source>

## Non-goals

- No real Notion token, Workspace, HTTP request, SDK dependency, page, Data Source, file upload or Owner Canary.
- No platform request, account, list Adapter, short-link transport, media acquisition/processing, model call, classification or user-data import.
- No full 10k Markdown rebuild (`ACC.x2n.md.002`) and no Notion View installation (`ACC.x2n.notion.004`).
- No Schema v2 migration, destructive schema edit, Stage 2 Review, `G2`, push or release claim.
- No title/category-derived Canonical path, media embedding, platform CDN URL, credential, Cookie, browser state, raw media or local absolute path in a public receipt.

## Durable walking path

```text
Schema v2 Canonical snapshot
  -> deterministic Markdown projection hash
  -> Markdown Outbox lease
  -> atomic owner-private file
  -> append-only Markdown Sink Receipt

Schema v2 Canonical snapshot
  -> deterministic Notion projection hash
  -> Notion Outbox lease
  -> rate-limited additive-schema/upsert Mock operation
  -> private notion_mapping
  -> append-only Notion Sink Receipt
```

Notion success before the local mapping/receipt commit is an expected ambiguous state. After the lease expires, reconciliation queries by the stable `content_key`, adopts exactly one existing page, writes the private mapping and completes the original event. Zero or one page is valid; more than one fails closed.

## Acceptance scope

- `ACC.x2n.md.001`: `PASS_CI_SYNTH_SCOPED` for six-platform representative inputs, long transcript/OCR, special characters, stable platform/content-ID paths, valid deterministic frontmatter, atomic replacement, provenance and zero CDN URL.
- `ACC.x2n.notion.001`: `PASS_CI_SYNTH_MOCK_SCOPED` for current Data Source/Page projection shape, additive-only schema changes, one page per `content_key`, category relation shape, unchanged user fields, projection-hash no-op and zero media/CDN URL.
- `ACC.x2n.notion.002`: `PASS_CI_SYNTH_MOCK_SCOPED` for serialized average `<=2 req/s`, 429/529 `Retry-After`, retryable timeout/reset, bounded attempts, Dead Letter and zero retry storm.
- `ACC.x2n.notion.003`: `PASS_CI_SYNTH_MOCK_SCOPED` for one-hour outage scheduling, Canonical/Markdown independence, success-before-receipt kill reconciliation, terminal Receipt/Dead Letter and zero duplicate page.

Real Notion and Owner Canary portions of the Acceptance remain `NOT_RUN`; this Run may not report the full cross-environment Acceptance as globally complete.

## Files and validation

Inspect: Task Pack, Acceptance contract, architecture, Runtime paths, Contracts, Schema v2, Canonical Store, Media Safety scanner and S004 history.

May modify only S005 sink modules/tests, narrowly required Canonical Store Outbox/Mapping primitives, this Run Contract, sink policies/fixtures, Task/machine state, project documentation, verifier and redacted evidence.

Required validation:

```bash
.venv/bin/python -B scripts/run_skeleton_005_acceptance.py
.venv/bin/python -B scripts/verify_skeleton_005.py --verify-worktree --allow-external-main-dirty --skip-external --require-evidence
PYTHONPATH=packages/contracts/src:apps/companion/src .venv/bin/python -B -m unittest discover -s apps/companion/tests -p 'test_*.py'
.venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python -B scripts/ci/run_lane.py --lane full --repetitions 2 --reports-dir build/s02-skeleton005-final
```

## Risks, rollback and stop conditions

- Risks: path traversal or symlink replacement; a partial Markdown file; projection drift; user Notion fields overwritten; duplicate Notion pages; retry storm; ambiguous success without a receipt; private page IDs entering evidence.
- Rollback: disable both sink workers, remove the derived Markdown library and rebuild later. Preserve Canonical rows, Outbox history, private mappings and append-only receipts for audit/reconciliation.
- Stop: any Notion write must share the Canonical transaction; a projection requires a media/CDN URL, credential or arbitrary path; user fields must be removed/changed; a category must be invented; recovery can create duplicate pages; Schema v2 needs a destructive migration; or implementation enters another Task.
