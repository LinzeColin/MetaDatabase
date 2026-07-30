# Stage 5 Task005 Run Contract — Durable Lifecycle and Governed Deletion

## Identity

- Task: `TSK.x2n.uxops.005`
- Phase: `PH.X2N.5.5`
- Run: `RUN-X2N-S05-U005`
- Scope: CI-synthetic implementation of the Private-MetaDatabase lifecycle, not a live data migration.

## Goal and minimum scope

Implement an Owner-previewable, fail-closed lifecycle for the active SQLite Canonical Store:

1. create a consistent local snapshot plus private Canonical JSONL export;
2. package the snapshot as a non-running archive, split it into domain-bound opaque chunks of at most 90 MiB;
3. use only the approved `private_db_client.py` command surface (`ingest`, `get`, `list`, `verify`) through a digest-pinned wrapper, without reading, emitting, exporting, modifying, deleting, rotating or revoking any authentication material;
4. make exact `domain=xhs-douyin-2notion` manifest rows and per-object get/hash/reassembly/SQLite-integrity the durability gate; area-global `verify` is redacted advisory only;
5. add monotonic `deletion_epoch`, append-only logical tombstones, preview/confirm deletion controls, bounded local runtime cleanup and TTL handling; and
6. support an Owner-confirmed whole-root Time Machine exclusion action on macOS, with an unsupported fail-closed result on other operating systems.

The Local WebUI may expose safe lifecycle status and preview metadata only. Any physical deletion, restore, private-client transfer or `tmutil` action requires its own exact confirmation literal at runtime.

## Explicit non-goals

This Run must not execute G5, any assurance Task, deployment, publication, Chrome Web Store work, real platform access, real account/Profile activity, real Notion writes, model calls, media acquisition, an authenticated Private-Database transfer, `tmutil`, or physical local deletion. It must not clone Private-Database, call the client `put` or `delete` commands, persist a platform CDN URL, credential, Cookie, browser state or raw platform media, or claim that a local wipe is durable hard erase.

## Data and evidence boundaries

- `X2N_DATA_ROOT` remains an ephemeral download/execution/active-SQLite working copy beneath the Owner-selected `X2N_DOWNLOAD_DESTINATION` namespace; its resolved path is never emitted publicly.
- Durable data is only `Private-MetaDatabase`, domain `xhs-douyin-2notion`, through `KMOS/KMDatabase/machine/tools/private_db_client.py`; the client source digest is rechecked before any real invocation.
- Archive object names are opaque. Public receipts contain only hashes, aggregate counts, enum states, and static error codes.
- A missing x2n object fails closed even if area-global `verify` exits successfully. Other-domain manifest/object state never blocks x2n and is never rendered to logs, WebUI or evidence.
- Direct MVP remains the release policy: no Alpha, Beta, fixed 30-day health observation, or soak gate. Deploy/run/online smoke stay in final Stage 6 `assurance.005` after the DAG and acceptance gates.

## Acceptance and validation

The synthetic suite must cover JSONL/export round-trip, chunk hash/reassembly, archive SQLite integrity, domain filtering, cross-domain same-payload isolation, missing x2n versus other-domain records, command allowlisting, token/auth zero-contact attestation, temporary get cleanup, durability-pending recovery, deletion preview/cancel/confirm, content-versus-relation tombstones, stale deletion epoch rejection, TTL, safe WebUI lifecycle status, and macOS/non-macOS exclusion contracts.

Required validation commands are recorded by `scripts/run_uxops_005_acceptance.py` and enforced by `scripts/verify_uxops_005.py`. Task004 is replayed on its fixed commit in a disposable alternate-object Git checkout; it is not evaluated against Task005 sources.

## Risks, rollback and stop condition

Default physical-delete and OS-backup-exclusion flags are off. The implementation uses temporary synthetic data only; any test artifact is removed before the test exits. Roll back by disabling lifecycle mutations, retaining only logical tombstones and the safer whole-root exclusion policy, and restoring only a verified manifest at the current deletion epoch.

Stop immediately and fail closed if any archive is a raw running `.sqlite/.db` upload, an object exceeds 90 MiB, an object name carries title/content/account/source information, an external domain affects x2n's verdict, a temporary download remains, a restore can use an older epoch or omit a tombstone, an authentication value would be accessed, or the client digest/action allowlist cannot be proven.
