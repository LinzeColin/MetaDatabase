# CB-010 Resource Baseline

## Result

`passed`

The Owner directed this Run to resolve the target from existing local deployment
records. A unique primary OVH asset, strict known-host identity and key-only deployment
identity were found in the protected local operations record. No address, credential or
private-key material was persisted in this project.

Three immediate snapshots from that same authenticated host selected
`constrained`, guard=`recover`, activation-safe=`true`. Ports 8765/8780 and all four
proposed CyberBoss paths were absent. A separate read-only probe confirmed the existing
Status host-direct compose, collector, snapshot, cron ingestion, mounts and Traefik
routing without persisting their raw configuration or project rows.

The bounded live fixture then passed inside an ephemeral, non-root, no-network,
read-only-root container with 128 MiB memory/swap, 32 PID and 0.25 CPU hard limits.
It allocated 16 MiB RAM, wrote and removed 8 MiB temporary data, exercised 100 queue
items and completed recover → warn/protect → recover with zero OOM/kill events.

## Evidence classification

| Evidence | Result | What it proves | What it does not prove |
|---|---|---|---|
| `public-status-observation.json` | observed | Current public Status schema and aggregate host indicators | total/available RAM, swap, inode, listeners, units, containers, path conflicts |
| `preflight.local-linux-container.json` | pass | Default Linux collector executes three snapshots with no network and fails closed against a finite 512 MiB cgroup | OVH resources, listeners, services or path conflicts |
| `resource-pressure.local-container.json` | pass | Bounded fixture, cgroup limit visibility, guard ladder and zero observed OOM kill in a local container | OVH headroom, existing-service isolation or production cgroup behaviour |
| `live-host-preflight.redacted.txt` | pass | Same-host OVH memory/swap/load/disk/inode, listeners, process/service/container summaries, Status ingestion and conflict inventory | Runtime installation or online Status mutation |
| `live-host-pressure.redacted.json` | pass | Authorized-host safety gate, finite live container cgroup, exact induced bounds, recovery and zero OOM-kill delta | Production Runtime workload behavior |
| `test_resource_profile.py` | 7/7 pass | Profile selection, cgroup ceiling, pressure downgrade, guard transitions, safe/unsafe writes and read-only check mode | Which profile is safe on the real host |
| `preflight.sh --check` | pass | Three-immediate-snapshot and clean-shell contract without live reads or persistent host writes | Live host measurements |

The local container evidence explicitly sets `claimed_as_live_host_evidence=false`.
The separate live evidence explicitly binds both artifacts to the same pseudonymous host
identity and sets the bounded fixture's live-evidence scope only for that authorized run.

The default Linux-path fixture uses an already-local pinned image with
`--pull=never`, network disabled, read-only root, all capabilities dropped and
no-new-privileges. It exposed and now guards against a real false-selection case:
when `/proc/meminfo` reports host memory larger than a finite cgroup,
the most restrictive current/ancestor `memory.max/current` and
`memory.swap.max/current` values define the effective ceiling and headroom.
The 512 MiB fixture therefore selects `constrained` but blocks activation instead
of incorrectly selecting `standard`.

## Authorized-target resolution

The earlier public observation truthfully records that its deliberately narrow discovery
scope—SSH alias names and environment-variable names—found no target. It remains an
immutable historical observation.

The Owner then explicitly directed this Run to resolve access from local Alpha/KMFA/OVH
deployment records and complete the in-scope work autonomously. The protected operations
record supplied:

- one primary asset repeated consistently across baseline, status and handover records;
- an existing deployment identity with `0600` file mode;
- three matching local known-host records and strict host-key verification;
- successful key-only BatchMode authentication as an unprivileged user.

The address and credential values were used only by the local SSH client and were never
printed, copied into CyberBoss or committed. The live fixture was run only after the
read-only baseline passed its safety budget, and only with the TaskPack's exact bounded
allocation.

## Measured live baseline

All three snapshots completed in less than one second and reported:

| Metric | Measured boundary |
|---|---:|
| Host memory | 3819 MiB total; 1948–1955 MiB available |
| Swap | 2047 MiB total; 1095 MiB free |
| CPU/load | 2 CPU; 0.938 one-minute load |
| Root storage | 15,558 MiB free; 59.7% blocks; 8.4% inodes used |
| Existing containers | 21 running |
| Proposed listeners | 8765 and 8780 both free |
| Proposed paths | app/state/workspace/config all absent |

Selected limits are `MemoryHigh=768M`, `MemoryMax=1152M`, `TasksMax=256`,
queue protect at 20, a 512 MiB memory safety reserve and a 4 GiB disk reserve.
The calculated runtime memory budget was 1436 MiB, so `MemoryMax` fits while retaining
the reserve. Disk caps also fit the measured free space while retaining the reserve.

The collector reported missing Node, Codex, rclone and sqlite3 as deployment
remediations, so its overall line is `PASS_WITH_ACTIVATION_PENDING`. That is not a
CB-010 capacity failure: this task establishes safe host boundaries before later tasks
install or activate the Runtime. No missing core collector command, protect state,
listener collision or path collision was present.

## Existing Status integration

The live whitelist probe found two Status containers, one Traefik container, ten routed
containers, five Status-source mounts across two containers, the expected compose,
collector/web/data directories and a fresh JSON snapshot. Two active cron lines cover
Status/collector ingestion. Only counts, state flags, snapshot size/hash/top-level keys
and freshness were retained; raw container rows, routes, mount sources, config and
project data were discarded.

## Public aggregate observation

The public snapshot reported memory at 49%, disk at 60%, one-minute load at 0.34,
uptime at 8 days, disk total `40483942400` bytes and used `24148606976` bytes.
The JSON evidence carries the response hashes and authoritative observation timestamp.

These public aggregates were not used to derive the live profile. The authenticated
same-host snapshots and whitelist probes supplied the missing inputs.

## Executable resource policy

The calculator chooses and dynamically downgrades among:

| Profile | MemoryHigh MiB | MemoryMax MiB | TasksMax | Queue protect |
|---|---:|---:|---:|---:|
| constrained | 768 | 1152 | 256 | 20 |
| tiny | 1100 | 1600 | 384 | 50 |
| standard | 1800 | 2600 | 512 | 100 |

Activation requires all of the following:

- finite current/ancestor cgroup v2 memory/swap ceilings override larger host
  `/proc` values;
- `MemoryMax` fits inside available memory after an effective-scope reserve of
  the greater of 512 MiB or 10% of total memory;
- disk caps fit after a host reserve of the greater of 4096 MiB or 15% of free space;
- minimum release/workspace/cache/state/log/snapshot allocations are met;
- current guard state is not `protect`.

Protect is entered on any of: available memory below 512 MiB, memory used at least 92%,
disk or inode used at least 90%, load over the CPU-scaled ceiling, or queue depth at the
profile limit. Recovery requires all lower recovery predicates simultaneously. The writer
refuses both environment and systemd-drop-in output when activation is unsafe.

## Acceptance boundary

CB-010 proves the OVH baseline, safe constrained profile, proposed port/path
non-conflict, existing Status integration surface and bounded cgroup recovery. It does
not install CyberBoss, Node or Codex; create directories or users; change a service,
container, reverse proxy, DNS or online Status row; or prove production workload
behavior. Those remain gated by later TaskPack phases.
