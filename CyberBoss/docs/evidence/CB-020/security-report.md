# CB-020 Security Report

- Status: pre-final validation complete
- Scope: repository identity, workspace write boundary, data-client boundary,
  provider control/data planes, credential slots, Access policy and release
  compliance regression
- External writes: 0

## Findings

| Severity | Open findings |
|---|---:|
| P0 | 0 |
| P1 | 0 |

## Controls verified

- another repository, project path, workspace alias or root write is rejected;
- Private-Database clone/put/delete, another area/domain/repo/branch is rejected;
- R2/OCI another provider/bucket/prefix and path traversal are rejected;
- broad or unrelated provider write attestations are rejected;
- missing provider slots return `activation_pending`, never a wait node;
- Access denies anonymous and unauthorized fixtures and rejects Bypass,
  Everyone and any-valid-service-token rules;
- provider simulator reconciliation is idempotent and DNS follows Access;
- OCI mock objects are immutable and prefix locked;
- seven protected known-secret values can be loaded for equality scanning
  without emitting them; repository matches remain zero;
- the CB-000 Corresponding Source, notices, dependency versions and strict
  `GPL-3.0-only AND AGPL-3.0-only` conflict record remain intact.

The exact final scanner counters are in `secret-scan.json`. No simulator result
is classified as real external activation.
