# Social Archive v0.0.0.4 compatibility overlay

This overlay preserves the supplied `v0.0.0.4` Task Pack as the sole product,
roadmap, task-ID, stage-gate, and acceptance baseline. It repairs only five
execution-control defects discovered against the actual integrated
`xhs-douyin-2notion` tree.

It is deliberately not placed in the Owner's three-file delivery contract and
does not alter the supplied ZIP. Before use, `prepare_compat_taskpack.py`
verifies the exact base archive, its original manifest, ZIP safety, and the
override allowlist. It then creates a disposable compatible extraction, replaces
only the five listed scripts, refreshes that copy's manifest, and runs the
Task Pack verifier. The compatible extraction is not a release artifact.

## Fixed execution defects

1. Detect the real focused-tested core at
   `apps/companion/src/x2n_companion/{canonical_store,orchestrator}.py` with
   its focused recovery tests, rather than searching only obsolete `src/x2n`.
2. Require a worktree branch to include the fetched `origin/main` without
   requiring development to occur on `main` or silently merging remote history.
3. Move and snapshot only tracked product files, never ignored runtime or raw
   data. Generated migration/candidate directories are ignored before backup or
   candidate creation.
4. Keep prebuilt `src/social_archive` core files as SA-003 candidates when a
   legacy core is proven; never create a second live authority through a blind
   whole-tree move plus overlay.
5. Make SQLite inspection explicit, one-snapshot, aggregate-only and genuinely
   write-free in dry-run; make rollback plan-only by default and require an
   exact destructive confirmation for execution.
6. Use Git's explicit `git mv --sparse` when the current worktree includes the
   legacy source but not the new product path, so the tracked identity move is
   allowed without broadening the sparse checkout or touching ignored runtime.

## Execution authority

The external handoff refers to `11_AGENT/BUILD_AGENT_RUNBOOK.md`, which is not
present in the sealed ZIP. For this compatibility overlay only, the exact
replacement is the already-required pair:

- `11_AGENT/EXECUTION_ORDER.md` for run ordering and handoff rules; and
- `09_ROADMAP/TASK_GRAPH.json` for the 32 task dependencies, acceptance and
  stop conditions.

The explicit Social Archive v0.0.0.4 Owner instruction supersedes the old x2n
v0.0.0.1 product DAG only for the Social Archive migration. The x2n permanent
privacy, data-placement, no-crawler and real-account boundaries remain in
force. Its active Owner-private A005 runtime is not imported, moved, read or
claimed by this Task Pack; any future data transfer requires its own explicit
Private-Database Run Contract.

## Non-goals

- No Social Archive product code is built by this overlay.
- No source connector, destination, account, private database, runtime data,
  browser profile, credential, deployment, or GitHub remote is contacted.
- SA-000 and later tasks remain unstarted until their own Run Contract.

## Validation

Run from this directory with the project Python environment:

```sh
python3 scripts/validate_compatibility.py \
  --base-zip '/absolute/path/Social_Archive_v0.0.0.4_FINAL_TASKPACK_20260730.zip'
```

The validator uses only temporary repositories and synthetic files. It proves
the original package still validates, the actual companion layout selects the
preserve-core architecture decision, ignored runtime data is not moved, the
prebuilt core remains a candidate, and rollback is non-mutating by default.
