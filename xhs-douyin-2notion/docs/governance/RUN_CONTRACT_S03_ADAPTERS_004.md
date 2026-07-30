# Run Contract — `RUN-X2N-S03-A004`

## Identity and authorization

- Task: `TSK.x2n.adapters.004`
- Phase: `PH.X2N.3.4`
- Stage: `STG.X2N.3`
- Task base: `0939d78303f5e96ddedf9c8ef8a01a8dce03574a`
- Branch: `codex/xhs-douyin-2notion-v0001-s03-adapters004`
- Run kind: one DAG Task only

The Task base is the local final commit of `TSK.x2n.adapters.003`. This Run
first fixes that predecessor verifier to the final commit, then reads historical
facts from Git blobs. It does not absorb unrelated `main` or other worktree
changes. Stage 3 remains local until all Adapter Tasks, independent Stage Review,
fixes, re-acceptance and `G3` complete.

## Objective and bounded scope

Expose a stable `DouyinAdapter` boundary around the audited
`jiji262/douyin-downloader` pin without making the upstream program, its storage,
or its output a truth source:

1. pin repository commit `ef3ad18c2b50e38e534f72aabe2b3fbb0b3fadd7`,
   tree `ff7774b618f269fcdc750e17dc63612f159b6b46`, declared version
   `2.0.0`, MIT identity and x2n sidecar protocol/schema versions;
2. require an exact health handshake before every bounded action, including
   commit/tree/version/license, capabilities, persistence-off declarations,
   exact integration-lock digest, transitive-license report digest and SBOM digest;
3. provide no-shell subprocess and loopback-only REST transports with bounded
   timeout/response size, minimal environment, one request per explicit Owner
   action, and stable safe error normalization;
4. accept only a strict, sanitized likes/favorites response of at most 20 items,
   reject unknown/missing fields recursively, derive canonical Douyin page URLs
   locally, and reject URLs, paths, credentials, raw metadata/media and upstream
   primary keys before any Canonical transaction;
5. map normalized items atomically to SQLite Content, independent `liked` or
   `favorited` UserRelation, `selected_collection` SourceObservation and a
   versioned Durable Checkpoint; unknown/error/timeout/partial output never
   advances, removes or completes;
6. provide fixed 20-like and 20-favorite non-executing Canary plans, public
   synthetic contract fixtures, deletion-protection cases and a shadow-upgrade
   comparator which can block a changed candidate but cannot promote it.

The upstream CLI and its raw REST server are not the sidecar protocol. At the
audited pin they do not attest commit/tree/schema and may read or write Cookie,
database, JSON, manifest, paths and media. This Run therefore does not vendor,
install, import or execute upstream code and adds no upstream Runtime dependency.
An eventual Owner-managed private sidecar build remains disabled until its exact
executable digest, resolved dependency lock, transitive-license report and SBOM
are present under the private x2n Runtime root and match the integration manifest.

This Run may change the Douyin Companion wrapper/Adapter, non-executing CLI plans,
public synthetic fixtures, pin/policy facts, Task verifier, evidence and required
project-state documentation. It must not enter `TSK.x2n.adapters.006` or
`TSK.x2n.adapters.005`, wire a production Side Panel action, alter Native Messaging
v1, add Chrome permissions, access an Owner Profile/Cookie/credential, run a real
platform request, automatically scroll/paginate/retry/login, mutate account state,
persist an upstream URL/path/primary key/raw object/media, reconcile missing
relations, delete data, call Notion/models, upload GitHub, or access shared
authentication material.

## Evidence-backed policy boundary

The reviewed current Douyin Open Platform permission matrix and authorized-video
API document OAuth/scoped access and the authorized user's own posted videos. The
review found no explicit personal liked-video list or favorite-folder/list scope.
This is a bounded research result, not a claim that such a capability cannot exist.
`douyin_likes` and `douyin_favorites` therefore remain `UNKNOWN_DISABLED`; all
Owner Alpha/private-gold and real-account cases are `NOT_RUN`.

Anonymous fixed-source audit confirmed the registered pin and MIT notice. A
2026-07-23 shadow observation found upstream `main` four commits ahead at
`2e373df6fe474368804909f337fd26ee5139ce5d`. The candidate is only negative shadow
input: A004 neither updates the approved pin nor imports candidate behavior.

## Acceptance

- `ACC.x2n.dy.001`: 20 public synthetic favorites across two synthetic collections
  normalize into exactly 20 Content and 20 `favorited` Relations. Upstream
  collection identity is mapped to a sidecar-issued stable x2n collection key;
  upstream paths/primary keys in Canonical are `0`. ENV-OWNER-ALPHA is `NOT_RUN`,
  so the result is `PASS_CI_SYNTH_SCOPED`, not full Owner acceptance.
- `ACC.x2n.dy.002`: 20 public synthetic likes normalize into exactly 20 Content and
  20 `liked` Relations. ENV-OWNER-ALPHA is `NOT_RUN`; result is
  `PASS_CI_SYNTH_SCOPED`.
- `ACC.x2n.dy.003`: normal subprocess and loopback REST, missing field, unknown
  field, recursive forbidden field, error exit, normalized upstream error,
  timeout, oversize, invalid JSON, Schema drift, version/commit/tree/license/lock
  mismatch and shell-injection inputs are covered. Mismatch is blocked before a
  Canonical write; NOTICE and exact pin manifest are verified.
- `ACC.x2n.batch.001`: auth-expired, transport error, schema change, empty unknown
  and partial output generate removed `0`; this Task creates no
  `tombstone_candidate`, physical delete or Content delete. Two-complete-scan
  reconciliation remains owned by `TSK.x2n.adapters.005`.

The synthetic sidecar process and loopback HTTP server are contract fakes. They
make platform calls `0` and are not evidence that upstream or the real account ran.
Owner Profile login, real page, real account, private sidecar install and Canary are
`NOT_RUN`; `G3=NOT_RUN` and remote upload remains forbidden.

## Verification commands

```bash
.venv/bin/python -B scripts/run_adapters_004_acceptance.py
.venv/bin/python -B scripts/verify_adapters_004.py \
  --verify-worktree --allow-external-main-dirty
.venv/bin/python -B scripts/ci/run_lane.py --lane full --repetitions 2 \
  --reports-dir build/s03-adapters004-final
.venv/bin/python -B scripts/verify_adapters_004.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/s03-adapters004-final/software-lane.json --write-evidence
.venv/bin/python -B scripts/verify_adapters_004.py \
  --verify-worktree --allow-external-main-dirty --skip-external \
  --lane-report build/s03-adapters004-final/software-lane.json --require-evidence
```

Any real upstream/platform call, direct raw upstream CLI/REST use, missing exact
lock/license/SBOM attestation, unknown Schema acceptance, shell execution, automatic
pagination, account mutation, URL/path/credential/raw-media leakage, silent item
loss, relation overwrite/removal, physical/Content deletion, Owner execution claim,
private Runtime data in public output, task overlap or premature upload fails this
Run.

## Risk, rollback and stop conditions

- Risk: upstream release/schema drift, missing reproducible lock, error ambiguity,
  raw metadata/path leakage, favorite-mode/folder limitations and false completion.
- Rollback: keep both Douyin flags disabled, restore the approved pin/manifest,
  revert this local Task commit and retain current-page capture plus all existing
  Canonical data.
- Stop: MIT becomes incompatible; an exact lock, transitive-license report or SBOM
  cannot be produced for a future private sidecar; the wrapper cannot prevent
  schema/URL/path/credential/raw-media leakage; a route needs control bypass,
  real-account execution without authorization, another DAG Task, or remote upload.
