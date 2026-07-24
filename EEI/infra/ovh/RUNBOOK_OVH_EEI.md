# RUNBOOK — deploy EEI refresh app to the shared governance box

**Audience:** the admin/owner who performs the live deploy. A worker prepared and
tested these artifacts; **the worker does not run any live step below.**

**Target:** `ubuntu@139.99.61.6` (owner's central governance box; Coolify).
EEI deploys as a **separate Coolify project** and must never touch, link to, or
share a network/volume with any co-tenant (Keycloak, Coolify, KMFA, the
trading gateway/API, etc.).

**Artifacts (in this repo):**
`docker-compose.ovh.yml`, `infra/docker/refresh.Dockerfile`,
`infra/docker/refresh-entrypoint.sh`, `.env.ovh.example`,
`infra/ovh/RESOURCE_SAFETY_ANALYSIS.md`.

**Hard caps (already in the compose):** `eei-db` 320 MiB / 0.75 CPU,
`eei-refresh` 320 MiB / 1.0 CPU, **both with swap disabled** (`memswap_limit ==
mem_limit`) and `oom_score_adj: 500`. The refresh cap can be 320 MiB because
the publish leg is **streaming** (server-side cursors -> chunked HTTPS batches
to the worker's authenticated publish channel; measured publisher RSS ~47 MiB
at live scale, flat with coverage). No Node/wrangler in the image; the box
holds a narrow `EEI_PUBLISH_TOKEN`, never an account-level Cloudflare
credential.

**One-time prerequisite (local, before first container start):** bind the
publish-channel secret to the worker and deploy the route:

```bash
cd <repo>/EEI/apps/cloudflare-public
openssl rand -hex 32          # -> EEI_PUBLISH_TOKEN value; store it in
                              #    _protected (never in the repo) + box env
npx wrangler secret put EEI_PUBLISH_TOKEN   # paste the same value
# the /v1/internal/publish/exec route ships with the worker deploy
# (scripts/deploy_cloud.sh from a CLEAN main checkout)
```

---

## 0. Key/SSH

```bash
KEY=/Users/linzezhang/Documents/Codex/GithubProject/_protected/alpha_deploy_private/linze_ovh_production_ed25519
ssh -i "$KEY" ubuntu@139.99.61.6
```

---

## 1. PRE-DEPLOY SAFETY GATE  (run on the box; ABORT if any check fails)

```bash
# 1a. RAM headroom. EEI needs ~230 MiB steady + a ~1-min daily spike to ~450 MiB.
free -m
#   REQUIRE: MemAvailable >= 1024 MiB.
#   If below 1024 -> ABORT. Do NOT deploy. Escalate to the owner to free room on
#   the box (governance forbids a new VPS, so the fix is trimming/right-capping a
#   co-tenant, not moving EEI off-box).

# 1b. Swap must not be actively growing. Record the baseline; the box already
#     carries ~880 MiB of cold swap — that's tolerated, but it must be STABLE.
swapon --show; cat /proc/meminfo | grep -i swap

# 1c. Baseline the co-tenants so post-deploy comparison is possible.
docker ps --format 'table {{.Names}}\t{{.Status}}' | tee /tmp/eei_pre_ps.txt
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}' | tee /tmp/eei_pre_stats.txt

# 1d. Confirm no name/port collisions with the EEI stack.
docker ps -a --format '{{.Names}}' | grep -E '^eei-(db|refresh)$' && echo "NAME CLASH -> resolve first" || echo "names free"
```

**Gate decision:** proceed only if `MemAvailable >= 1024 MiB`, swap stable, no
name clash. Otherwise stop and report to the owner.

---

## 2. SEED THE DB FROM THE LOCAL SYSTEM-OF-RECORD  (do this BEFORE first start)

The refresh loop republishes the **local** system-of-record onto live D1 by
`DELETE`-then-`INSERT`. If `eei-db` were empty on first run, the first publish
would wipe the live graph. Two protections: (a) the entrypoint **refuses to
start on an empty DB** (exit 2); (b) you seed it first, here.

```bash
# On the Mac (local EEI DB running): dump the system-of-record.
cd ~/Documents/Codex/GithubProject/MetaDatabase/EEI
set -a; source .env; set +a          # DATABASE_URL for the local eei DB
pg_dump --no-owner --no-privileges --format=custom "$DATABASE_URL" -f /tmp/eei_sor.dump
scp -i "$KEY" /tmp/eei_sor.dump ubuntu@139.99.61.6:/tmp/eei_sor.dump
```

Bring up **only the DB** first (via Coolify, or compose), then restore into it:

```bash
# on the box, after eei-db is healthy (see step 3 for how it comes up):
docker exec -i eei-db pg_isready -U eei -d eei
cat /tmp/eei_sor.dump | docker exec -i eei-db pg_restore --no-owner --no-privileges \
    --clean --if-exists -U eei -d eei
docker exec -i eei-db psql -U eei -d eei -c \
    "SELECT count(*) AS research_target FROM entities WHERE status='research_target';"
#   EXPECT: a few thousand (matches local). If it prints 0, do NOT start the loop.
rm -f /tmp/eei_sor.dump      # don't leave the dump on the box
```

> Alternative (fresh bootstrap, only if you deliberately want to rebuild from
> scratch and re-collect for hours): set `EEI_ABORT_IF_EMPTY_UNIVERSE=0` and run
> `collect_universe` once before enabling publish. Not recommended for the
> handover — restoring the dump is faster and keeps live D1 intact.

---

## 3. DEPLOY  (as a SEPARATE Coolify project)

1. Coolify → **New Project** → name `eei` (NOT inside any existing project).
2. New Resource → **Docker Compose** → point at this repo, compose file
   `EEI/docker-compose.ovh.yml`.
3. Set environment (Coolify project env, or a `.env.ovh` file for compose).
   The template lives on disk at `EEI/.env.ovh.example` **but that file is
   gitignored** (the repo ignores all `.env.*`), so it is reproduced here in
   full — copy this block:

   ```bash
   # --- Postgres (EEI system-of-record; separate from every other DB on the box) ---
   EEI_DB_NAME=eei
   EEI_DB_USER=eei
   EEI_DB_PASSWORD=CHANGE-ME-strong-unique
   # --- SEC fair-access identity (MUST contain a contact email) ---
   SEC_USER_AGENT=EEI-refresh-bot (contact: you@example.com)
   # --- Publish channel (--apply -> live D1 via the public worker) ---
   # Narrow publish token only; NEVER an account-level Cloudflare credential
   # on this shared box. Must match the worker secret (wrangler secret put).
   EEI_PUBLISH_URL=https://eei.linzezhang.com/v1/internal/publish/exec
   EEI_PUBLISH_TOKEN=CHANGE-ME-64-hex
   # --- Refresh sweep: enrich+GLEIF backfill every hour; full DELETE+INSERT
   #     republish only every 24th cycle (=daily) to stay in D1's free tier ---
   EEI_REFRESH_INTERVAL_SECONDS=3600
   EEI_PUBLISH_EVERY=24
   EEI_ENRICH_BATCH=500
   EEI_GLEIF_BATCH=300
   # --- Near-real-time watcher: poll SEC's latest-filings firehose this often;
   #     incremental-upserts only new material filings to live D1 ---
   EEI_WATCH_INTERVAL_SECONDS=60
   EEI_ABORT_IF_EMPTY_UNIVERSE=1     # keep at 1 (empty-DB publish guard)
   ```

   Notes: `EEI_DB_PASSWORD` strong + unique; `SEC_USER_AGENT` must contain a
   contact email or the pipeline fails closed; keep `EEI_ABORT_IF_EMPTY_UNIVERSE=1`;
   schedule the daily cycle **off-peak** (e.g. 18:00 UTC, matching the existing
   SEC cadence). If you want the template committed, `git add -f EEI/.env.ovh.example`.
4. **Verify no shared networking:** the compose defines only its own default
   bridge + named volumes `eei-db-data`, `eei-refresh-state`. Do not attach it to
   any co-tenant network in the Coolify UI.
5. Deploy the **DB first** and restore the dump (step 2), **then** let
   `eei-refresh` start (it waits for DB health, migrates, ensures the `sec_edgar`
   source, runs the empty-guard, then enters the loop).

Manual compose equivalent (if not driving it through the Coolify UI):
```bash
cd <repo>/EEI
docker compose -f docker-compose.ovh.yml --env-file .env.ovh up -d eei-db       # then restore dump
docker compose -f docker-compose.ovh.yml --env-file .env.ovh up -d eei-refresh  # hourly sweep + daily republish
docker compose -f docker-compose.ovh.yml --env-file .env.ovh up -d eei-watch    # 60s near-real-time freshness
```

---

## 4. POST-DEPLOY HEALTH CHECKS

```bash
# 4a. Co-tenants still healthy & unchanged vs baseline.
docker ps --format 'table {{.Names}}\t{{.Status}}'          # compare to /tmp/eei_pre_ps.txt
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}'  # Keycloak/trading ~ unchanged

# 4b. NO OOM kills anywhere on the box.
sudo dmesg | grep -i -E 'oom|killed process' | tail        # expect: nothing new
#   (or: journalctl -k --since "10 min ago" | grep -i oom)

# 4c. Swap did NOT grow materially vs the step-1b baseline.
free -m; swapon --show

# 4d. EEI caps are actually applied (swap must read 0 for both).
docker inspect eei-db eei-refresh --format \
  '{{.Name}} mem={{.HostConfig.Memory}} memswap={{.HostConfig.MemorySwap}} cpus={{.HostConfig.NanoCpus}}'
#   EXPECT: eei-db mem=335544320 memswap=335544320 ; eei-refresh mem=335544320 memswap=335544320

# 4e. EEI itself progressed a cycle and published cleanly.
docker exec eei-refresh sh -c 'tail -1 /state/.eei_refresh_runs.jsonl'
#   EXPECT JSON with "publish_rc": 0 and "publish_drill_passed": true (once the
#   first scheduled cycle has run). The D1 parity drill compares remote row
#   counts to the local export.

# 4f. Watch the FIRST live publish stay comfortably under the cap.
cat /sys/fs/cgroup/system.slice/docker-$(docker inspect -f '{{.Id}}' eei-refresh).scope/memory.peak
docker stats eei-refresh    # during the first cycle; peak should stay far < 320 MiB
```

If 4a–4c show any regression (a co-tenant unhealthy, a new OOM line, swap
climbing) → **roll back immediately** (step 5) and report.

---

## 5. ROLLBACK

EEI is fully isolated, so rollback is clean and cannot harm a co-tenant:

```bash
# Stop EEI only (Coolify: Stop/Delete the `eei` project), or via compose:
docker compose -f docker-compose.ovh.yml down            # keeps volumes
# Full removal incl. data volume (system-of-record can be re-seeded from dump):
docker compose -f docker-compose.ovh.yml down -v
```

* Stopping the loop does **not** affect live D1 — D1 is the independent serving
  copy and keeps its last published state; only the *refresh* pauses.
* No co-tenant container, network, or volume is touched by any step above.

---

## 6. ONGOING (good-neighbour maintenance)

* The steady-state cost is ~230 MiB (db + idle loop). The publish leg is
  **streaming** (implemented): publisher RSS is flat (~47 MiB measured at live
  scale) at ANY coverage, so coverage growth no longer threatens the cap. The
  remaining growth dimension is the Postgres data volume (disk), not RAM.
* Deploys/restarts/image pulls on this box happen **only in US-market-closed
  windows** (co-tenant live-trading rule): frozen Mon–Fri 13:30–20:00 UTC,
  daily 20:10–20:20 UTC, Tue 14:00–15:00 UTC.
* Re-run the pre-deploy gate before any re-deploy or cap change.
