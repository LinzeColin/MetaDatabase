# CB-100 Validation Report

## Decision

`passed`

Task state: `passed`

`P1.1 / CB-100` installed the supplied lightweight host layout and systemd
walking skeleton on the same authorized OVH target proven in CB-010. The exact
local implementation commit
`b2a603e415a2045b441f31e07cf74ac451ba6240` is the immutable release ID.
Only the main `cyberboss-cloud.service` was installed; it is disabled and
inactive. No real Runtime, external provider, Private-MetaDatabase object,
public route, Git branch, PR, tag or release was created.

## Acceptance

- AC-044: `passed`
- AC-067: `passed_for_CB-100_scope`
- CB-110: `not_started`

| Check | Result |
|---|---|
| Same authorized target / strict known-host / key-only SSH | pass |
| Fresh constrained/recover/activation-safe profile | pass |
| Prestate paths, user/group, units, journal config and ports | all zero |
| Exact commit archive and inner SHA-256 manifest | pass |
| First apply | pass |
| Second apply | idempotent pass; no resource remeasurement |
| Dedicated non-root identity and exact modes | pass |
| Immutable release/current pointer/rollback prestate | pass |
| `systemd-analyze verify` and sandbox/resource/log directives | pass |
| Permission negatives | 5 denied; 2 allowlisted writes |
| Actual systemd kill/restart | 100/100 |
| Active-owner ready predicate | new PID active and lock held |
| Singleton contention | 100/100 denied; post-stop acquire 1 |
| Normalized route topology | unchanged |
| Final state | disabled/inactive; 8765=0; 8780=0 |
| Runtime/provider/data activation | zero |
| GitHub publication | none |

The target did not have `shellcheck`; no package was installed to manufacture
that check. Both scripts passed `bash -n`, five host-layout contract tests,
actual target execution and the final verifier.

## Preserved conflict record

The first acceptance harness completed and checked the 100 restart and 100
singleton markers, then failed inside a composite postcheck labelled
`final_verify`. That harness did not retain the exact failing subcheck. Every
postcheck passed when immediately split into individual read-only assertions.
The likely source was the raw `ip -j route` hash, whose records contain
volatile expiry/timing fields; this is recorded as an assessment, not a
fabricated certainty.

A second complete 100-cycle acceptance therefore used a canonical route
topology that removes only volatile timing fields. It passed restart 100/100,
singleton 100/100, unchanged topology, final verifier and safe terminal state.
Both attempts remain represented in
`systemd-acceptance.redacted.json`; the earlier failure was not erased.

## Source and license boundary

The fixed App and vendor source bundles were not modified. Original source,
licenses, Corresponding Source and the unresolved whereabouts license conflict
remain intact. Compliance remains
`GPL-3.0-only AND AGPL-3.0-only`, with
`upstream_clarification_received=false`; no upstream relationship or
clarification is claimed.

## Regression and scope

- Host-layout contract: 5/5
- Frozen App regression: 155/155
- CB-000 source/license validation: pass
- Prestage: pass
- DAG: 30 tasks / 6 stages
- Traceability: 53/53
- No-wait: zero real-time/fixed-sleep nodes
- TaskPack: 82 files
- Secret scan: zero known/pattern/P0/P1 findings; no values emitted

Only CB-100 changed state. `CB-110` and every later task remain
`not_started`; PG-1 through PG-5 remain `not_started`.
