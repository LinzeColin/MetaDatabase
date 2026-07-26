# CB-000 License and Corresponding Source Record

## Compliance posture

`CyberBoss/` is distributed under AGPL-3.0-only. Original source, license text,
provenance, modifications, dependency versions and integrity locks are retained.

| Component | Declared indicator | License-file conclusion | Compliance treatment |
|---|---|---|---|
| CyberBoss source | `AGPL-3.0-only` | `AGPL-3.0-only` | AGPL-3.0-only |
| timeline-for-agent | `AGPL-3.0-only` | `AGPL-3.0-only` | AGPL-3.0-only |
| whereabouts-mcp | `AGPL-3.0-only` | `GPL-3.0-only` | `GPL-3.0-only AND AGPL-3.0-only` |
| qrcode-terminal 0.12.0 | legacy `Apache 2.0` metadata | Apache-2.0 plus bundled MIT QRCode notice | `Apache-2.0 AND MIT` |

## Whereabouts conflict decision

The exact `whereabouts-mcp` commit declares `AGPL-3.0-only` in `package.json`
but contains the GPLv3 license text in `LICENSE`. No upstream clarification was
requested or received, and this project must never claim otherwise.

Owner decision: preserve both indicators and the full original source, meet the
strictest combined GPLv3 and AGPLv3 obligations, and record the conflict in every
machine/legal evidence surface. This is a conservative project compliance
decision, not a statement that the historical author granted or clarified a
specific dual-license expression.

## Dependency closure

`dependency-license-inventory.json` contains all 129 lockfile package entries
including the root package. It records name, version, resolved source, integrity,
declared license, concluded compliance license and evidence. Unresolved license
count is zero.

`qrcode-terminal` uses deprecated `licenses` metadata that npm's v3 lock does not
copy into `license`; its exact registry package includes the Apache-2.0 text and
an embedded MIT notice. That original file is preserved at
`licenses/qrcode-terminal-0.12.0-LICENSE`, SHA-256
`b3c7a2fadb2515b8106eae58439a4b9c0581a4eaa88d6a265701f8d4dd7dadb8`.

## Corresponding Source locations

- CyberBoss modified source: `CyberBoss/app/`
- Timeline source: `CyberBoss/vendor/timeline-for-agent/`
- Whereabouts source: `CyberBoss/vendor/whereabouts-mcp/`
- Registry dependency identities/integrity: `CyberBoss/app/package-lock.json`
- Full license inventory: this directory's
  `dependency-license-inventory.json`
- Original and current manifests: this directory's `manifests/`
- Modifications: `baseline-source.md`, `REUSE_CHANGE_MAP.md`,
  `CyberBoss/CHANGELOG.md`
- Provenance and notices: `CyberBoss/UPSTREAM_PROVENANCE.md`,
  `CyberBoss/THIRD_PARTY_NOTICES.md`

No upstream remote, submodule, branch dependency, auto-sync or runtime source
fetch is required to provide or rebuild these sources.
