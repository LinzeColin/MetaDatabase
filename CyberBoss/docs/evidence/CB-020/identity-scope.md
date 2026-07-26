# CB-020 Identity, Data and Provider Scope Evidence

- Observed: 2026-07-26
- Task: `P0.3 / CB-020`
- Evidence mode: repository checks, protected-record metadata, read-only provider
  API probes and deterministic local simulators
- External mutation: none

## Locked identity

| Boundary | Required | Verified |
|---|---|---|
| Git remote | `git@github.com:LinzeColin/MetaDatabase.git` | yes |
| Repository | `LinzeColin/MetaDatabase` | yes |
| Project path | `CyberBoss/` | yes |
| Workspace alias | `cyberboss` | yes |
| Workspace write scope | `CyberBoss/**` | yes |
| New/fork repository | forbidden | none created |
| Current branch | `codex/cyberboss-prestage0` | local only |
| GitHub CyberBoss branch/PR/tag | forbidden before all TaskPack/PG gates | none |

The machine-readable source is
`implementation-kit/config/identity-scope.policy.json`. Both
`scope_policy.py` and `validate_config.js` reject another repository, project
subpath, alias or write path. Root integration remains disabled until a later
Run Contract explicitly authorizes a named root file.

## Canonical data boundary

CyberBoss may use only:

```text
LinzeColin/Private-Database
branch=main
area=Private-MetaDatabase
domain=CyberBoss
operations=ingest|get|list|verify
transport=private_db_client.py
clone=false
```

The shared client was found at the governance-defined KMOS location and
inspected read-only:

```text
basename=private_db_client.py
size_bytes=10818
sha256=8a26302c98a470e75122fbf01ff1d1a23381ccf5db5f26df9ed5f9e59e5c9ffa
declared_repo=LinzeColin/Private-Database
declared_branch=main
Private-MetaDatabase_supported=true
```

No `Private-Database` clone exists under `GithubProject`. The shared client was
not copied or modified. `private_db_client_safe.py` validates its identity and
source contract, strips CyberBoss down to the allowed four operations and
requires the exact area/domain before it can execute. `put`, `delete`, `clone`,
another area, domain, repository or branch fail closed. No real data operation
was made in this Run.

## Provider and credential boundary

Repository files contain only canonical `/etc/cyberboss/credentials/` slot
paths. They contain no account IDs, zone IDs, owner identity, service-token
identifier, API token, access key, PAR URL, OCI OCID or private key. Exact slot
inventory and required modes are in
`implementation-kit/config/credential-slots.json`.

Read-only local discovery found protected Cloudflare and OCI credential
records with owner-only modes. The values were never printed or persisted.
Capability probes are summarized in
`provider-capability-observation.json`.

Real provider writes require an external scope-attestation file:

- Access: exactly `Access: Apps and Policies Write` on the one existing account,
  with no unrelated write permission;
- DNS: exactly `DNS Write` for `linzezhang.com`;
- R2 control plane: exactly `Workers R2 Storage Write`, without Access/DNS
  write;
- OCI: only `OBJECT_INSPECT`, `OBJECT_READ` and `OBJECT_CREATE` for one
  pre-existing bucket and
  `cyberboss-cold-backup/ovh-singapore-vps-1/`.

Broad account write, extra write permissions, another bucket/prefix or a
missing attestation returns `hazard_blocked`/`activation_pending`. This Run did
not fabricate an attestation from successful reads.

## Cloudflare activation order

The declarative adapter is idempotent and orders resources:

1. reconcile the self-hosted Access application;
2. reconcile explicit owner and specific status service-token policies;
3. ensure the private R2 bucket control-plane object;
4. retain Web Analytics as an explicit dashboard activation item with a
   no-private-fields contract;
5. create or reconcile the proxied DNS record only after Access.

Cloudflare Access denies users who do not match an explicit Allow policy by
default. The fixture forbids `Bypass`, `Everyone` and `any valid service token`;
Cloudflare documents that Bypass disables Access enforcement and that an Allow
policy including Everyone makes an application public. See the official
[Access policy documentation](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/)
and [Access application API](https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/applications/).
The required API permissions and endpoints are taken from Cloudflare's
[Access policy](https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/policies/methods/create/),
[DNS record](https://developers.cloudflare.com/api/resources/dns/subresources/records/methods/create/)
and [R2 bucket](https://developers.cloudflare.com/api/resources/r2/subresources/buckets/methods/create/)
references.

Cloudflare's UI names the exact service-token action `Service Auth`; the
current API schema serializes that action as `decision=non_identity`. The
adapter permits that API value only with one explicit
`service_token.token_id`; it never permits the broader
`any_valid_service_token` selector.

Web Analytics for a proxied hostname currently uses dashboard automatic setup,
so the adapter records this as a bounded manual control-plane activation
instead of inventing an API. See Cloudflare's
[Web Analytics setup](https://developers.cloudflare.com/web-analytics/get-started/).

## OCI activation boundary

The local OCI Python SDK authenticated read-only in `ap-sydney-1`, resolved the
Object Storage namespace and listed one existing bucket. No bucket/object was
created, read or changed. The task-pack string
`cyberboss-cold-backup/ovh-singapore-vps-1/` is treated as an object prefix
inside a separately injected pre-existing bucket, not as an assumed bucket
name.

The adapter requires the runtime bucket slot to equal the requested bucket and
locks every object key to the canonical prefix. Its mock proves immutable,
idempotent put/get/list behavior; real SDK execution additionally requires an
exact scope attestation and an explicit `--execute-real` flag. Oracle documents
that object listing accepts a prefix and that the object name is everything
after `/o/`; OCI IAM conditions can restrict both bucket and object name.
See [listing objects](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/managingobjects_topic-To_list_objects_in_a_bucket.htm)
and [common Object Storage policies](https://docs.oracle.com/en-us/iaas/Content/Identity/policiescommon/commonpolicies.htm).

## Access fixture evidence

- `access-deny.fixture.png`: anonymous/unauthorized request → `DENY`;
- `access-allow.fixture.png`: exact approved fixture identity → `ALLOW`;
- `implementation-kit/tests/access-policy-contract.test.js`: eight executable
  allow/deny and hostile-policy assertions.

The screenshots are deterministic local fixture evidence. They contain
`.invalid` identities only and explicitly do **not** claim real Cloudflare
activation.

## Acceptance mapping

| Acceptance | Evidence |
|---|---|
| AC-043 | bounded secret/DLP scanner, hostile fixture test, zero final hits |
| AC-056 | missing real slots return `activation_pending`; all mock/config/security tests continue; no wait node |
| AC-065 | repository scope, port/secret/workspace policy suite; P0/P1 findings reported separately |
| AC-069 | CB-000 Corresponding Source, original licenses, notices, dependency versions and unresolved-conflict record revalidated without modification |

Simulator success is never reported as real provider success. Provider writes
remain `activation_pending`; this is local task completion under the TaskPack's
missing-credential rule, not an external activation claim.
