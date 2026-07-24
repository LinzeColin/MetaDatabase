# MooMooAU RMD-05 final independent rereview request (attempt 17)

## Immutable target

- Baseline commit: `2b8625a83e69093b9dce989f4eb964556e1b5fa2`
- Review candidate anchor: `d9fe1b73ac23bf256df9a98dcf9503f655aad7bc`
- Execution candidate parent: `6b1d1519ca700f4e32ed7d1e0e39fadef364955c`
- Shared candidate tree: `86f4a61806b2d53f8712ff831b047171331041a6`
- Candidate-bound receipt: `/private/tmp/moomooau-rmd05-candidate17.HsOPNu/execution-receipt16.json`
- Receipt SHA-256: `a620d6b8f39fb78a88215714e0bf13b8c1415903c27489e700fa4ae4e28df937`
- Scope: `LOCAL_SYNTHETIC_ONLY`

The anchor has exactly one parent. The anchor and parent resolve to the same tree. Its commit
message contains exactly one execution-candidate trailer and exactly one receipt-digest trailer.
Treat the anchor, parent, tree, this request and receipt as immutable review inputs. The request and
receipt intentionally remain outside the immutable candidate tree until post-review
materialization.

## Preserved attempt-16 result and why it is superseded

Attempt 16 produced two independent PASS replies, but it is not accepted as final closure because
the subsequent final-output materialization exposed a new blocking defect. The exact artifacts are
preserved byte-for-byte in the candidate:

- Sol: `machine/stages/S6/reviews/rmd05/final12/gpt-5.6-sol.reply.json`
  - SHA-256 `4026dddd373d1387ba78d0560507704c85a058ef1f622e714bb6b75a69cfaa15`
- Terra: `machine/stages/S6/reviews/rmd05/final12/gpt-5.6-terra.reply.json`
  - SHA-256 `1a466d65996259569d2544af389461da68ce9d7bfe1c49d021d8b9e33d3a4d61`
- Shared request: `machine/stages/S6/reviews/rmd05/rereview15-request.md`
  - SHA-256 `691f815fd09f5f2c7df84e6142e13f5b8ab4c3324324aa209f9633e3bef93067`
- Shared receipt: `machine/stages/S6/reviews/rmd05/execution-receipt15.json`
  - SHA-256 `5091a3bc3d6bd3fa976ed94524a479392f18ae2b71e22baed0f04742dbf0d1fe`
- Review anchor: `3794c433c7693e3e65581abfa012bc799d5bf5d6`
- Execution parent: `44f14389309a170edd6be7f97073c697d6efe2f3`
- Shared tree: `9585d313f8254cb0c7c0e952e3be84c20ceb95be`

Both current provenance records contain exactly 16 ordered attempts, 32 distinct Codex platform
task IDs and `closure_status=BLOCKED`. Attempt 16 is
`REREVIEW_SECRET_SCAN_MATERIALIZATION_SUPERSEDED`. Attempt 17 may become `REREVIEW_FINAL` only if
both new replies independently PASS and close the complete finding history.

## New blocking finding to verify

`RMD05-CLOSURE-011` was discovered only after attempt-16 replies, receipt15, request15, provenance,
all 67 final authorities and human/task-pack metadata were materialized. The final scoped secret
scan failed with 22 `Hex High Entropy String` findings from the legitimate digest-bearing
`execution-receipt15.json`.

The defect was an overlap between two scan layers:

1. `STRUCTURED_RECEIPT_PATHS` already inspected receipt15 using explicit credential/private-key
   patterns that distinguish sensitive material from legitimate hashes.
2. The generic `detect-secrets` exclusion covered only receipts 1 through 14, so receipt15 was
   scanned a second time by the high-entropy plugin after final materialization.
3. Candidate gates ran before receipt15 was inside the candidate tree, so a pre-materialization
   secret-scan PASS could not detect this final-state failure.

Attempt 16 is therefore preserved as a superseded PASS rather than rewritten as final authority.
No final authority commit from that attempt was accepted.

## Remediation under review

### 1. Receipt scanning is non-overlapping and remains fail closed

`machine/tools/validate_stage6_secret_scan.py` now lists receipts 1 through 16 in
`STRUCTURED_RECEIPT_PATHS`. The generic exclusion is exactly
`execution-receipt(?:[2-9]|1[0-6])?\.json`, so every receipt is scanned once by the structured
credential/private-key patterns and is not misclassified solely because it contains required Git
and SHA-256 digests. Provenance records remain structured-scanned. The candidate's scoped scan has
zero findings; a sensitive age identity inserted into any receipt, including receipt16, is still
rejected by regression tests.

### 2. The regression exercises the actual post-review materialized state

`test_rmd05_public_closure_uses_real_git_and_the_full_authority_set` builds a clean real-Git closure,
materializes receipt16, request16, both final13 replies, both provenance wrappers, all Stage 6 v2
evidence, all 67 authorities and v1.0.5 metadata, then calls the actual secret-scan validator. The
test requires a zero-finding PASS. The synthetic request uses the same backtick-delimited immutable
Git binding format as real review requests; no scanner rule was weakened to hide fixture output.

### 3. Attempt protocol and evidence routing are exact

- Provenance schema permits exactly 16 attempts only with `closure_status=BLOCKED`, and exactly 17
  attempts only with `closure_status=PASS`.
- Attempt 16 has the dedicated phase `REREVIEW_SECRET_SCAN_MATERIALIZATION_SUPERSEDED`; its two
  replies, task IDs, request, receipt, anchor and tree are identity/hash pinned.
- Final Stage 6 evidence routes only to `execution-receipt16.json`; the final replies route only to
  `final13/`, and the shared final request only to `rereview16-request.md`.
- A final reply must make all four dimensions PASS, contain no OPEN finding and explicitly resolve
  the complete history through `RMD05-CLOSURE-011`.
- The exact non-authority post-review set remains 12 paths: receipt16, request16, final13 replies,
  two provenance wrappers, README, VERSION and four human/task-pack metadata files. Attempt-16
  artifacts are already immutable candidate-tree content, not post-review additions.

### 4. Governance and derived authorities remain deterministic

The final changelog fact now says `十七次不可变尝试链`. An ephemeral exact closed-state fixture was
checked against pinned Governance commit `ebc6c2e4884edc959118cfc56d0e18a86c49460f`: no fact
mismatch, no render drift, shared budget PASS and blocker PASS. The seven generated document hashes
are:

- `文档/00_我在哪.md`: `e8640872a36030932bf70b2df273f79b1a792fea4e42198f692774511379a888`
- `文档/01_产品需求.md`: `33bc71d5215a2b50290729cac50d1615378c8c476d5c30647dd915c3ca4c5d51`
- `文档/02_系统架构.md`: `48e7277040b64bd7926f3596482a6f24680226fce8c124c520073c196559802e`
- `文档/03_口径字典.md`: `0cd7c9e25e2415cbab74fbe0289301a7f4335d6d6a018de3d29cc22001531bb7`
- `文档/04_操作流程.md`: `98ddc96fef39fc7a899463bc5f23248ebaddd7bc2729484db77452e9d22c6362`
- `文档/05_执行与验收.md`: `36d57486d3553458b5c1b086d5cb8867337f3425379e521452eb41b29d716d0e`
- `文档/06_运维手册.md`: `200808f5c0c208ef39e1de830fcd0b745866cfd1c6a1590197bbffa75c984e4a`

The actual delivery tree must still rerun pinned Governance final check and the actual final secret
scan after both replies and all final outputs are materialized. A pre-review fixture result is not
accepted as final closure evidence.

## Candidate-bound local gates

Receipt16 records exactly 19 distinct commands, all with exit code zero. Its v1 schema validates,
all sanitized stdout/stderr digests are recomputable, and the detached checkout remained clean.
Recorded outcomes include:

- Ruff format and lint PASS; strict mypy PASS;
- Stage 6 task tests: `55 passed`;
- affected Stage 7 runtime regressions: `37 passed`;
- RMD-05 remediation regressions: `33 passed` in 154.67 seconds, including the actual fully
  materialized secret-scan assertion and real-Git authority attacks;
- assurance history integrity PASS with 16 attempts per model and 32 distinct task IDs while
  closure remains honestly BLOCKED;
- Stage 6 `REVIEW_INPUT` PASS and exact v1.0.4 PRE_CLOSURE delivery status PASS;
- 13 governance facts match;
- dependency audit, reproducible SBOM, zero-finding secret scan and publication scan PASS;
- pinned shared Governance validation PASS on the reviewed PRE_CLOSURE candidate;
- local container build, network-none/read-only smoke, cleanup and local package build PASS.

Receipt16 records `sensitive_data_observed=false`,
`production_or_protected_executed=false`, `remote_service_writes=0` and
`ephemeral_local_outputs_removed=true`.

## Required independent review method

Review read-only and independently. Inspect the exact Git objects, external receipt16, preserved
attempt-16 artifacts, schemas, validator, builders, fixed render digests and regressions. Recompute
hashes and run read-only local checks where useful. Independently confirm that the fully materialized
secret-scan path is covered and that the pinned Governance renderer can produce the seven fixed
final document hashes from an exact closed-facts fixture; do not trust this narrative over candidate
source.

Do not access Gmail, GitHub remotes, Secrets, protected Oracles, production workflows, deployment
or publication. Do not communicate with or inspect the other reviewer.

Return one UTF-8 JSON object conforming to
`machine/stages/S6/schemas/review-reply-v2.schema.json`, with:

- target baseline `2b8625a83e69093b9dce989f4eb964556e1b5fa2`;
- target candidate `d9fe1b73ac23bf256df9a98dcf9503f655aad7bc`;
- target tree `86f4a61806b2d53f8712ff831b047171331041a6`;
- this request's exact SHA-256;
- `review_mode=READ_ONLY_INDEPENDENT`;
- exactly the four dimensions `SCOPE`, `EVIDENCE_QUALITY`, `FAILURE_HONESTY`, `ROLLBACK`;
- the complete applicable finding chain, including an explicit disposition for
  `RMD05-CLOSURE-011`;
- honest limitations and false sensitive/protected/production claims.

Required verdict rule: return `PASS` only if all four dimensions PASS, every applicable finding is
`RESOLVED`, the final secret-scan materialization defect is genuinely closed and no new OPEN finding
exists. Otherwise return `FAIL` and include every OPEN finding with a concrete required fix.

## Scope limitations that must remain explicit

This review proves only local immutable Git objects, deterministic post-candidate authority paths
and local synthetic gates. It does not prove protected Oracles, real Gmail, a private repository,
real Secrets, production health, a production workflow, deployment, publication, RMD-06, RMD-07
or final AC-033.
