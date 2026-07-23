# RMD-05 isolated Stage 6 assurance review request

Review exactly the immutable Stage 6 change below. This is a read-only assurance review, not an
implementation task and not a production-readiness review.

## Immutable target

- Repository: `MetaDatabase`, project path `LinzeDatabase/MooMooAU`
- Baseline commit: `2b8625a83e69093b9dce989f4eb964556e1b5fa2`
- Candidate commit: `be8e196b03dcc475ed6261fbe20593b08bd26bcf`
- Candidate tree: `56e8dce97168bab0ba5b57fe0cb580267776d94e`
- Required dimensions: `SCOPE`, `EVIDENCE_QUALITY`, `FAILURE_HONESTY`, `ROLLBACK`

The invocation supplies the SHA-256 of this request. Bind that exact digest into the reply.

## Isolation and data boundary

1. Inspect only Git objects reachable through the baseline/candidate pair above and this request.
2. Do not read the current worktree except this request. In particular, do not read either existing
   file directly under `machine/stages/S6/reviews/`; they are disputed evidence and would anchor the
   review.
3. Do not read environment variables, credentials, user directories, local configuration, Gmail,
   private GitHub state, network resources, or any file outside the immutable diff.
4. Do not execute tests, write files, invoke network tools, spawn another agent, or contact another
   reviewer. Static inspection of the immutable Git diff is sufficient.
5. The target is intended to contain only code, contracts and synthetic evidence. If any real or
   sensitive data appears, stop and return `FAIL` without reproducing that value.

The exact full-diff command is:

```text
git diff --no-ext-diff --unified=80 2b8625a83e69093b9dce989f4eb964556e1b5fa2 be8e196b03dcc475ed6261fbe20593b08bd26bcf -- . ':(exclude)LinzeDatabase/MooMooAU/machine/stages/S6/reviews/gpt-5.6-sol.json' ':(exclude)LinzeDatabase/MooMooAU/machine/stages/S6/reviews/gpt-5.6-terra.json'
```

Use `git show <commit>:<path>` only for a path present in that diff when more context is required.
Pay particular attention to the Stage 6 run/acceptance contracts, validator, model boundary,
attachment inspection, capacity/operation gates, load probe, chaos/kill matrices, tests, workflow
pins, dependency lock, SBOM, evidence truthfulness and rollback boundary.

## Decision rule

- Return `PASS` only if all four dimensions pass and there are no open findings.
- Return `FAIL` for any defect, unsupported claim, scope escape, unverifiable evidence, unsafe
  rollback, or uncertainty material to a dimension. Every finding in a fresh reply is `OPEN`.
- Do not infer remote CI, protected Oracle, real Gmail/private-repository behavior, production
  health, or final AC-033 from local/synthetic evidence.

## Exact response contract

Return one JSON object only, without Markdown fences or text before/after it:

```json
{
  "schema_version": "moomooau.independent-review-reply.v2",
  "target": {
    "baseline_commit": "2b8625a83e69093b9dce989f4eb964556e1b5fa2",
    "candidate_commit": "be8e196b03dcc475ed6261fbe20593b08bd26bcf",
    "candidate_tree": "56e8dce97168bab0ba5b57fe0cb580267776d94e",
    "request_sha256": "<digest supplied by invocation>"
  },
  "review_mode": "READ_ONLY_INDEPENDENT",
  "verdict": "PASS or FAIL",
  "dimensions": [
    {
      "id": "SCOPE",
      "status": "PASS or FAIL",
      "evidence_refs": ["path:line or path"],
      "rationale": "concise evidence-based rationale"
    },
    {
      "id": "EVIDENCE_QUALITY",
      "status": "PASS or FAIL",
      "evidence_refs": ["path:line or path"],
      "rationale": "concise evidence-based rationale"
    },
    {
      "id": "FAILURE_HONESTY",
      "status": "PASS or FAIL",
      "evidence_refs": ["path:line or path"],
      "rationale": "concise evidence-based rationale"
    },
    {
      "id": "ROLLBACK",
      "status": "PASS or FAIL",
      "evidence_refs": ["path:line or path"],
      "rationale": "concise evidence-based rationale"
    }
  ],
  "findings": [
    {
      "id": "reviewer-local stable identifier",
      "severity": "BLOCKING or HIGH or MEDIUM or LOW",
      "status": "OPEN",
      "finding": "defect or unsupported claim",
      "evidence_refs": ["path:line or path"],
      "required_fix": "minimum remediation and re-review condition"
    }
  ],
  "limitations": ["what this static local review does not prove"],
  "sensitive_data_observed": false,
  "production_or_protected_claimed": false,
  "summary": "concise final conclusion"
}
```
