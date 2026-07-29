# xhs-douyin-2notion handoff

## Current objective

Complete only `TSK.x2n.assurance.005 / PH.X2N.6.5`: direct bounded Owner MVP deployment, running, online smoke,
and verifiable rollback. No Alpha/Beta, fixed observation period, or soak. The implementation now uses
`owner_authorized_direct_mvp`; legacy Canary tooling is not a release prerequisite.

## Current source state

- Branch: `codex/xhs-douyin-2notion-v0001-s03-review-resume`
- Stage 0–5 and Assurance001–004 are historical completed evidence; Assurance005 is the only active Task.
- The A005 source implementation adds private owner input/state contracts, four exact 20-item scopes with hash-only
  Owner manifests, XHS visible-batch handoff, Douyin private Sidecar boundary, aggregate-only 80-item verification,
  source-only staging, Native Host install/disable, and a Side Panel health handshake bound to the same staged
  artifact as the Host.
- Before sign-off it now runs two deterministic Markdown rebuilds from the Canonical SQLite baseline, requires the
  second pass to make zero derived writes, and verifies the resulting archive through the approved
  Private-MetaDatabase client. The private release-state schema is `1.1` and persists only aggregate hashes/counts.
  Notion remains explicitly disabled by the current Owner input, with zero Notion calls rather than a false write
  claim.
- The staged extension receives one generated, hash-only `release_identity.json`; it is never present in public
  source. A stale or mismatched Side Panel cannot mint the deployment handshake.
- The source lane verifies the Owner-input Markdown contract against the immutable digest packaged with the
  Companion, so the installed Native Host does not need a repository checkout to validate private release input.
- The final acceptance runner is read-only and only emits `PASS_OWNER_MVP_DIRECT_RELEASE_CORE` after real Owner
  runtime proof. It emits the immutable, aggregate-only `FINAL_ACCEPTANCE_BUNDLE` with a receipt-bound checksum root
  only after explicit confirmation; it cannot mint G6 or a release receipt from fixtures.
- `x2n release preflight` is a read-only aggregate A005 gate. It can prove Owner-input/state, source-tag, and
  configured-and-pinned Private-MetaDatabase-client readiness without emitting a path, content ID, credential value,
  or platform request. It cannot arm or mutate the release.
- `x2n release input-template` now contains literal, deliberately invalid replacement tokens for every Owner content
  hash, Douyin Sidecar digest, and Sidecar port. It cannot accidentally validate or arm until the Owner has supplied
  the real private facts; the source-bound contract digest and fixed boundaries remain intact.
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

- Full Companion `unittest discover` passed: 322 tests. Focused A005 bundle/release/acceptance tests passed: 23
  tests, covering exact scopes, hash-manifest mismatch before adapter initialization, Markdown idempotency, durable
  archive proof, external gates, pointer rollback, staged Native Host binding, and stale Side Panel identity rejection.
- Contract `unittest discover` passed: 18 tests. Extension full E2E, XHS fixture suites, TypeScript contract checking,
  Ruff, schema parsing, source privacy scan, and a temporary candidate-artifact scan passed. All fixture platform
  calls remain `0`; the candidate artifact has 91 members and 0 runtime-data files.
- The A005 verifier fails closed without a real immutable receipt, as expected. A broad historical root-suite run has
  18 failures that assert earlier Stage 0–5 states/files must still be the current state; they are outside A005 and
  must not be "fixed" by rewriting historical evidence. No A005-required suite failed.
- The approved local Runtime layout was initialized and its empty Canonical SQLite store passed integrity checks;
  all required owner-only directories now validate. Current real `release preflight` is safe and reports
  `owner_input=MISSING_OR_INVALID`, `release_state=NOT_STARTED`,
  `private_durability_client=NOT_READY`, and `source_release_tag=NOT_READY`.

## Next work

1. Do not create `v0.0.0.1` until the Owner is ready to execute the complete direct-release sequence.
2. When the Owner is ready, use the deliberately invalid template only as a private shape, replace every Owner token
   with four private 20-ID hash manifests and Sidecar facts, configure the approved digest-pinned
   Private-MetaDatabase client, and rerun `x2n release preflight` until it reports a valid input and no existing
   release state. Then perform the four explicit actions, baseline verification, Markdown/durability
   materialization, rollback rehearsal, sign-off, exact tag, deploy, staged-extension reload, handshake, and
   immediate online smoke in the documented order.
3. Only after that real sequence succeeds, run the read-only acceptance verifier and explicitly write the immutable
   receipt and `FINAL_ACCEPTANCE_BUNDLE`. Do not claim G6 from this direct-core receipt.
4. A real Notion write needs a separately authorized Owner Integration and Parent configuration; until then A005's
   explicit zero-call Notion-disabled outcome is the only truthful release state.
