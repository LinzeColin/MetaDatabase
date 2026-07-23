# MooMooAU RMD-05 final independent rereview request (attempt 18)

## Immutable target

- Repository checkout: `/private/tmp/moomooau-rmd05-candidate18.erK4yj/repository`
- Project path: `LinzeDatabase/MooMooAU`
- Baseline commit: `2b8625a83e69093b9dce989f4eb964556e1b5fa2`
- Review candidate anchor: `2ba0d34cee89672297d7c575205c3d4bf854461b`
- Execution candidate parent: `dc8f7be36f45d3368cb2a6931fdb6cdcdf1fefc1`
- Shared candidate tree: `673132302ed909d8c02e856fdb19887b20c3f447`
- Candidate-bound receipt: `/private/tmp/moomooau-rmd05-candidate18.erK4yj/execution-receipt17.json`
- Receipt SHA-256: `6e8fd35c8d5d3dac2d1320713d3b17d32fa9c285e2bc77146565fef4e44beef0`
- Scope: `LOCAL_SYNTHETIC_ONLY`

The anchor has exactly one parent, that parent is the execution candidate, and the anchor and parent
resolve to the same tree. Its commit message contains exactly one recognized
`MooMooAU-Execution-Candidate` trailer and exactly one recognized
`MooMooAU-Execution-Receipt-SHA256` trailer. Treat the anchor, parent, tree, this request and receipt
as immutable review inputs. The request and receipt intentionally remain outside the candidate tree
until post-review materialization.

## Preserved attempt-17 result and why it is superseded

Attempt 17 produced two independent PASS replies, but it is not accepted as final closure because
the subsequent clean final-output verification exposed a new blocking defect. The exact artifacts
are preserved byte-for-byte in the candidate:

- Sol: `machine/stages/S6/reviews/rmd05/final13/gpt-5.6-sol.reply.json`
  - SHA-256 `affcfd9e1c2977a19ad9a80f3f1024e9cf9a6b9626937153dc8d5e493e3adcc3`
- Terra: `machine/stages/S6/reviews/rmd05/final13/gpt-5.6-terra.reply.json`
  - SHA-256 `941b8564a33469668c61abb74c30d857f73415df736802fff22b32a84f06fb0d`
- Shared request: `machine/stages/S6/reviews/rmd05/rereview16-request.md`
  - SHA-256 `c9dbfe36571c73f6316e1e8ac2b5f86aa37b64528d4c6ed4b57e64e07b743fd1`
- Shared receipt: `machine/stages/S6/reviews/rmd05/execution-receipt16.json`
  - SHA-256 `a620d6b8f39fb78a88215714e0bf13b8c1415903c27489e700fa4ae4e28df937`
- Review anchor: `d9fe1b73ac23bf256df9a98dcf9503f655aad7bc`
- Execution parent: `6b1d1519ca700f4e32ed7d1e0e39fadef364955c`
- Shared tree: `86f4a61806b2d53f8712ff831b047171331041a6`

Both current provenance records contain exactly 17 ordered attempts, 34 distinct Codex platform
task IDs and `closure_status=BLOCKED`. Attempt 17 is
`REREVIEW_ASSURANCE_CLI_IMPORT_SUPERSEDED`. Attempt 18 may become `REREVIEW_FINAL` only if both new
replies independently PASS and close the complete finding history.

## New blocking finding to verify

`RMD05-CLOSURE-012` was discovered only after attempt-17 replies and all proposed final outputs were
materialized and committed. The exact final workflow command invokes
`python machine/tools/validate_assurance_reviews.py` directly. In that direct entry path Python put
only `machine/tools` on `sys.path`; it did not put the project root there. During final post-review
authority validation, `_validate_post_review_authorities` imports `machine.acceptance`, so the clean
direct CLI could raise `ModuleNotFoundError` and report false authority failures. The delivery-status
validator did not expose the problem because its import chain had already inserted the project root.

Attempt 17 is therefore preserved as a superseded PASS rather than rewritten as final authority.
The proposed final materialization commit was reverted before this candidate was built. No protected,
production, deployment, publication or remote authority was granted.

## Remediation under review

### 1. The standalone CLI establishes its own deterministic import root

`machine/tools/validate_assurance_reviews.py` now derives `PROJECT_ROOT` from its own file path and
inserts that exact root into `sys.path` before importing sibling validation code. The later duplicate
root declaration was removed. This makes direct script execution independent of incidental import
order while keeping the same repository root used by candidate Git and Acceptance checks.

### 2. The regression executes the exact direct CLI on a clean final state

`test_rmd05_public_closure_uses_real_git_and_the_full_authority_set` builds a clean real-Git fully
materialized closure, including the final receipt/request/replies, both provenance wrappers, all
Stage 6 v2 evidence, all 67 deterministic authorities and all final metadata. It then executes the
fixture's own `machine/tools/validate_assurance_reviews.py` through a fresh subprocess, with
`--repository-root` and the pinned Governance checkout, and requires exit code zero plus
`status=PASS`. The same fixture also invokes the actual final secret scanner and delivery validator.
This regression failed before the import fix and passes on the candidate.

### 3. Attempt protocol and final routes are exact

- Provenance permits exactly 17 attempts only with `closure_status=BLOCKED`, and exactly 18 attempts
  only with `closure_status=PASS`.
- Attempt 17 has the dedicated phase `REREVIEW_ASSURANCE_CLI_IMPORT_SUPERSEDED`; its two replies,
  task IDs, request, receipt, anchor and tree are identity/hash pinned.
- Attempt 18 is the only allowed `REREVIEW_FINAL` position. It uses distinct task IDs
  `/root/rmd05_sol_rereview17` and `/root/rmd05_terra_rereview17`.
- Final Stage 6 evidence routes only to `execution-receipt17.json`; final replies route only to
  `final14/`; the shared final request routes only to `rereview17-request.md`.
- A final reply must make all four dimensions PASS, contain no OPEN finding and explicitly resolve
  the complete history through `RMD05-CLOSURE-012`.
- The exact final-output non-authority set remains 12 paths. All attempt-17 artifacts are already
  immutable candidate-tree content and are not post-review additions.
- Receipts 1 through 17 remain structured-scanned for credentials/private keys and excluded from
  the generic high-entropy layer; receipt-sensitive-value negative regressions remain fail closed.

### 4. Governance and derived authorities remain deterministic

The final changelog fact says `十八次不可变尝试链`. An exact closed-state real-Git fixture was checked
against pinned Governance commit `ebc6c2e4884edc959118cfc56d0e18a86c49460f`. The public closure
regression requires all seven rendered document hashes below, a zero-drift Governance check, budget
PASS and blocker PASS:

- `文档/00_我在哪.md`: `e8640872a36030932bf70b2df273f79b1a792fea4e42198f692774511379a888`
- `文档/01_产品需求.md`: `33bc71d5215a2b50290729cac50d1615378c8c476d5c30647dd915c3ca4c5d51`
- `文档/02_系统架构.md`: `48e7277040b64bd7926f3596482a6f24680226fce8c124c520073c196559802e`
- `文档/03_口径字典.md`: `0cd7c9e25e2415cbab74fbe0289301a7f4335d6d6a018de3d29cc22001531bb7`
- `文档/04_操作流程.md`: `98ddc96fef39fc7a899463bc5f23248ebaddd7bc2729484db77452e9d22c6362`
- `文档/05_执行与验收.md`: `36d57486d3553458b5c1b086d5cb8867337f3425379e521452eb41b29d716d0e`
- `文档/06_运维手册.md`: `2b02803ff141261a9222f3b5c03c97097e730ad18269c89f75376dbf1da21177`

The actual delivery tree must still rerun the pinned Governance final check, actual final secret scan,
direct assurance CLI and delivery-status validation after both replies and every final output are
materialized. A pre-review fixture result is not accepted as final closure evidence.

## Candidate-bound local gates

Receipt17 records exactly 19 distinct commands, all with exit code zero. Its v1 schema validates,
all sanitized stdout/stderr digests are recomputable, and the detached checkout remained clean.
Recorded outcomes include:

- Ruff format and lint PASS; strict mypy PASS;
- Stage 6 task tests: `55 passed`;
- affected Stage 7 runtime regressions: `37 passed`;
- RMD-05 remediation regressions: `33 passed` in 159.73 seconds, including the exact direct CLI,
  actual fully materialized secret-scan assertion, frozen Acceptance and real-Git authority attacks;
- assurance history integrity PASS with 17 attempts per model and 34 distinct task IDs while closure
  remains honestly BLOCKED;
- Stage 6 `REVIEW_INPUT` PASS and exact v1.0.4 PRE_CLOSURE delivery status PASS;
- 13 Governance facts match;
- dependency audit, reproducible SBOM, zero-finding secret scan and publication scan PASS;
- pinned shared Governance validation PASS on the reviewed PRE_CLOSURE candidate;
- local container build, network-none/read-only smoke, cleanup and local package build PASS.

Receipt17 records `sensitive_data_observed=false`,
`production_or_protected_executed=false`, `remote_service_writes=0` and
`ephemeral_local_outputs_removed=true`.

## Required independent review method

Review read-only and independently. Inspect the exact Git objects, external receipt17, preserved
attempt-17 artifacts, schemas, validators, builders, fixed render digests and regressions. Recompute
hashes and run read-only local checks where useful. Independently confirm that the exact direct CLI
works in a clean fully materialized fixture and that the pinned Governance renderer can produce the
seven fixed final document hashes from exact closed facts. Do not trust this narrative over candidate
source.

Do not access Gmail, GitHub remotes, Secrets, protected Oracles, production workflows, deployment
or publication. Do not communicate with or inspect the other reviewer.

Return exactly one UTF-8 JSON object and no Markdown, conforming to
`machine/stages/S6/schemas/review-reply-v2.schema.json`, with:

- target baseline `2b8625a83e69093b9dce989f4eb964556e1b5fa2`;
- target candidate `2ba0d34cee89672297d7c575205c3d4bf854461b`;
- target tree `673132302ed909d8c02e856fdb19887b20c3f447`;
- this request's exact SHA-256 (provided in the dispatch message);
- `review_mode=READ_ONLY_INDEPENDENT`;
- exactly the four dimensions `SCOPE`, `EVIDENCE_QUALITY`, `FAILURE_HONESTY`, `ROLLBACK`;
- the complete applicable finding chain, including an explicit disposition for
  `RMD05-CLOSURE-012`;
- honest limitations and false sensitive/protected/production claims.

Required verdict rule: return `PASS` only if all four dimensions PASS, every applicable finding is
`RESOLVED`, the direct CLI import defect is genuinely closed and no new OPEN finding exists.
Otherwise return `FAIL` and include every OPEN finding with a concrete required fix.

## Scope limitations that must remain explicit

This review proves only local immutable Git objects, deterministic post-candidate authority paths
and local synthetic gates. It does not prove protected Oracles, real Gmail, a private repository,
real Secrets, production health, a production workflow, deployment, publication, RMD-06, RMD-07
or final AC-033.
