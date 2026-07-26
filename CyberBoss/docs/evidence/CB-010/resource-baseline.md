# CB-010 Resource Baseline

## Result

Repository-local resource policy, clean-shell preflight and bounded pressure fixture are
implemented and executable. The public Status surface was observed read-only, but it does
not expose enough information to establish the OVH host baseline. No authorized OVH target
was discoverable, so the live profile is **not selected** and CB-010 remains
`activation_pending`.

## Evidence classification

| Evidence | Result | What it proves | What it does not prove |
|---|---|---|---|
| `public-status-observation.json` | observed | Current public Status schema and aggregate host indicators | total/available RAM, swap, inode, listeners, units, containers, path conflicts |
| `preflight.local-linux-container.json` | pass | Default Linux collector executes three snapshots with no network and fails closed against a finite 512 MiB cgroup | OVH resources, listeners, services or path conflicts |
| `resource-pressure.local-container.json` | pass | Bounded fixture, cgroup limit visibility, guard ladder and zero observed OOM kill in a local container | OVH headroom, existing-service isolation or production cgroup behaviour |
| `test_resource_profile.py` | 7/7 pass | Profile selection, cgroup ceiling, pressure downgrade, guard transitions, safe/unsafe writes and read-only check mode | Which profile is safe on the real host |
| `preflight.sh --check` | pass | Three-immediate-snapshot and clean-shell contract without live reads or persistent host writes | Live host measurements |

The local container evidence explicitly sets `claimed_as_live_host_evidence=false`.
The two required live evidence files are intentionally absent.

The default Linux-path fixture uses an already-local pinned image with
`--pull=never`, network disabled, read-only root, all capabilities dropped and
no-new-privileges. It exposed and now guards against a real false-selection case:
when `/proc/meminfo` reports host memory larger than a finite cgroup,
the most restrictive current/ancestor `memory.max/current` and
`memory.swap.max/current` values define the effective ceiling and headroom.
The 512 MiB fixture therefore selects `constrained` but blocks activation instead
of incorrectly selecting `standard`.

## Authorized-target discovery

At `2026-07-26T06:53:05.277337Z`, discovery was limited to SSH host alias names and
OVH/CyberBoss environment-variable names:

- one configured alias was present, with no OVH/CyberBoss match;
- no matching environment-variable name was present;
- no credential value or key content was read;
- no IP, DNS name or host identity was guessed.

Running host commands without an unambiguous authorized target would violate the Run
Contract stop condition.

The current Owner instruction authorizes read-only preparation only. That does not imply
permission to allocate bounded live-host pressure or write its temporary disk fixture, so
no such permission is claimed.

## Public aggregate observation

The public snapshot reported memory at 49%, disk at 60%, one-minute load at 0.34,
uptime at 8 days, disk total `40483942400` bytes and used `24148606976` bytes.
The JSON evidence carries the response hashes and authoritative observation timestamp.

These aggregates cannot safely derive a profile: they omit total and available memory,
swap, disk free-space policy reserve, inode utilization, CPU count, queue depth, listeners,
process/service/container inventory, reverse-proxy configuration and Status ingestion
location.

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

## Live acceptance still required

On the same explicitly authorized OVH host, CB-010 still requires:

1. three immediate redacted snapshots covering memory, swap, load, disk, inode and queue;
2. redacted listener, process, systemd, container, reverse-proxy, Status ingestion and
   canonical-path inventory;
3. profile and cap calculation from those measurements;
4. one bounded induced-load/cgroup snapshot with no OOM kill and successful recovery.

Items 1–3 require an authorized SSH alias. Item 4 additionally requires explicit bounded
live-pressure permission after the baseline proves the cap safe.

Until those exist, ports 8765/8780 and canonical paths remain proposals rather than
conflict-verified choices, and no real runtime activation is permitted.
