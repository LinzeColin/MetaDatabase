# CB-110 Validation Report

- Run: `P1.2 / CB-110`
- Task state: `passed`
- CB-120: `not_started`
- Implementation/release:
  `3cd8eee4f6b7c0a78f7b6fde90dae0f4ff1392fc`
- Target: same pseudonymous OVH asset as CB-010/CB-100
- Codex auth: `activation_pending`
- Remote publication: `none`

## Result

The exact implementation commit was transferred through a `0700` ephemeral
staging directory and its archive hash was verified on target. The target then
performed two applies and an independent verify. Both applies resolved to the
same immutable project-local Node.js `24.18.0`, Codex CLI
`0.146.0-alpha.3.1`, protected Codex home and commit-bound version manifest.
The second apply was idempotent. No global Node/Codex path, CB-100 current
release, systemd unit or public route changed.

Node `node:sqlite` passed an in-memory create/insert/select check. A transient
process running as `cyberboss` returned `/readyz` HTTP 200 and completed Codex
App Server `initialize` plus `initialized`. While active, the only 8765
listener was `127.0.0.1:8765`; an external TCP attempt to the target public
address was not reachable. After acceptance, App Server processes, 8765/8780
listeners and staging artifacts were all zero, and the main unit remained
disabled/inactive.

The metadata-only auth probe found the exact CLI but no `auth.json`; login
classification is `not_authenticated`, so the real target adapter remains
`activation_pending`. No credential value or content was read. Device auth was
not executed, and no public callback was needed.

Claude Code was deliberately not installed because it is optional and would
add unneeded resource/supply-chain surface. The deployed defaults leave both
gates false. Target dispatch tests rejected false/false, true/false and
false/true; true/true only passed the gate into a `true` fixture and did not
start the adapter. Claude binary, credential and business Runtime remained
absent.

## Acceptance

- AC-011: `passed`
- AC-017: `passed`
- AC-065: `passed_for_CB-110_scope`
- P0 findings: `0`
- P1 findings: `0`
- Provider/Private-MetaDatabase writes: `0`
- Auth/secret content reads: `0`

## Preserved execution conflicts

The first transient acceptance orchestration failed to release its hold marker
inside 60 seconds. The probe failed with
`external_scan_release_marker_timeout` and cleaned up; no runtime pass was
claimed. The next run passed the Runtime and external-scan Oracles, but the
local export failed because the `ubuntu` transfer identity could not traverse
the deliberately `0700 cyberboss` staging parent. A final complete rerun kept
that protection, exported through a separate owner-only temporary file, and
passed all Oracles and cleanup. These were harness/export defects, not erased
from the record.

## Compliance boundary

Fixed App/vendor source, original license files, Corresponding Source and all
CB-000–CB-100/PG-0 historical evidence are unchanged. The unresolved
whereabouts metadata/file conflict continues under the strict expression
`GPL-3.0-only AND AGPL-3.0-only`; original source, both license indicators and
the conflict record remain preserved, with
`upstream_clarification_received=false`.

Only CB-110 changed state. CB-120 and every later task, plus PG-1–PG-5, remain
`not_started`. No branch, PR, tag, release or push exists remotely.
