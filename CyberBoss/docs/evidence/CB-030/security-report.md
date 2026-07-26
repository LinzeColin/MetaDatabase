# CB-030 Security Report

- Status: `PASS`
- Scope: channel/runtime simulators, authentication-state metadata probes,
  activation commands, repository secret/DLP scan and fixed-source regression
- Real provider or target mutation: 0

## Findings

| Severity | Open findings |
|---|---:|
| P0 | 0 |
| P1 | 0 |

## Controls verified

- both simulators fail closed unless the listener is loopback-only;
- simulator output and the screenshot are explicitly labelled synthetic and
  cannot move a real adapter to `verified`;
- Codex auth and WeChat account/session contents were never read, copied,
  hashed, backed up or persisted in evidence;
- local and authorized-OVH probes emit only presence, ownership, mode,
  version, count and classification metadata;
- SSH used key-only batch authentication with strict host-key checking, and
  the OVH probe performed no persistent remote write;
- missing target Codex/WeChat state returns `activation_pending`; it does not
  become a global wait node;
- the activation sheet protects auth material with owner-only directories and
  files, separates adapter switching and records explicit re-login/revocation;
- the final repository scan loads seven protected known-secret values for
  equality checks without emitting values or hit paths;
- the scanner's token/JWT/Bearer/WeChat word-boundary expressions were
  corrected after static review exposed literal-backslash false negatives;
  seven hostile, runtime-constructed fixtures now prove every pattern family;
- known-secret hits, forbidden-pattern hits and unreadable files are all zero;
- the fixed upstream source, original license/notices and unresolved
  `GPL-3.0-only AND AGPL-3.0-only` record remain unchanged, with no claim of
  upstream clarification.

The exact scanner counters are in `secret-scan.json`. Real AC-001 and AC-010
remain `activation_pending`; simulator results are non-activation evidence
only.
