# xhs-douyin-2notion handoff

## Current objective

Complete only `TSK.x2n.assurance.005 / PH.X2N.6.5`: direct bounded Owner MVP deployment, running, online smoke,
and verifiable rollback. No Alpha/Beta, fixed observation period, or soak. The implementation now uses
`owner_authorized_direct_mvp`; legacy Canary tooling is not a release prerequisite.

## Current source state

- Branch: `codex/xhs-douyin-2notion-v0001-s03-review-resume`
- Stage 0–5 and Assurance001–004 are historical completed evidence; Assurance005 is the only active Task.
- The A005 source implementation has been committed locally and the source tree is clean. It adds private owner input/state contracts, four exact 20-item
  scopes with hash-only Owner manifests, XHS visible-batch handoff, Douyin private Sidecar boundary,
  aggregate-only 80-item verification, source-only staging, Native Host install/disable, and a Side Panel health
  handshake that is bound to the same staged artifact as the Host.
- The staged extension receives one generated, hash-only `release_identity.json`; it is never present in public
  source. A stale or mismatched Side Panel cannot mint the deployment handshake.
- The source lane verifies the Owner-input Markdown contract against the immutable digest packaged with the
  Companion, so the installed Native Host does not need a repository checkout to validate private release input.
- The final acceptance runner is read-only and only emits `PASS_OWNER_MVP_DIRECT_RELEASE_CORE` after real Owner
  runtime proof. It cannot mint G6 or a release receipt from fixtures.
- Real Owner Runtime, profiles, platform calls, Notion, models, media, private-database transfer, exact release tag,
  deploy, Side Panel handshake, and online smoke are `NOT_RUN`.

## Key boundaries

- Parent repository is `MetaDatabase`; this child is only `xhs-douyin-2notion`.
- Do not read, show, modify, rotate, revoke, or use the shared GitHub Token.
- Runtime data remains private; never persist platform media CDN addresses, raw media, credentials, or browser state
  in public source/evidence.
- Exactly four MVP scopes are permitted at 20 items each. Other four platforms stay external-gated until a future
  explicit authorization; no call or live-support claim is allowed for them in this Task.
- Deployment refuses a dirty/untagged source tree and an existing Native Host. The direct first-release rollback is
  disable plus the already rehearsed private SQLite backup.

## Latest verification

- Full Companion, root, and contract `unittest discover` suites passed locally.
- Focused MVP/Native Host/acceptance tests passed; the MVP suite covers exact scopes, hash-manifest mismatch before
  adapter initialization, pointer rollback, staged Native Host binding, and stale Side Panel identity rejection.
- Contract generation, TypeScript contract checking, extension self-test/full E2E/XHS fixture suites, Ruff,
  `compileall`, source privacy scan, and a temporary candidate-artifact scan passed. All fixture platform calls remain
  `0`.
- `x2n release verify` and the acceptance runner with no private runtime fail closed as expected.

## Next work

1. Do not create `v0.0.0.1` until the Owner is ready to execute the complete direct-release sequence.
2. When the Owner is ready, create the private input and four private 20-ID hash manifests, then perform the four
   explicit actions, baseline verification, rollback rehearsal, sign-off, exact tag, deploy, staged-extension reload,
   handshake, and immediate online smoke in the documented order.
3. Only after that real sequence succeeds, run the read-only acceptance verifier and explicitly write the immutable
   receipt. Do not claim G6 from this direct-core receipt.
