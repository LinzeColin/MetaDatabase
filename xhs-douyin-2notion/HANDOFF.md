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
- A private Owner MVP input, release-state, or browser-handshake symlink, including a dangling one, is treated as
  unsafe rather than absent. `load`, `arm`, state persistence, and handshake recording reject it before any
  pre-switch backup, private state write, or platform action.
- The XHS profile fallback now treats a favorites/likes surface as selected only when the matching label belongs to
  a semantic interactive control (selected button/link or selected role=tab). A cosmetic profile counter with an
  `active` class is rejected before it can misclassify ordinary profile content as a relation list.
- The Douyin A005 path is now an x2n clean-room, current-visible-DOM Sidecar rather than a wrapper around a downloader:
  the Side Panel requires the matching semantic 收藏/喜欢 surface and forwards only one sanitized 20-item facts batch;
  a nonce-bound Owner-private loopback process revalidates that batch and exits after one exchange. It has no platform
  network, crawler/downloader runtime, Cookie/Profile input, automatic scroll/pagination/retry, raw media, URL, or
  Sidecar persistence surface. `provision-douyin-visible-sidecar` is the only supported bundle creator. `preflight`,
  `arm`, and each Douyin action require the owner-only executable, resolved lock, SBOM, and transitive-license report
  both to match the private input and to byte-match the current approved clean-room template; raw crawler artifacts
  therefore fail before any loopback connection or Canonical write.
- If the clean-room Douyin Sidecar fails before its ready signal, the Companion terminates and reaps the child before
  returning a fail-closed error. It does not retry, reuse the process, or leave a background loopback listener.
- The direct deployment transaction now has isolated regressions for each failure boundary: an initial Native Host
  install failure discards the staged release without switching; a pointer-switch failure disables the just-installed
  Host and discards staging; and any failed cleanup escalates to `POLICY_BLOCKED` rather than leaving an ambiguous
  release state. The public rollback entry is separately tested to disable the Native Host before moving a pointer,
  to leave the pointer unchanged if disabling fails, and to preserve a post-disable pointer failure for recovery.
  The CLI also normalizes every post-switch state-recording or rollback-cleanup failure to a safe
  `POLICY_BLOCKED` outcome after attempting the same-browser rollback.
  The release loader now verifies both authorization and the exact Runtime marker phase, so a failed active-marker
  write after online smoke is detected as integrity drift instead of silently resuming with an armed marker.
- The Douyin list extractor accepts only one corresponding platform-owned surface after exactly one selected
  收藏/喜欢 control. When the unique dedicated `user-favorite-list` / `user-like-list` coexists with an empty active
  `user-favorite-tab` / `user-like-tab` shell, it deliberately prefers the narrower dedicated list; the active tab
  is a fallback only when that list is absent. It has no generic `main` fallback and therefore cannot treat footer
  or recommendation cards as a relation list.
- The XHS profile fallback recognizes the observed rendered surface only when one visible
  `#userPageContainer.user-page` has exactly one direct active `.reds-tab-item.sub-tab-list` with the expected
  relation in exactly one visible `.reds-tabs-list.tertiary`: 收藏 for favorites, or 赞过/点赞 for likes. On the
  current transform layout it binds that relation's tab index to the same-index direct
  `.feeds-tab-container > .transform-container > .tab-content-item` only when the target panel has at least a
  meaningful 16×16 viewport intersection; an inactive transformed panel's one-pixel edge is ignored rather than
  falsely creating ambiguity. It still rejects a mapping mismatch or a target panel that is only a sliver, rather
  than accidentally reading the static `#userPostedFeeds` posts panel. The legacy `#userPostedFeeds` fallback
  remains only for a profile without any tab-content panels.
  Additional tertiary controls remain allowed only when they do not create a second matching active relation; a
  generic active class or an unrelated feed root remains rejected, and the exact-20 release gate remains mandatory.
- The final acceptance runner is read-only and only emits `PASS_OWNER_MVP_DIRECT_RELEASE_CORE` after real Owner
  runtime proof. It emits the immutable, aggregate-only `FINAL_ACCEPTANCE_BUNDLE` with a receipt-bound checksum root
  only after explicit confirmation; it cannot mint G6 or a release receipt from fixtures.
- `x2n release preflight` is a read-only aggregate A005 gate. It can prove Owner-input/state, source-tag, and
  configured-and-pinned Private-MetaDatabase-client readiness, plus known-local Chrome executable availability and
  whether Chrome has a fresh Native Host install slot, without emitting a path, content ID, credential value, or
  platform request. It cannot arm or mutate the release. `chrome_executable=AVAILABLE` does not inspect a Profile or
  claim a login. `native_host_fresh_install=READY_FOR_FRESH_INSTALL` means only that `uv`, source/runtime
  prerequisites, and the empty Host target were verified without a write; it is not an install or go-live claim.
  It independently reports a correctly provisioned fixed Douyin bundle as
  `CONFIGURED_CLEAN_ROOM_UNATTESTED` while Owner input is unavailable; that status cannot arm a release and becomes
  `CONFIGURED_AND_MATCHED` only after the private input attestation also validates.
- `x2n release input-template` contains literal, deliberately invalid replacement tokens for every Owner content hash,
  Douyin Sidecar digest, and Sidecar port. The provision command emits only the non-secret build-attestation fragment;
  it cannot fabricate the four real private 20-ID manifests, a loopback port, sign-off, or release receipt.
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

- Current Companion discovery contains 332 tests. A bounded current full rerun was stopped during the existing 10k
  Markdown rebuild without a verdict, so it is not treated as a current full-suite pass. Focused A005
  bundle/release/acceptance tests passed: 36 tests, covering exact scopes, hash-manifest mismatch before adapter
  initialization, Markdown idempotency, durable archive proof, external gates, deployment-failure cleanup, pointer
  rollback, staged Native Host binding, and stale Side Panel identity rejection.
- Contract `unittest discover` passed: 18 tests. Extension full E2E, XHS fixture suites, TypeScript contract checking,
  Ruff, schema parsing, source privacy scan, and a temporary candidate-artifact scan passed. All fixture platform
  calls remain `0`; the current candidate artifact has 93 members and 0 runtime-data files.
- The A005 verifier fails closed without a real immutable receipt, as expected. A broad historical root-suite run has
  18 failures that assert earlier Stage 0–5 states/files must still be the current state; they are outside A005 and
  must not be "fixed" by rewriting historical evidence. No A005-required suite failed.
- The approved local Runtime layout was initialized and its empty Canonical SQLite store passed integrity checks;
  all required owner-only directories now validate. Current real `release preflight` is safe and reports
  `chrome_executable=AVAILABLE`, `native_host_fresh_install=READY_FOR_FRESH_INSTALL`,
  `douyin_sidecar_bundle=CONFIGURED_CLEAN_ROOM_UNATTESTED`, `owner_input=MISSING_OR_INVALID`,
  `release_state=NOT_STARTED`, and `source_release_tag=NOT_READY`. The normal shell has not persisted a client
  configuration; a one-shot, non-invoking preflight with the approved digest-pinned
  `X2N_PRIVATE_DB_CLIENT` reports `private_durability_client=CONFIGURED_AND_PINNED`. It neither reads a Token nor
  contacts the client or any remote service.
- The A005 XHS surface-safety, clean-room Douyin Sidecar artifact/process, and Douyin semantic visible-list regressions,
  both existing XHS fixture suites, extension self-test, focused A005 Companion source-lane bundle (104), Contract
  tests (18), and Ruff passed. These remain synthetic/local checks; they do not prove an Owner baseline.
- A read-only current-profile structural audit found that the active 收藏/点赞 relations are rendered in same-index
  transform panels while `#userPostedFeeds` remains a separate static posts panel. The XHS adapters now require a
  complete same-index mapping plus a meaningful 16×16 target-panel viewport intersection, so an inactive panel's
  one-pixel transformed edge cannot block the active list; the surface-safety suite covers the positive and sliver
  rejection cases. No browser content, IDs, URLs, or platform call entered the repository.
- In the latest delegated Owner Chrome pass, the real XHS 收藏 and 点赞 panes each exposed exactly 20 first visible,
  unique items under that strict mapping without a scroll. Their IDs were hashed only in transient process memory,
  never emitted or persisted; this is not an Owner-input or platform-action claim. The real logged-in Douyin profile
  selected 收藏 and 喜欢 successfully, but the corresponding active `user-favorite-tab` / `user-like-tab` panes each
  contained only one empty placeholder descendant and zero verifiable cards after bounded no-scroll stabilization.
  There was no visible loading or empty-state text to reinterpret. The current release therefore has no valid
  four-scope exact-80 Owner input and remains undeployed. The strict tab-pane compatibility regression now covers an
  empty active relation pane with 20 out-of-pane footer links: it must remain `empty_unverified` with zero captured
  items. There are 9 zero-network fixture cases; current focused source evidence is 104 Companion tests, 18 contract
  tests, extension self-test, Douyin visible-list fixtures, Douyin extension E2E (100 controlled worker restarts),
  both XHS fixtures, and a 662-file zero-finding privacy scan.
- A subsequent delegated Owner Chrome topology audit resolved the apparent empty-panel block: the active panels are
  tab shells, while a unique visible sibling `user-favorite-list` exposes 30 legal unique relation IDs and a unique
  visible sibling `user-like-list` exposes 40, both without scrolling. The extractor's dedicated-list preference is
  covered by 11 zero-network fixture cases and the current full A005 source lane passed. Fresh private manifest
  capture may now proceed, but no Owner input, tag, deployment, or smoke claim has yet been made.

## Next work

1. Do not create `v0.0.0.1` until the Owner is ready to execute the complete direct-release sequence.
2. In the current delegated Owner run, re-observe all four scopes from their fresh visible panes without scrolling.
   Do not create an Owner input unless each has exactly 20 actual unique items; a missing/ambiguous dedicated list is
   an explicit stop condition, not a reason to substitute footer cards or invent hashes. Only then provision the
   clean-room private Douyin Sidecar, use its attestation fragment with the deliberately invalid template, replace
   every remaining Owner token with four private 20-ID hash manifests and the loopback port, configure the approved
   digest-pinned Private-MetaDatabase client, and rerun `x2n release preflight` until it reports a valid input and no
   existing release state. Then perform the four explicit actions, baseline verification, Markdown/durability
   materialization, rollback rehearsal, sign-off, exact tag, deploy, staged-extension reload, handshake, and
   immediate online smoke in the documented order.
3. Only after that real sequence succeeds, run the read-only acceptance verifier and explicitly write the immutable
   receipt and `FINAL_ACCEPTANCE_BUNDLE`. Do not claim G6 from this direct-core receipt.
4. A real Notion write needs a separately authorized Owner Integration and Parent configuration; until then A005's
   explicit zero-call Notion-disabled outcome is the only truthful release state.
