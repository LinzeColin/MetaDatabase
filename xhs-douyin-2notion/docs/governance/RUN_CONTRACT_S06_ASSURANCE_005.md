# Stage 6 Assurance005 Run Contract

## Identity

- Task: `TSK.x2n.assurance.005`
- Phase: `PH.X2N.6.5`
- Release: `v0.0.0.1`
- Delivery model: direct local Owner MVP; no Alpha, Beta, fixed observation period, or soak gate

## Single-task outcome

This is the only Task that may make the bounded Owner MVP live. It may activate exactly four scopes:

| Scope | Bound | Execution surface |
|---|---:|---|
| Xiaohongshu favorites | 20 visible items | explicit Side Panel action; no automatic scroll |
| Xiaohongshu likes | 20 visible items | explicit Side Panel action; no automatic scroll |
| Douyin favorites | 20 items | Owner-private loopback Sidecar with attestation |
| Douyin likes | 20 items | Owner-private loopback Sidecar with attestation |

The four scopes form one exact 80-relation baseline. Bilibili, Kuaishou, Weibo, and Taobao remain
`DISABLED_EXTERNAL_GATE` unless a separate owner-authorized activation provides an independent manifest and at
most 20 actual items. `BLOCKED_TECHNICAL` never settles as disabled.

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

```bash
x2n release provision-douyin-visible-sidecar --confirm PROVISION_X2N_DOUYIN_VISIBLE_SIDECAR
x2n release preflight
x2n release input-template
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
its output is a non-secret attestation fragment for the private input. `preflight` first checks those four regular
files against the current clean-room template without requiring an Owner input. A matching clean-room bundle with an
unavailable Owner input is reported only as `CONFIGURED_CLEAN_ROOM_UNATTESTED`; that is an aggregate local-artifact
fact, not an input validation or an arm permission. Once the input is valid, `preflight`, `arm`, and each Douyin
action require an exact match with its Owner attestation as well. This local check never starts the Sidecar, reads
Browser state, calls a platform, or prints its relative or absolute location, filenames, byte contents, or digests.
A missing, symlinked, non-owner-only, oversized, raw-crawler, or mismatched artifact is `MISSING_OR_INVALID` and
fail-closed.

`input-template` is intentionally **not** a valid release input: every Owner content-ID hash, Douyin Sidecar
attestation digest, and loopback port is a literal replacement token. The clean-room provision command produces the
four attestation digests, while the exact four 20-ID private manifests and loopback port remain Owner-private facts.
The private owner-only input must be complete before `validate-input` can pass. The contract digest and fixed
scope/boundary fields are source-bound and must not be changed.

The private release input also contains four ordered, hash-only 20-item Owner manifests (one per enabled scope).
The Owner replaces the template placeholders with SHA-256 values of the selected stable content IDs. The Companion
compares the observed 20 IDs to that private set before any Canonical write; it never prints either the IDs or the
manifest. A mismatch stops the scope with zero write. A private input or release-state symlink, including a dangling
one, is never treated as absent: it blocks load/arm before a backup, state write, or platform action.

After `arm`, the Owner performs one explicit bounded Side Panel action for each four fixed scopes. The UI must not
scroll, alter platform account state, or run a background batch. Then complete the same release Task:

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
