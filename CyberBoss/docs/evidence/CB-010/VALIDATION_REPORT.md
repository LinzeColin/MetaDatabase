# CB-010 Validation Report

## Decision

`passed`

Repository-local, public read-only and authorized OVH live acceptance for P0.2 are
complete. The target was resolved from protected local deployment records under the
Owner's explicit instruction, authenticated with strict known-host/key-only SSH, and
represented only by pseudonymous hashes in committed evidence.

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
| Live OVH preflight | pass | three same-host immediate snapshots; constrained/recover/safe; proposed ports and paths free |
| Live Status/reverse-proxy ingestion probe | pass | host-direct compose, collector/data/web, mounts, fresh snapshot, cron and Traefik counts |
| Live OVH bounded induced load | pass | existing image, no pull/network, 128 MiB cgroup, 16 MiB/8 MiB/100, zero OOM-kill delta |
| Online CyberBoss Status row | out of scope | no online mutation was made |

## Acceptance accounting

- AC-067 clean-shell, live collector and runbook requirements are executable and aligned.
- AC-064 guard ladder and authorized-host finite-cgroup proof both pass.
- CB-020 and all later tasks remain `not_started`.
- PG-0 through PG-5 remain `not_started`.
- No push, PR, tag, release, persistent OVH mutation or online Status mutation occurred.

The collector's `PASS_WITH_ACTIVATION_PENDING` line refers only to later Runtime
dependencies (Node, Codex, rclone and sqlite3) not yet installed. Core collection,
capacity, reserve, port/path and pressure acceptance passed; runtime activation remains
outside CB-010.

## Final regression

- `validate_cb010.py`: PASS, `task_state=passed`, `live_ovh=true`
- `validate_cb000.py`: PASS
- `validate_prestage0.py`: PASS, 6 stages / 30 tasks / 53 oracles / 53 requirements
- Resource profile: 7/7 PASS
- Status adapter contract: 7/7 PASS
- TaskPack: PASS, 65 files / 16 required items
- DAG: PASS, 30 tasks / 6 stages
- Traceability: PASS, 53 requirements / 53 mapped oracles
- No-wait: PASS, zero real-time soak, credential-wait and fixed-sleep nodes
- Config: PASS, one workspace
- Both SHA-256 manifests and `git diff --check`: PASS
