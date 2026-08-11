# Social Archive v0.0.0.6 Validation Report

**Status: DEGRADED — not PASS.** 23 of 32 tasks pass. Nine are `BLOCKED_ENVIRONMENT` behind four root causes, and every one of them needs an Owner action at a provider UI.

## What is real

Production runs the current candidate on the OVH node `vps-83b882b4` from `/opt/social-archive`: `social-archive/core:0.0.0.6`, public API reporting `0.0.0.6`, PWA serving `assets/app.js?v=006-r1`, all three containers healthy.

- **Storage.** All 17 pending artifacts — the canary plus a real Bilibili video and a real Xiaohongshu post with their media — replicated to R2 and OCI as age-x25519 ciphertext, 17/17 on each. A separate no-user-data canary wrote, read back against its recorded cipher hash, and deleted itself on both stores.
- **Destinations.** GitHub private Markdown, local Markdown, the Obsidian vault and JSONL all carry the same `projection_sha256`. The GitHub copy was re-fetched independently through the contents API from the developer machine and hashed locally, not re-read from the writer's own buffer.
- **Authority.** The Private-Database fact synced through the official clone-free client and the immediate re-run returned `NO_CHANGE`, so delivery is marked only after a strict readback. `local_checkout` stayed false throughout.
- **Recovery.** Cold backup produced two verified remote copies and two verified recovery descriptors; both R2 and OCI restore to the same plaintext hash, verify-only and for real. Object-level recovery passes from R2 and OCI.
- **Edge.** `doctor.sh --self-test` passes 28 deployment-contract checks. The credential-free public smoke behaves exactly as intended: library returns the Access login boundary, health and the non-sensitive pairing status are public, `/v1/library`, `/v1/accounts` and `/v1/destinations` all return 401, and the status projection answers 200.
- **Library.** Against live production the table sorts by relation time descending by default, carries the six mandatory columns, sorts by any allowed column with ascending as the exact reverse of descending, and narrows correctly on Chinese full-text search and platform filter. No demo rows.

Full application regression: **310 passed**. Structural verify PASS. Sealed task pack verify PASS on a clean extraction with zero failures, 395 manifest entries and 97 candidate tests.

## Defects found and fixed

Running the task pack's own per-task gates end to end — which earlier runs had not done — surfaced seven real problems.

1. **Pairing-code rotation could never reach a running Core.** Compose publishes each secret as an individual file bind mount, so the container follows the *inode*, and rotation used temp-file plus `os.replace`. Core kept serving the pre-rotation record indefinitely. This is why production sat at `one_time_code_available=false, attempts_remaining=0` and no extension could pair; earlier runs recorded it as an unexplained environment block. Now rotates in place under `flock`, with the reader taking a shared lock. Verified live: minting flips the public status with no restart.
2. **Locale-fragile shell quoting.** `start_readers.sh` and `prepare_systemd_host.sh` interpolated bare `$secret`, `$HOST_DATA_ROOT` and `$key` immediately before full-width punctuation. Under a C/POSIX locale — what systemd units and `docker exec` normally get — bash folds the leading continuation byte into the identifier and `set -u` aborts.
3. **`doctor.sh --self-test` crashed** with a `UnicodeDecodeError` naming no file, because a macOS-side copy had left nine AppleDouble sidecars in the deploy tree and two sat beside `api.py` and `db.py`.
4. **The GitHub archive repository pointed at `Private-Database`**, which would have collapsed the object-bytes plane into the structured-facts plane. The dedicated vault also did not exist, despite an earlier run recording its creation.
5. **`backup.py` chained the two cold-backup stores.** An R2 failure marked OCI `blocked_prerequisite` and never attempted it, taking the offsite copy from two copies to zero exactly when it was most needed. The frozen pack already iterated them independently.
6. **`ExportRequest` and `PairingRequest` accepted unknown fields**, so a request naming `destinations` instead of `destination_ids` returned 202 having exported nothing.
7. **Stale v0.0.0.5 contracts.** Five test files still asserted the superseded shell, and the three-receipt completion contract was asserted as a string in the extension rather than as the server invariant in `db.py`.

One prior claim was retracted: earlier evidence concluded the Cloudflare Tunnel origin was a container on the developer Mac. Deploying only the OVH host flipped the public endpoint while the Mac container stayed untouched, which settles it.

## What is not done, and why it needs the Owner

| Root cause | Tasks | Why only the Owner can clear it |
|---|---|---|
| Extension not installed in the logged-in Chrome | SA-205, SA-303, SA-305 | No browser is connected to the agent session, so the profile is unreachable. The install entry point is verified working and the package is confirmed 0.0.0.6 with `bridge.js`. |
| No fine-grained token for `LinzeColin/Social-Archive-Vault` | SA-503, SA-506 | Fine-grained tokens select repositories by ID, so recreating the name cannot re-attach the orphaned token, and no GitHub API can widen one. Using the broad local OAuth credential on the host, or retargeting the third copy at `Private-Database`, were both rejected as boundary violations. |
| No Notion Integration token or shared `data_source_id` | SA-402, SA-404 | Notion Integration tokens exist only behind Notion's own UI. `export_all.py` does emit `notion-import.csv` as a zero-credential manual route. |
| Host disk capacity | SA-304 | Karakeep and Linkwarden need several GB; the 38 GB root is at 90 percent serving about eight unrelated projects. Pruning another project's images or volumes is not a build-agent decision. |

SA-507 is blocked by all of the above.

## Release actions

None. No push, tag, release, image publish or timer enablement, per the standing instruction not to push until the whole task pack is complete. The branch `claude/social-archive-v0-0-0-6-eaad48` is local only.

## Rollback

The source tarball `/opt/social-archive-rollback/opt-social-archive-source-20260803T055259Z.tar.gz` was drilled and is sound: tar intact, 6351 members, `VERSION` 0.0.0.5, compose pinned to `:0.0.0.5`, Dockerfile and 28 source modules present. The dated `.env` backups sit beside it.

**Correction:** an earlier version of this report also listed the `:0.0.0.5` images as retained. They are not — they were removed during the cleanup after the failed Karakeep pull, and the claim had been asserted rather than checked. Rollback therefore needs a rebuild rather than an instant image swap, roughly five minutes and about 1 GB of disk.

```bash
sudo tar -xzf /opt/social-archive-rollback/opt-social-archive-source-20260803T055259Z.tar.gz -C /opt \
  && cd /opt/social-archive \
  && sudo cp /opt/social-archive-rollback/env-20260803T055259Z.bak .env \
  && sudo docker compose build core-api core-worker cli-tools \
  && sudo docker compose up -d
```

That overwrites the source tree in place. `runtime/`, the secrets and the SQLite data plane live outside the tarball and are untouched.
