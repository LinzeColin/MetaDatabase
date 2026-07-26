# CB-010 Validation Report

## Decision

`activation_pending`

All safe repository-local and public read-only work for P0.2 is complete. Real OVH
acceptance is not complete because no explicitly authorized host target was available,
and read-only preparation does not authorize live induced load. Public Status aggregates
and a local bounded container are not substituted for live host evidence.

## Verification matrix

| Check | Result | Evidence |
|---|---|---|
| Public page and snapshot read-only observation | pass | HTTP 200, response hashes and sanitized schema in `public-status-observation.json` |
| Existing `projects[]` contract | pass | 11 required fields, three page status values, 8 rows, zero CyberBoss rows |
| Resource profile calculator | pass | 7/7 Python tests, including finite-cgroup ceiling |
| Unsafe profile write refusal | pass | Test proves no output file is created |
| Clean-shell preflight contract | pass | `preflight.sh --check`; no live command or persistent host write |
| Immediate snapshot contract | pass | check mode reports exactly three snapshots with no real-time wait |
| Default Linux collector path | pass | no-network/read-only local container; 3 snapshots; 512 MiB cgroup → constrained/protect/HAZARD_BLOCKED |
| Guard → warn/protect → recover ladder | pass | seven expected transitions |
| Bounded local cgroup pressure | pass | 128 MiB memory limit, 64 PID limit, zero OOM-kill delta |
| Status adapter contract | pass | 7/7 Node tests, including hostile-field sanitization |
| Live OVH preflight | pending | no authorized target; required evidence intentionally absent |
| Live OVH bounded induced load | pending | must run only after host safety budget is known |
| Online CyberBoss Status row | out of scope | no online mutation was made |

## Acceptance accounting

- AC-067 repository-local clean-shell and runbook requirements are executable and aligned.
- AC-064 repository-local pressure ladder is executable, but real-host/cgroup proof remains
  pending.
- CB-020 and all later tasks remain `not_started`.
- PG-0 through PG-5 remain `not_started`.
- No push, PR, tag, release, OVH mutation or online Status mutation occurred.

CB-010 may become `passed` only after the same authorized OVH host supplies the redacted
three-snapshot preflight and bounded induced-load/cgroup evidence required by the Run
Contract.
