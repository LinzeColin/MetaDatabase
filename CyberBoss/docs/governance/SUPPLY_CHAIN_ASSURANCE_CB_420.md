# CyberBoss Security, Supply-chain, Privacy and AGPL Assurance — CB-420

## Scope

- Owner-locked product: `v0.0.0.5`
- Evaluation: local, deterministic and read-only
- Runtime model calls: `0`
- Control-plane/operations LLM calls: `0 / 0`
- macOS launchd dependency: `false`
- Cloudflare Web Analytics and release distribution: `activation_pending`

This document is a local assurance result, not a claim that Cloudflare
Analytics is enabled, that source has been distributed to users, or that a
real provider/release operation has occurred.

## Security report

The `canonical-security-assurance` evaluator traverses only the declared source
and machine paths, skips `node_modules` and transient directories, rejects
symlinks and local `.env` files, and never prints a matched value. Its
high-confidence patterns cover private-key blocks, GitHub tokens, OpenAI-style
keys and long Bearer credentials.

The closure requires all of the following:

| Control | Required local result |
|---|---|
| High-confidence secret hits | 0 |
| Local environment files | 0 |
| Unaccepted P0/P1 findings | 0 |
| Control-plane / operations LLM calls | 0 / 0 |
| macOS launchd dependency | false |
| Network or provider operations | 0 |

Any nonzero result fails closed before a release can be considered.

## Canonical SBOM

The full SBOM remains the existing, immutable
`docs/evidence/CB-000/dependency-license-inventory.json` rather than a copied
or regenerated parallel inventory. The evaluator proves:

- lockfile version is 3 and the inventory has exactly 129 components;
- every component has name, version, concluded license and lock path;
- unresolved-license count is zero;
- the one `whereabouts-mcp` conflict remains explicitly
  `GPL-3.0-only AND AGPL-3.0-only`, not silently normalized or waived;
- the output binds inventory SHA-256, `app/package-lock.json` SHA-256 and a
  deterministic component digest.

## Corresponding Source package

The repository `CyberBoss` source tree is the Corresponding Source package.
The evaluator emits a relative-path, per-file SHA-256 manifest over the
authoritative app, two vendor bundles, root license/notices and frozen source
governance inputs. It contains no absolute path, credential or copied archive.
This avoids creating a second source repository or a competing source/SBOM
truth while retaining a reproducible package boundary for a future immutable
release.

The package is complete only when all three locked bundles remain present:

| Source | Compliance expression | Original source/license |
|---|---|---|
| cyberboss | AGPL-3.0-only | preserved |
| timeline-for-agent | AGPL-3.0-only | preserved |
| whereabouts-mcp | GPL-3.0-only AND AGPL-3.0-only | preserved, conflict unresolved |

The source-distribution state is `activation_pending`. A future distribution
receipt must bind the exact release Subject; this local manifest does not claim
that distribution has happened.

## Access and analytics privacy closure

CB-420 invokes the existing CB-320 policy contract rather than inventing a new
Access or analytics system:

- Codex remains `ws://127.0.0.1:8765` only; external `8765` is unreachable.
- Anonymous and direct-origin bypass are denied by the existing Access
  contract.
- Only aggregate page-view and performance fixtures are admitted.
- Query/fragment, private content, prompt/result, Access identity, thread/job
  identifiers and a second analytics database are rejected.
- The provider is named `Cloudflare Web Analytics` but remains
  `activation_pending` until an authorized external activation receipt exists.

## Release posture

This gate passes only the local deterministic security/supply-chain/privacy/
license closure. It does not activate any provider, service, runtime or source
distribution. A high-confidence secret, incomplete corresponding source,
license-closure regression, external-8765 regression or analytics privacy
regression keeps the release disabled and stops the candidate.
