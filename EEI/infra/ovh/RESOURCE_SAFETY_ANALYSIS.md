# EEI on the shared governance box — resource-safety analysis

**Scope.** Run EEI's data-collection + dynamic-refresh pipeline as a hard
resource-capped app on the owner's single central governance server
(`ubuntu@139.99.61.6`), co-existing with every other project already deployed
there. Governance policy forbids a dedicated server, so the goal is **make EEI a
good neighbour under a hard cap**, never to move it off-box.

All numbers below are **measured**, not guessed: image built from
`infra/docker/refresh.Dockerfile`, run against a hard-capped local
`postgres:16-alpine`, peaks read from the authoritative cgroup-v2 counter
`/sys/fs/cgroup/memory.peak` (not sampled `docker stats`, which can miss a
sub-second spike).

---

## 1. The box today (read-only inspection, 2026-07-23)

```
Mem:  total 3.7Gi | used 2.0Gi | free 275Mi | buff/cache 1.9Gi | available 1.8Gi
Swap: total 2.0Gi | used 878Mi        <-- already swapping
Load: 0.36 0.37 0.37  on 2 vCPU        <-- CPU is idle; the constraint is RAM
Disk: /  38G, 22G free
```

Co-tenant containers to protect (peers, never to be touched), memory at inspection:

| Container | Mem | Note |
|---|---|---|
| `identity-keycloak-1` | 543 MiB (limit 1.17G) | biggest single tenant |
| `coolify` (+ db/redis/realtime/proxy/sentinel) | ~320 MiB total | the control plane itself |
| `app-…` / `skills-…` (KMFA) | ~68 MiB | another project |
| `identity-identity-postgres-1` | 35 MiB (limit 256M) | Keycloak's DB |
| `monitoring-gatus-1` | 18 MiB (limit 128M) | uptime checks |
| 4× hash-named Coolify apps | ~1 MiB each | idle project deploys |
| host procs: `OpenD` (52M), `uvicorn` (61M), `python` (151M+64M) | | live-trading gateway + API |

**Key fact:** the box is **already under memory pressure** — only 275 MiB truly
free and **878 MiB already pushed to swap**. The "1.8 GiB available" is almost
entirely reclaimable page cache. So EEI must be sized so its *steady-state*
addition is small and its *spikes* are hard-contained.

---

## 2. EEI measured footprint (hard-capped local test)

Test DB seeded from first-hand sources: 861 research-target entities, up to
14,929 SEC-filing events, 122 GLEIF relationships (≈ current live D1 scale).

| Phase | What runs | Container cap | **Peak (cgroup)** |
|---|---|---|---|
| **DB** (`eei-db`) | postgres:16-alpine, tuned tiny (`shared_buffers=96MB`, `work_mem=4MB`, `max_connections=20`) | 320 MiB, **swap 0** | **202 MiB** @ 15k events |
| **Refresh — idle** | loop sleeping between daily cycles | 640 MiB, **swap 0** | **27.5 MiB** |
| **Refresh — collectors** | `refresh_cycle` enrich_sec + collect_gleif (stream one company at a time) | 640 MiB | **63 MiB** |
| **Refresh — publish** @ 1% | `publish_to_cloud_channel` render (1.7k events, 1.5 MB SQL) | 640 MiB | **266 MiB** |
| **Refresh — publish** @ live | same, 14.9k events, **12.1 MB SQL** | 640 MiB | **365 MiB** |

Image size: 660 MB (Python 3.13 + psycopg + httpx + pinned Node 20 + wrangler
4.42 for the D1 publish leg).

### What this means for the host

* **24/7 steady-state cost of EEI ≈ ~230 MiB actual RSS** (DB ~150–200 MiB +
  loop ~28 MiB). `mem_limit` is a *ceiling*, not a reservation — the containers
  only commit pages they actually use, so day-round EEI adds ~230 MiB, which the
  kernel can absorb by reclaiming a slice of the 1.9 GiB page cache.
* **The only stress event is a ~1-minute daily publish spike** to ~365 MiB
  (measured, render + wrangler r2 probe). The live `--apply` path additionally
  streams the 12 MB SQL file to D1 through Node; the 640 MiB cap is sized to
  cover that upload leg with margin (the measurement deliberately did **not**
  touch live D1).
* **CPU is a non-issue** (box load 0.36 / 2 vCPU); caps are `0.75` (db) + `1.0`
  (refresh).

---

## 3. Growth curve — the one real limiter

Publish memory grows ~linearly with the **published surface**, and the project's
stated baseline is *full* universe coverage. Measured: 6k rows → 266 MiB, 19k
rows → 365 MiB (≈ +7.6 MiB per 1,000 rows on top of a ~90 MiB fixed floor for
the Python interpreter + spawned Node).

The publisher (`export_publication_surface` + `render_sql`) **materialises the
entire surface in memory at once** — all rows as Python dicts, then a single
multi-MB SQL string (and, transiently, both the list of statement fragments and
the joined string). Extrapolated to full coverage (~8,000 companies × ~27
events ≈ 210k events → ~650k published rows, ~170 MB SQL):

> **publish peak would reach ~1.5–2 GiB — impossible under any small cap.**

So: **EEI fits the box comfortably at today's scale**, but *the publish step is
what will eventually break a flat cap as coverage grows toward the baseline.*

**Recommended enabling change (out of scope for containerisation, flagged for a
follow-up):** make publish streaming so its memory stays flat forever —
(1) read each table with a **server-side named cursor** (`itersize`) instead of
`fetchall`; (2) **append** `INSERT` chunks to the `.sql` file as you go instead
of building one giant string; (3) feed D1 in **file chunks** via successive
`wrangler d1 execute --file` calls. This keeps the whole loop under ~150 MiB at
any coverage and is the clean way to honour "full coverage on a shared cap".
Until then, the 640 MiB cap holds to roughly **2× current event coverage
(~30k events)**; past that, re-run the measurement and either implement
streaming or (only after a fresh headroom check) raise the cap.

---

## 4. How the host stays safe

1. **Hard mem cap + zero swap per service.** `mem_limit` **and**
   `memswap_limit == mem_limit` → the container's swap ceiling is 0. If EEI ever
   exceeds its cap it is **cgroup-OOM-killed and restarted (contained to EEI)**,
   never allowed to swap and drag the co-tenants (or the trading gateway) into
   disk thrash. This is the single most important guardrail on a box that is
   already 878 MiB into swap.
2. **`oom_score_adj: 500`** on both EEI services → in the unlikely event of
   box-wide pressure, the kernel prefers to kill EEI over Keycloak / OpenD /
   Coolify.
3. **CPU caps** (`cpus` 0.75 + 1.0) so a cycle can't starve the 2 vCPU box.
4. **Total hard ceiling 640 MiB** (320 + 320; refresh lowered from the draft
   640 after the streaming publish landed — see §6), but **actual 24/7 draw
   ~230 MiB**; leaves the box's reclaimable-cache headroom intact at rest.
5. **Full isolation from peers.** Separate Coolify project, its own
   `eei-db`/`eei-refresh` containers, its own bridge network and named volumes —
   it never links to, shares a network/volume with, or names any co-tenant.
6. **Off-peak schedule.** The daily spike runs on the refresh interval; point it
   at a low-activity window (the existing SEC cadence is 18:00 UTC) so the spike
   never coincides with a trading burst.
7. **Empty-DB publish guard.** The entrypoint refuses to start (exit 2) if the
   system-of-record has 0 research-target entities, so a first publish can never
   `DELETE` the live D1 surface and replace it with nothing.

---

## 5. Verdict

* **Does ~1.8 GiB "available" safely fit EEI alongside the other projects?**
  **Yes, at today's scale, as a hard-capped app** — steady-state ~230 MiB with a
  contained, off-peak, ~1-minute daily spike. No dedicated VPS (correctly
  disallowed by governance); none is needed for the current footprint.
* **Caveats the owner must accept:** the box is already swapping, so (a) EEI
  must keep the no-swap caps exactly as specified, (b) the pre-deploy gate in the
  runbook must pass before every deploy, and (c) the **publish step must be made
  streaming before coverage approaches full**, or its memory will outgrow any
  shared-box-safe cap. The first two are enforced by the artifacts here; the
  third is DONE — see §6.

---

## 6. Addendum (2026-07-23) — streaming publish implemented

The §3 limiter is resolved. `publish_to_cloud_channel.py` is now streaming end
to end: every table is read through a **server-side named cursor** and rendered
into bounded multi-row INSERTs, and the apply leg POSTs **chunked statement
batches** to the public worker's authenticated internal channel
(`/v1/internal/publish/exec`, bearer `EEI_PUBLISH_TOKEN`, atomic D1 batch per
request). Consequences, all measured on the live-scale surface (9,635 entities
/ 3,044 relationships / 13,103 events, 482 statements):

| What | Before | After |
|---|---|---|
| Publisher peak RSS @ live scale | 365 MiB (cgroup peak) | **47 MiB** (`/usr/bin/time -l` max RSS) |
| RSS at full-coverage extrapolation (~210k events) | ~1.5–2 GiB (impossible) | **flat ~<100 MiB** (bounded chunks) |
| Node + wrangler in the image | required (660 MB image) | **removed** (pure-Python image) |
| Cloudflare credential on the box | account-level API token | **narrow publish token only** |
| `eei-refresh` mem_limit | 640 MiB | **320 MiB** (matches the co-tenant ruling) |

Both transports produce byte-order-identical statement streams (statement and
row counts verified equal); `--transport wrangler` remains for local manual
runs via the OAuth session.
