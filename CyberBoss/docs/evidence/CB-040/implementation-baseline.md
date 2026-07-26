# CB-040 Implementation Baseline and Release Plan

## Decision

```text
GO_TO_PG-0
```

This decision authorizes only the next explicit Gate, `PG-0`. It does not pass
`PG-0`, start `P1.1 / CB-100`, activate a real provider, deploy a release, or
authorize a push/PR/tag. All later tasks and `PG-0`–`PG-5` remain
`not_started`.

## Claim boundary

- Phase: `P0.5`
- Task: `CB-040`
- Frozen input commit:
  `539a15e0cbebce6b6dd016316721085576dba0d6`
- Repository: `LinzeColin/MetaDatabase`
- Project subtree: `CyberBoss/`
- Local branch: `codex/cyberboss-prestage0`
- Remote publication: none permitted in this phase
- Real external mutation: none
- Credential values read or persisted: none
- Implementation status: plan frozen; `CB-100` and all later implementation
  remain `not_started`

The local baseline commit cannot safely contain its own Git SHA. P0.5 therefore
uses two local commits: the first freezes this baseline; the second records and
validates that already-existing SHA in `baseline-commit.json`, updates the
Stage 0 task state, and closes the phase. Neither commit is pushed.

## Authority and conflict resolution

The authority order is:

1. `machine/facts/owner_decisions.json`;
2. `machine/source-lock.json`;
3. `implementation-kit/config/identity-scope.policy.json`;
4. `implementation-kit/config/credential-slots.json`;
5. Task DAG and Acceptance contract;
6. architecture/operations controls;
7. validated implementation-kit configuration.

One resolvable class of conflict was found: stale Feature Flag aliases in four
product documents. They were normalized to the exact runtime names already
enforced by `cyberboss.env.example` and `validate_config.js`; defaults and
scope did not change. The complete errata record and all zero-conflict checks
are in `canonical-conflict-scan.json`.

No unresolved repository, path, domain, service, port, data-authority,
license, upstream-relationship, Mac connector, wait/soak or scope-expansion
conflict remains.

## Locked identity and separation

| Boundary | Frozen value |
|---|---|
| Code repository | `LinzeColin/MetaDatabase` |
| Project path | `CyberBoss/` |
| Workspace alias/root | `cyberboss` / `/srv/cyberboss-workspaces/cyberboss` |
| Write scope | `CyberBoss/**` |
| New repository | forbidden |
| Canonical data | `LinzeColin/Private-Database/main/Private-MetaDatabase/CyberBoss` |
| Data transport | `private_db_client.py`; `ingest/get/list/verify`; no clone |
| Host | authorized OVH primary host, pseudonym `7865f743d174` |
| Domain | `cyberboss.linzezhang.com` |
| Runtime | Codex `0.146.0-alpha.3.1`, OVH-local loopback only |
| Runtime endpoint | `ws://127.0.0.1:8765` |
| HTTP/status listener | `127.0.0.1:8780` |
| Primary service | `cyberboss-cloud.service` |
| App/state/workspace roots | `/opt/cyberboss-cloud`; `/var/lib/cyberboss`; `/srv/cyberboss-workspaces` |
| R2 | `cyberboss-cold/ovh-singapore-vps-1/`, private |
| OCI | `ap-sydney-1`, bucket slot, `cyberboss-cold-backup/ovh-singapore-vps-1/`, private |

The repository keeps historical source identity and fixed-SHA provenance only.
No upstream remote, submodule, Git URL runtime dependency, automatic sync,
runtime fetch or periodic rebase is allowed. A future source update requires
an Owner Change Event.

## License baseline

The `CyberBoss/` subtree remains `AGPL-3.0-only` with Corresponding Source
obligations. The locked `whereabouts-mcp` source remains under the strict
compliance expression:

```text
GPL-3.0-only AND AGPL-3.0-only
```

Its original source, declared license, license file and conflict record are
retained. `upstream_clarification_received=false`; this project must not claim
that upstream clarified the conflict.

## Actual environment substitutions

The complete non-secret, machine-readable set is
`environment-substitutions.json`. Secret values are deliberately absent. Only
the 15 root-protected file/slot references and four exact-scope attestation
paths are recorded.

The live CB-010 host evidence overrides template resource defaults:

| Setting | Actual baseline |
|---|---:|
| Resource profile | `constrained` |
| `MemoryHigh` | `768M` |
| `MemoryMax` | `1152M` |
| `TasksMax` | `256` |
| Queue protect | `20` |
| Job concurrency | `1` |
| Memory reserve | `512 MiB` |
| Disk reserve | `4096 MiB` |

Ports 8765/8780 were free and all proposed CyberBoss roots were absent at the
read-only probe. Node, Codex, rclone and sqlite3 were not installed on the
target; installation remains a later TaskPack action, not a CB-040 defect.

## Exact MVP Feature Flags

These are the only current runtime Feature Flags:

| Flag | Default | Baseline state |
|---|---:|---|
| `CB_DURABLE_INBOX` | true | mandatory |
| `CB_DURABLE_OUTBOX` | true | mandatory |
| `CB_PRIVATE_DB_CANONICAL_SYNC` | true | mandatory |
| `CB_TIMELINE_WEB` | true | mandatory |
| `CB_STATUS_EXPORTER` | true | mandatory |
| `CB_R2_SNAPSHOT` | true | implementation required; real activation pending |
| `CB_OCI_BACKUP` | false | activation pending |
| `CB_CLAUDE_RUNTIME` | false | out of scope |
| `CB_FILE_ATTACHMENTS` | false | Stage 2B |
| `CB_STORE_FULL_CONTENT` | false | separate encryption/privacy authority |
| `CB_AUTONOMOUS_MUTATION` | false | no current enable path |

Timeline search is contained within `CB_TIMELINE_WEB`; multi-workspace has no
current enable flag. This prevents an undocumented alias from silently
expanding scope.

## Reuse/change implementation baseline

`implementation-plan.json` maps every remaining task `CB-100`–`CB-540` to:

- exact existing modules to reuse/preserve/extend;
- planned modules where no implementation exists yet;
- executable or planned tests;
- the exact Task DAG Acceptance set;
- the future evidence directory;
- immutable release artifacts.

Key boundaries are:

- reuse the fixed WeChat protocol, Codex adapter, shared start, Timeline kernel
  and current tests;
- add durability only at inbox/job/outbox/canonical boundaries;
- keep SQLite as reconstructable Runtime spool, never canonical data;
- keep Cloudflare/OCI operations behind plan → exact scope attestation →
  idempotent reconcile;
- use deterministic resource/self-heal predicates without an LLM;
- never add a second Timeline, Mac connector, independent repository or
  upstream link.

Planned paths are not claims that those files exist. Each later Run Contract
must select exactly one phase and prove its own diff and Acceptance evidence.

## Release and rollback plan

```text
/opt/cyberboss-cloud/releases/<commit>/  immutable candidate
/opt/cyberboss-cloud/current             active symlink
/opt/cyberboss-cloud/previous            rollback symlink
```

The release identity is the Git commit SHA. A release must have lockfile,
checksums, SBOM/Corresponding Source, additive migration result, predicate
readiness, test evidence and an explicit rollback pointer. Deployment uses
`deploy-release.sh`; rollback uses `rollback-release.sh`. `wait-ready.sh` is a
bounded predicate loop, not a fixed sleep or time-based soak.

No release is built or deployed in CB-040. Final publication remains forbidden
until every TaskPack task and `PG-0`–`PG-5` have passed.

## Traceability and no-wait

AC-068 uses a deterministic pseudo-random sample: SHA-256 of the P0.4 input
commit plus each of the 53 requirement IDs, lowest ten digests selected.
`traceability-sample.json` locates Requirement → Acceptance → Task → Test →
Evidence → Release for all ten without claiming later tests have run.

The TaskPack validators report:

```text
DAG_VALIDATION=PASS tasks=30 stages=6
TRACEABILITY_VALIDATION=PASS requirements=53 oracles=53 mapped_oracles=53 tasks=30
NO_WAIT_VALIDATION=PASS real_time_soak_nodes=0 credential_wait_nodes=0 fixed_sleep_scripts=0
TASKPACK_VALIDATION=PASS files=81 required_items=16 seven_is_minimum_not_limit=true
```

The seven core control files are a minimum architecture skeleton, not a cap on
necessary implementation, evidence, compliance or handover files.

## Activation continuation

Real target Codex, WeChat, Private-MetaDatabase, Access, DNS, R2 and OCI remain
`activation_pending`; the observed broad Cloudflare R2/D1 token remains
`hazard_blocked` for real write. Simulator results are not real activation.
`activation-continuation.json` proves that these states create zero global wait
nodes and do not block dependency-independent development.

## Explicitly out of scope

- Stage 2B: file attachments, approval persistence/recovery, active
  multi-workspace scheduling, deep Timeline expansion;
- Stage 3: multi-user, multi-node/HA, multi-runtime parity, additional channels,
  scale and commercialization;
- public Codex/SSH/shell exposure;
- full-content canonical storage without separate encryption/privacy authority;
- autonomous irreversible/broad mutation;
- real provider write without exact scope attestation;
- any push, PR, tag, release, deployment or `PG-0` execution in this phase.

## Gate rationale

CB-000–CB-030 are `passed`; all CB-040 Acceptance evidence is locally
executable; Canonical Facts now have zero unresolved conflict; external
activation is truthfully isolated; and the next dependency is the explicit
`PG-0` gate. Therefore the narrow decision is `GO_TO_PG-0`.
