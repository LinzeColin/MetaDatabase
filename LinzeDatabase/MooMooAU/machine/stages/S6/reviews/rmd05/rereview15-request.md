# MooMooAU RMD-05 final independent rereview request (attempt 16)

## Immutable target

- Baseline commit: `2b8625a83e69093b9dce989f4eb964556e1b5fa2`
- Review candidate anchor: `3794c433c7693e3e65581abfa012bc799d5bf5d6`
- Execution candidate parent: `44f14389309a170edd6be7f97073c697d6efe2f3`
- Shared candidate tree: `9585d313f8254cb0c7c0e952e3be84c20ceb95be`
- Candidate-bound receipt: `machine/stages/S6/reviews/rmd05/execution-receipt15.json`
- Receipt SHA-256: `5091a3bc3d6bd3fa976ed94524a479392f18ae2b71e22baed0f04742dbf0d1fe`
- Scope: `LOCAL_SYNTHETIC_ONLY`

The anchor has exactly one parent. The anchor and parent resolve to the same tree. Its commit
message contains exactly one execution-candidate trailer and exactly one receipt-digest trailer.
Treat the anchor, parent, tree, this request and receipt as immutable review inputs. The request and
receipt intentionally remain outside the immutable candidate tree until post-review
materialization.

## Preserved attempt-15 result and why it is superseded

Attempt 15 produced two independent PASS replies, but it is not accepted as final closure because
the subsequent final-authority materialization exposed a new blocking defect. The exact replies
remain preserved byte-for-byte:

- Sol: `machine/stages/S6/reviews/rmd05/final11/gpt-5.6-sol.reply.json`
  - SHA-256 `2d82f66fa0e64b28cb53a64b5a1e9fd880d325100ae3d56baece79d2c5d35f6e`
- Terra: `machine/stages/S6/reviews/rmd05/final11/gpt-5.6-terra.reply.json`
  - SHA-256 `6ff2e11ab21e4004edf86b59b99df6ba7e5851996e6dc4d9522a365ba4e0a732`
- Shared request: `machine/stages/S6/reviews/rmd05/rereview14-request.md`
  - SHA-256 `7f1ec39e6e27096620a9c15347f44c77e34365d8b0052a0bbf093b85f562b06c`
- Shared receipt: `machine/stages/S6/reviews/rmd05/execution-receipt14.json`
  - SHA-256 `798811aa1304fa1aa9739b825009a6a1e273656093caf882c860e4b6b2a55a15`
- Review anchor: `85fffeb6b43e8867b2b070d727d6401d465402ae`
- Execution parent: `a4cae6b6cc4dddbb635764b484bfb5220588c0b8`
- Shared tree: `953360aefea09618457fe341821e174eea6a706b`

Both current provenance records contain exactly 15 ordered attempts, 30 distinct Codex platform
task IDs and `closure_status=BLOCKED`. Attempt 15 is
`REREVIEW_GOVERNANCE_MATERIALIZATION_SUPERSEDED`. Attempt 16 may become `REREVIEW_FINAL` only if
both new replies independently PASS and close the complete finding history.

## New blocking finding to verify

`RMD05-CLOSURE-010` was discovered only after attempt-15 review outputs and all final authorities
were materialized. The final machine facts were internally valid, but pinned Governance final
validation failed:

1. Four generated human documents drifted from the reviewed candidate render:
   `文档/00_我在哪.md`, `文档/03_口径字典.md`, `文档/05_执行与验收.md` and
   `文档/06_运维手册.md`.
2. The final facts used unregistered English terms `run` and `PASS`, causing the shared Chinese
   terminology gates to fail.
3. The old 60-file post-review authority set excluded all seven generated human documents, so the
   public closure mechanism could not prove their exact pinned final render.

Attempt 15 is therefore preserved as a superseded PASS rather than rewritten as final authority.
No final authority commit from that attempt was accepted.

## Remediation under review

### 1. All seven Governance documents are exact post-review authorities

`GOVERNANCE_DOCUMENT_AUTHORITY_SHA256` pins the exact UTF-8 bytes rendered from the final closed
facts by Governance commit `ebc6c2e4884edc959118cfc56d0e18a86c49460f`:

- `文档/00_我在哪.md`: `e8640872a36030932bf70b2df273f79b1a792fea4e42198f692774511379a888`
- `文档/01_产品需求.md`: `33bc71d5215a2b50290729cac50d1615378c8c476d5c30647dd915c3ca4c5d51`
- `文档/02_系统架构.md`: `48e7277040b64bd7926f3596482a6f24680226fce8c124c520073c196559802e`
- `文档/03_口径字典.md`: `0cd7c9e25e2415cbab74fbe0289301a7f4335d6d6a018de3d29cc22001531bb7`
- `文档/04_操作流程.md`: `98ddc96fef39fc7a899463bc5f23248ebaddd7bc2729484db77452e9d22c6362`
- `文档/05_执行与验收.md`: `36d57486d3553458b5c1b086d5cb8867337f3425379e521452eb41b29d716d0e`
- `文档/06_运维手册.md`: `9a892056824fb87d8446e0ec60314817f05e474fb72c43b4a8cc7bc184c7d14d`

The exact post-review authority set is now 67 paths: the former 60 deterministic outputs plus all
seven documents. `_validate_post_review_authorities` reads every document, checks its fixed digest,
includes its exact bytes in the candidate-to-final delta calculation and rejects any missing,
unreadable or different render.

### 2. Real Git path comparison handles non-ASCII paths deterministically

The public Git evaluator now invokes Git with `core.quotepath=false`. Without that setting, Git
returned quoted octal escapes for the Chinese document names and misclassified valid authority
paths as protected drift. The real public closure tests exercise these paths through
`_validate_git_subject(..., allow_post_review_authorities=True)` and
`evaluate_assurance_reviews(..., verify_git=True)`.

### 3. A synchronized Governance-document attack is covered publicly

`test_rmd05_public_closure_rejects_governance_document_render_drift` starts from a valid, clean,
committed closure, changes `文档/06_运维手册.md`, rebuilds the canonical package manifest and commits
the synchronized result. The public evaluator must be BLOCKED specifically with
`post-review Governance document authority differs from the reviewed pinned render`, and the
delivery-status validator must fail.

The existing public scenarios still require a valid 67-path closure, block five forbidden-path
mutations with synchronized manifests, and freeze Acceptance builder inputs to the reviewed
candidate. The complete RMD-05 test file now reports 33 passing tests.

### 4. Final facts are terminology-safe and the actual final render remains mandatory

`build_governance_facts.py` now emits the Chinese final plan text
`RMD-05 已关闭；下一轮仅进入 RMD-06` and the Chinese changelog description
`十六次不可变尝试链...独立通过`. It no longer introduces the unregistered English terms that caused
the final shared Governance gates to fail.

An ephemeral closed-facts fixture was rendered with the pinned Governance checkout and then checked
again: no fact mismatches, no render drift, shared budget gate PASS and shared blocker gate PASS.
Its seven document digests match the constants above. This fixture is local synthetic evidence, not
production evidence. After the two final review replies are materialized, the actual delivery tree
must still run pinned Governance `--render` and a separate final check before RMD-05 may be declared
closed.

### 5. Exact protocol limits remain fail closed

- The only non-authority post-review paths are the exact 12 final-output files for receipt15,
  request15, final12 replies, provenance wrappers and v1.0.5 human/task-pack metadata.
- Every other source, workflow, dependency, test, validator, schema, unexpected facts, extra
  Acceptance or Oracle path remains protected.
- Schema and validator permit exactly 15 attempts only with `closure_status=BLOCKED`, and exactly
  16 attempts only with `closure_status=PASS`.
- Attempt 15's two replies, request14, receipt14, anchor and tree are hash/identity pinned.
- Attempt 16 must use two new distinct platform task IDs, this shared request15, two distinct
  final12 replies, receipt15 and the same anchor/tree.
- A final reply must make all four dimensions PASS, contain no OPEN finding, and explicitly resolve
  the complete history through `RMD05-CLOSURE-010`.

## Candidate-bound local gates

Receipt15 records exactly 19 distinct commands, all with exit code zero. Its v1 schema validates
and every sanitized stdout/stderr digest is recomputable. Recorded outcomes include:

- Ruff format: 86 files; Ruff lint PASS;
- strict mypy: 72 source files;
- Stage 6 task tests: `55 passed`;
- affected Stage 7 runtime regressions: `37 passed`;
- RMD-05 remediation regressions: `33 passed`, including the real Governance-document drift case;
- assurance history integrity PASS with 15 attempts per model and 30 distinct task IDs while
  closure remains honestly BLOCKED;
- Stage 6 `REVIEW_INPUT` PASS and exact v1.0.4 PRE_CLOSURE delivery status PASS;
- 13 governance facts match;
- dependency audit, reproducible SBOM, zero-finding secret scan and publication scan PASS;
- pinned shared Governance validation PASS on the reviewed PRE_CLOSURE candidate;
- local container build, network-none/read-only smoke, cleanup and local package build PASS.

Receipt15 records `sensitive_data_observed=false`,
`production_or_protected_executed=false`, `remote_service_writes=0` and
`ephemeral_local_outputs_removed=true`. The candidate checkout remained clean.

Two earlier local candidate-gate executions were honestly rejected before receipt creation: one at
delivery-status validation because derived hash roots had not yet been rebuilt, and one at secret
scan because nine SHA-256 authority values lacked explicit non-secret allowlist annotations. The
reviewed candidate contains both fixes and reran the entire matrix from the beginning.

## Required independent review method

Review read-only and independently. Inspect the exact Git objects, external receipt15, schemas,
validator, builders, fixed render digests and regressions. Recompute hashes and run read-only local
checks where useful. Independently confirm that the pinned Governance renderer can produce the
seven fixed final document hashes from an exact closed-facts fixture; do not trust this narrative
over candidate source.

Do not access Gmail, GitHub remotes, Secrets, protected Oracles, production workflows, deployment
or publication.

Return one UTF-8 JSON object conforming to
`machine/stages/S6/schemas/review-reply-v2.schema.json`, with:

- target baseline `2b8625a83e69093b9dce989f4eb964556e1b5fa2`;
- target candidate `3794c433c7693e3e65581abfa012bc799d5bf5d6`;
- target tree `9585d313f8254cb0c7c0e952e3be84c20ceb95be`;
- this request's exact SHA-256;
- `review_mode=READ_ONLY_INDEPENDENT`;
- exactly the four dimensions `SCOPE`, `EVIDENCE_QUALITY`, `FAILURE_HONESTY`, `ROLLBACK`;
- the complete applicable finding chain, including an explicit disposition for
  `RMD05-CLOSURE-010`;
- honest limitations and false sensitive/protected/production claims.

Required verdict rule: return `PASS` only if all four dimensions PASS, every applicable finding is
`RESOLVED`, the new final-Governance-authority defect is genuinely closed, and no new OPEN finding
exists. Otherwise return `FAIL` and include every OPEN finding with a concrete required fix.

## Scope limitations that must remain explicit

This review proves only local immutable Git objects, deterministic post-candidate authority paths
and local synthetic gates. It does not prove protected Oracles, real Gmail, a private repository,
real Secrets, production health, a production workflow, deployment, publication, RMD-06, RMD-07
or final AC-033.
