# RUN-X2N-S02-S002 — Douyin Current Page CI-SYNTH

## 1. Run identity

- Unique DAG Task: `TSK.x2n.skeleton.002`
- Unique Phase: `PH.X2N.2.2`
- Stage: `STG.X2N.2`
- Task base: `894553c6d15c3c73315e54429c8bd26588b6f83a`
- Origin cutoff: `6777c8fcce75a36741b70c2858c8bc5fff17d440`
- Isolated branch: `codex/xhs-douyin-2notion-v0001-s02-skeleton002`
- Acceptance: `ACC.x2n.capture.002`, `ACC.x2n.ext.001`
- Completion class: `PASS_CI_SYNTH_SCOPED`; `G2=NOT_RUN`

## 2. Objective and minimum scope

Implement a clean-room Douyin current-page adapter for public synthetic video, gallery and short-link
fixtures. It must establish one stable synthetic content identity, rebuild a queryless canonical page URL,
emit only sanitized facts, and enter the existing Native Host/SQLite queue only after the owner-facing
Extension Action and Side Panel interaction.

The short-link output in this Run is a transport-injected, network-free redirect validator. Production code
contains no requester, does not call `fetch`/XHR, does not navigate the tab, and cannot resolve a real short
link. Every short code, intermediate identity and final identity must carry the fixed `synthetic-` prefix.

## 3. Allowed changes

- Douyin-specific isolated-world extractor, validator and capture-payload builder.
- Douyin synthetic redirect allowlist/canonicalization state machine with an injected fixture requester.
- Existing page recognizer, Service Worker adapter registry and Side Panel gating needed for this Task.
- Public synthetic fixtures and isolated Playwright E2E for the exact current-page and redirect matrix.
- This Run Contract, machine facts/policies, verifier/tests, compact evidence and owner-facing status docs.
- Minimal forward-compatibility edits to the Skeleton001 historical verifier so its facts remain pinned to
  its final commit while its XHS behavior still regresses against the current tree.

## 4. Forbidden changes and execution

- No `TSK.x2n.skeleton.006`, collection/list Adapter, downloader, media, ASR/OCR, classification, Notion or
  real sink work.
- No real Douyin page, account, OAuth, API, short-link request, Owner Canary or platform call.
- No new Manifest permission, Host Permission, static Content Script, Extension Storage, Native action or
  Native v1.0 Contract field.
- No automatic scrolling, account-state action, page click/playback, cookie/browser-state read, access-control
  bypass, proxy/fingerprint behavior or arbitrary URL proxy.
- No persistence or evidence of a short link, query, fragment, platform media URL, raw DOM, raw media,
  credentials, private content or local absolute path.
- No dependency addition, competitor source/runtime/output ingestion, push, PR or Stage 2 upload.

## 5. Policy and URL truth

The current official policy recheck is registered in
`machine/policy/platform_policy_registry.json`. It does not establish a general personal likes/favorites read
capability, a stable gallery route, or an exhaustive short-link object contract. The narrow public iframe and
OAuth-authorized published-video list are not substitutes for arbitrary current-page or favorites access.

Therefore only synthetic `/video/<synthetic-id>`, synthetic `/note/<synthetic-id>` and synthetic
`v.douyin.com/<synthetic-code>` fixtures are executable. A real-shaped numeric video may be recognized as a
supported platform page but is not executable. Real gallery and short-link shapes remain unsupported. Bare,
lookalike, userinfo, port, HTTP, IP and non-detail destinations fail closed.

## 6. Acceptance oracle

- DOM matrix: 8/8, including video, gallery, short canonical reconstruction, missing optional fields, stable-ID
  mismatch, feed-card rejection, multiple-detail rejection and non-synthetic short identity rejection.
- Redirect matrix: 16/16; exact two-field responses, manual redirect, omitted credentials, exact request URL,
  all five allowed redirect statuses, relative redirect, transport failure, non-redirect status, exact host/path,
  loop/limit and non-allowlisted destination rejection.
- Stable IDs: 4/4; `platform_changed`: 4/4; Observation Diff: 0.
- Query/fragment/short-link/raw/media persistence: 0; real account and platform calls: 0.
- Action-before-grant rejection: 2; owner-facing Side Panel submission after CDP Extension Action: pass.
- One Native/SQLite ledger row; 100 Service Worker restarts; lost/duplicate/wrong-status jobs: 0.
- Existing XHS fixture and full E2E remain green on the current tree.
- Owner Canary and real two-item canary are `NOT_RUN`; no real capability or G2 claim is permitted.

## 7. Verification

```bash
npm run self-test --workspace @x2n/extension
npm run test:xhs-fixtures --workspace @x2n/extension
npm run test:douyin-fixtures --workspace @x2n/extension
npm run test:e2e --workspace @x2n/extension
npm run test:douyin-extension --workspace @x2n/extension
python3.12 -B scripts/verify_skeleton_002.py \
  --verify-worktree --allow-external-main-dirty --write-evidence --require-evidence
python3.12 -B -m unittest discover -s tests -p 'test_*.py'
```

The verifier runs external processes with an allowlisted environment and does not inherit authentication
variables. Screenshots and traces are temporary; committed evidence contains only byte counts and SHA-256
receipts.

## 8. Stop, rollback and completion

Stop immediately if a non-allowlisted host/path can pass, any real/network route becomes executable, a
non-synthetic identity can enter Native, the focused tab/URL changes during capture, a forbidden artifact is
observed, or the old XHS path regresses.

Rollback is a revert of this single local Task commit and the `douyin_current_page` feature flag to false.
There is no external state, schema migration or product data to undo. Completion advances only to
`TSK.x2n.skeleton.006 / PH.X2N.2.3`; Stage 2 stays local until its later Review/Fix/Re-acceptance and G2 pass.
