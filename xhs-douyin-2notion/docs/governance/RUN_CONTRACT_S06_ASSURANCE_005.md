# Stage 6 Assurance005 Run Contract

## Identity

- Task: `TSK.x2n.assurance.005`
- Phase: `PH.X2N.6.5`
- Release: `v0.0.0.1`
- Delivery model: direct local Owner MVP; no Alpha, Beta, fixed observation period, or soak gate
- Scope amendment: `CE-X2N-20260729-S06-A005-XHS-CURRENT-CONTENT`

## Single-task outcome

This is the only Task that may make the bounded Owner MVP live. It may activate exactly four scopes:

| Scope | Bound | Execution surface |
|---|---:|---|
| Xiaohongshu favorites | 20 visible items | explicit Side Panel action; no automatic scroll |
| Xiaohongshu current content (`xiaohongshu_current_content`) | 20 explicit detail pages | 20 separate Owner gestures; no auto-scroll, pagination, navigation, or retry |
| Douyin favorites | 20 items | Owner-private loopback Sidecar with attestation |
| Douyin likes | 20 items | Owner-private loopback Sidecar with attestation |

The four scopes form one exact 80-relation baseline. Bilibili, Kuaishou, Weibo, and Taobao remain
`DISABLED_EXTERNAL_GATE` unless a separate owner-authorized activation provides an independent manifest and at
most 20 actual items. `BLOCKED_TECHNICAL` never settles as disabled.

For this A005 baseline only, Xiaohongshu likes remains a CI-synthetic capability and is excluded from the live
Owner scope set. Xiaohongshu current content uses relation `saved_current`; it must never be represented as a
likes batch or be collected by synthetic list expansion.

The only executable Douyin implementation in this Task is the x2n clean-room visible-DOM Sidecar. It consumes one
sanitized, current-DOM batch from the explicit Side Panel gesture through a nonce-bound local loopback exchange and
then exits. It has no platform network route, crawler/downloader dependency, Cookie/Profile input, auto-scroll,
pagination, retry, raw-media, URL, or persistent Sidecar data surface. `jiji262/douyin-downloader` and
`ShilongLee/Crawler` remain non-executable research references; they are not bundled, installed, launched, or
accepted as a Sidecar artifact.
For every disabled external scope, public-safe evidence records the permitted external reason, disabled flag, zero
platform calls, and no live-support claim; a count-only assertion is not sufficient.

## Preconditions and public software lane

Before private Owner operations, run the bounded source checks:

```bash
PYTHONPATH=apps/companion/src:packages/contracts/src \
  .venv/bin/python -B -m unittest \
  apps.companion.tests.test_douyin_visible_sidecar \
  apps.companion.tests.test_mvp_release \
  apps.companion.tests.test_native_host \
  apps.companion.tests.test_adapter_dispatch \
  apps.companion.tests.test_douyin_adapter \
  apps.companion.tests.test_xiaohongshu_favorites \
  apps.companion.tests.test_xiaohongshu_likes
PYTHONPATH=packages/contracts/src .venv/bin/python -B -m unittest discover -s packages/contracts/tests -p 'test_*.py'
npm run self-test --workspace @x2n/extension
npm run test:douyin-visible-lists-fixtures --workspace @x2n/extension
npm run test:douyin-extension --workspace @x2n/extension
npm run test:xhs-favorites-fixtures --workspace @x2n/extension
npm run test:xhs-likes-fixtures --workspace @x2n/extension
```

The release source must be clean and carry the unique `v0.0.0.1` tag immediately before deployment. The release
command verifies both facts locally; it neither reads nor changes any credential, remote, or shared GitHub Token.
The source lane also verifies the Owner-input Markdown contract against the immutable digest packaged into the
Companion, so the installed Native Host never depends on an unchecked repository path at runtime.

## Owner-operated direct MVP sequence

All private input files are owner-only local files. Their contents, local locations, browser profile state, media,
credentials, cookies, content, and platform CDN URLs must never enter public output or Git.

Before any arm or Canonical write, use the Side Panel on the already selected visible surfaces: one hash-only
20-item preparation action for Xiaohongshu favorites, Douyin favorites, and Douyin likes, then 20 separate explicit
Xiaohongshu detail-page preparation actions. The preparation path never scrolls, paginates, navigates, retries,
creates a Canonical row/job, or changes account state. It retains only SHA-256 stable content identifiers in the
owner-only pre-arm state; it does not ask the Owner to copy IDs, compute hashes, edit JSON, or use a template.
Exactly four unique 20-item sets atomically freeze the private release input. A repeated/changed list, duplicate
current item, incomplete batch, invalid detail identity, existing input/state, or invalid private Sidecar stops with
no Canonical write and no changed release input.

The Side Panel uses a temporary, source-bound Native Host only as the pre-arm bridge. It is not a deployment or
release artifact: install it from the same clean source that provides the unpacked pre-arm Side Panel, complete the
hash-only preparation, then uninstall that owned temporary Host before `preflight`. Uninstalling the owned bridge
must preserve the private enrollment/input files while removing its Host runtime and manifest; only then may
`preflight` report a fresh Native Host slot for the staged tagged deployment. An unowned, incomplete, or residual
Host blocks rather than being replaced.

```bash
x2n release preflight
x2n release validate-input
x2n release arm --confirm ARM_X2N_OWNER_MVP_ACTIVATION
```

`preflight` is aggregate-only and read-only: it reports whether the Owner input, pre-arm state, local source tag,
approved Private-MetaDatabase client, fixed Owner-private Douyin Sidecar artifact bundle, local Chrome executable,
and a fresh Chrome Native Host slot are ready, while
emitting no local paths, private values, content IDs, or platform calls. `chrome_executable=AVAILABLE` proves only
that a known local Chrome executable is available; it does not inspect a Profile, load an extension, or claim a login.
`native_host_fresh_install=READY_FOR_FRESH_INSTALL` proves only that the installer prerequisites are present and no
Host target/residual blocks a first install; it is not an install or a go-live claim. It never creates the input, arms
a scope, calls the client, or opens Chrome.
A source tag is expected to remain `NOT_READY` until immediately before the later `deploy` command.

The Douyin bundle is a fixed Owner-only private layout under the Runtime root and contains the Sidecar executable,
resolved lock, SBOM, and transitive-license report. `provision-douyin-visible-sidecar` is the only supported creator;
the pre-arm finalizer invokes the same creator only when a matching bundle is not already present. It never accepts
an upstream crawler/downloader bundle. `preflight` first checks those four regular files against the current
clean-room template without requiring an Owner input. A matching clean-room bundle with an
unavailable Owner input is reported only as `CONFIGURED_CLEAN_ROOM_UNATTESTED`; that is an aggregate local-artifact
fact, not an input validation or an arm permission. Once the input is valid, `preflight`, `arm`, and each Douyin
action require an exact match with its Owner attestation as well. This local check never starts the Sidecar, reads
Browser state, calls a platform, or prints its relative or absolute location, filenames, byte contents, or digests.
A missing, symlinked, non-owner-only, oversized, raw-crawler, or mismatched artifact is `MISSING_OR_INVALID` and
fail-closed.

If the clean-room Sidecar process fails before its one-use ready signal, the Companion terminates and reaps that
child before returning its fail-closed error. It never retries, reuses a process, or leaves a background listener.

`input-template` remains a diagnostic-only, deliberately invalid public shape; it is never part of the Owner's MVP
workflow. The pre-arm finalizer creates the only valid input from the four prepared hash-only sets, its local
clean-room Sidecar attestation, and a private loopback port. The Companion validates that candidate before its atomic
private write. The release input contains four ordered, hash-only 20-item manifests and never prints IDs or hashes.
The Companion compares each post-arm list action's observed 20 IDs to its private set before any Canonical write.
For Xiaohongshu current content, it compares the stable ID of every one of the 20 explicit detail-page captures
before that capture's first Canonical write, and persists only its SHA-256 plus opaque Native Job ID. A mismatch
stops the affected action with zero write. A private enrollment/input/release-state/browser-handshake symlink,
including a dangling one, is never treated as absent: it blocks the corresponding action before a backup, private
state write, or platform action.

After `arm`, the Owner performs one explicit bounded Side Panel action for each of the three list-backed scopes,
then 20 separate explicit Xiaohongshu detail-page capture actions for the current-content scope. The UI must not
scroll, alter platform account state, auto-navigate, retry, or run a background batch. Then complete the same
release Task:

```bash
x2n release baseline-verify
x2n release materialize-knowledge-assets --confirm MATERIALIZE_X2N_OWNER_MVP_KNOWLEDGE_ASSETS
x2n release rollback-rehearse
x2n release signoff --confirm SIGN_OFF_X2N_OWNER_MVP
x2n release deploy --browser chrome --confirm DEPLOY_X2N_OWNER_MVP_V0_0_0_1
```

`materialize-knowledge-assets` runs two deterministic local Markdown rebuilds from the Canonical SQLite baseline and
requires the second pass to have zero derived writes. It then verifies a current Canonical archive through the
approved Private-MetaDatabase client without exposing or contacting any credential value. The current Owner input
keeps Notion explicitly disabled, so this action records zero Notion calls rather than claiming a Notion write.
Any missing or invalid Markdown/durability proof blocks rollback rehearsal and sign-off; it is not a waiting period.

`deploy` stages the source-only artifact, writes one hash-only Side Panel release identity into that private staged
copy, installs a fresh Native Host transactionally **from that staged Companion and contract source**, verifies the
Host's artifact binding, then switches `current`. It refuses to overwrite an existing Native Host: migration of an
older installation is a separate Owner task.
Rollback for this first release is therefore an immediate disable path, plus the verified Canonical SQLite backup.

The Owner then loads/reloads the staged local extension in Chrome, opens its Side Panel, and uses **Refresh** once.
That native health request records a no-content Side Panel handshake only when its generated staged release identity
matches the deployed Native Host artifact. Complete the immediate online smoke:

```bash
x2n release online-smoke --browser chrome --confirm ONLINE_SMOKE_X2N_OWNER_MVP_V0_0_0_1
x2n release verify
PYTHONPATH=apps/companion/src:packages/contracts/src \
  .venv/bin/python -B scripts/run_assurance_005_acceptance.py
```

`online-smoke` requires both the Side Panel handshake and a local Native Host health frame. It makes zero platform,
model, media, or Notion calls. `verify` re-reads the aggregate four-scope baseline, validates the staged artifact,
and requires the source tag; it cannot mint a go-live claim from a synthetic or incomplete state. The final
Assurance005 verifier is read-only: it repeats the aggregate runtime proof, checks all four external-gate settlements,
verifies that the Native Host is bound to the same staged artifact, and runs the public source-artifact scan in a
temporary directory. After the Owner reviews its safe JSON output, the same command may write the immutable public
receipt together with the aggregate-only `FINAL_ACCEPTANCE_BUNDLE` (including release notes and System Card) only
with an explicit confirmation:

```bash
PYTHONPATH=apps/companion/src:packages/contracts/src \
  .venv/bin/python -B scripts/run_assurance_005_acceptance.py \
  --write-public-receipt --confirm WRITE_X2N_ASSURANCE_005_PUBLIC_RECEIPT
.venv/bin/python -B scripts/verify_assurance_005.py
```

Neither command initiates a new capture, platform request, profile operation, deployment, or observation period.

## Immediate rollback

```bash
x2n release rollback --confirm ROLLBACK_X2N_OWNER_MVP
```

The rollback first disables execution in the private marker and release state, then uninstalls the fresh Native Host
and switches the staged extension pointer back to the previous version or disabled. Canonical records are retained;
the pre-switch backup has already been rehearsed. A failure remains fail-closed and must be resolved before any
new activation.

## Stop conditions

Stop immediately if an Owner input is missing or unsafe; any 20-item action is not exact; a secret, private value,
absolute local path, raw media, or platform CDN address reaches public output; the Side Panel handshake is absent;
the tagged source/artifact differs; deployment or rollback cannot complete; or any security, evidence, idempotency,
or recovery assertion is unknown. None of these conditions is replaced by a waiting period.
