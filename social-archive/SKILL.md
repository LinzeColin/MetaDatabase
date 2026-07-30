---
name: social-archive
description: >-
  Govern one frozen Social Archive v0.0.0.4 Task Pack task at a time while
  preserving the product's single-core, privacy, authorization and evidence boundaries.
---

# Social Archive

Use only the frozen v0.0.0.4 Task Pack and execute one bounded Task with its focused acceptance at a time. Do not run a full suite before the Frozen Candidate task, push an intermediate phase, create another worktree, or infer a real integration result from fixtures.

## Permanent boundaries

- Keep `social_archive` as the only active transaction core and product runtime identity.
- Keep SQLite rebuildable; write durable business facts only through the Private-Database boundary.
- Never persist or print credentials, browser state, cookies, tokens, raw platform media, or local runtime paths.
- Treat every source and destination as independently gated by Policy, Auth, Technical, Probe and Receipt evidence.
- Do not bypass platform controls, CAPTCHA, account protections or zero-cost gates.
- Keep third-party tools behind process, CLI, HTTP, container or import boundaries; do not copy their source into the first-party core.

## Current workflow

1. Read `HANDOFF.md`, the next Task Pack contract and its required evidence.
2. State the compact execution contract, then make the smallest scoped change.
3. Run only the task's focused test and Oracle.
4. Record PASS, FAIL, BLOCKED or NOT_RUN precisely in task evidence.

Real platform calls, destination authorization, cloud replication, deployment and rollback execution require their own task contract and explicit authority.
