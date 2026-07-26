# CB-120 Validation Report

- Run: `P1.3 / CB-120`
- Task state: `passed`
- CB-130: `not_started`
- Implementation/release:
  `10d988e908d72ea1a43bbed04a2130a338663363`
- Target: same pseudonymous authorized asset as CB-010/CB-100/CB-110
- Workspace alias: `cyberboss`
- Data activation: `activation_pending`
- Remote publication: `none`

## Result

The clean implementation commit produced one complete Corresponding Source
archive, one no-external-fetch partial seed, the exact canonical no-clone
client and the pinned official GitHub CLI archive. All local and target hashes
matched. The candidate passed the complete 166-test App suite, was hardened
root-owned/read-only and remained outside `current`.

Installer check mode was write-free. Two applies and one independent verify
passed against the same implementation commit; the second apply left the
controlled state digest unchanged. `current` still resolves to the CB-100
release, the main unit is disabled/inactive, and final CyberBoss/data process
and 8765/8780 listener counts are zero. The exact commit-bound incoming and
transfer directories were deleted after evidence validation; transient
artifact and budget-file counts are zero.

The single workspace resolves only through alias `cyberboss`, has exact head
and branch, `blob:none` promisor metadata, sparse paths `.github` and
`CyberBoss`, a local immutable seed origin and a clean status. Nine target
tests plus an actual registry resolution passed. Absolute paths, unknown
aliases, workspace/config/base symlink escape and an unregistered Runtime root
were rejected without binding or filesystem mutation.

The `cyberboss` identity cannot read the canonical data client or execute its
wrapper. The `cyberboss-data` identity cannot write the code workspace. Its
exact-hash wrapper completed only a `verify` plan and reported
`real_data_operation=false`; the credential file remains absent and no
Private-Database clone exists.

Live workspace use is 29,058,557 bytes against a 4 GiB limit, target free
space exceeds 20 GiB, and the state is `recover`. Deterministic guard/protect/
stop/recovery checks and the bounded 128 MiB target cgroup fixture passed with
16 MiB memory, 8 MiB disk, 100 queue items and zero OOM events. There was no
sleep or real-time soak.

## Preserved execution corrections

Six superseded local commits are retained in Git history with their exact
failed Oracle and rollback/cleanup outcome in
`install-acceptance.redacted.json`. None was published. Final acceptance also
preserves the operator-cwd Node invocation correction, the unsupported local
locale correction and relative-`current` comparison correction rather than
claiming those attempts passed.

The bounded pressure fixture initially let root Python create one `.pyc` and
its `__pycache__` directory inside the otherwise read-only candidate. These
two rebuildable transient entries were the only source-tree delta, were
deleted after exact path/type/owner verification, and no source file was
removed. The full candidate tree then passed immutability and cache-absence
checks. Any repeat of that fixture must set
`PYTHONDONTWRITEBYTECODE=1`.

## Compliance and security boundary

The exact original vendor source, original license files, notices,
Corresponding Source and the unresolved whereabouts conflict record remain
preserved. The conservative expression is
`AGPL-3.0-only AND GPL-3.0-only`; no upstream support, sync or endorsement
route is active, and `upstream_clarification_received=false`.

P0/P1 findings, credential content reads, provider writes,
Private-MetaDatabase writes/clones, public listeners and real business
Runtime starts are all zero. No target address or credential value is stored
in this evidence.

## Acceptance

- AC-013: `passed`
- AC-014: `passed`
- AC-064: `passed`
- Only CB-120 changed task state.
- CB-130 and every later task, plus PG-1–PG-5, remain `not_started`.
- No branch, PR, tag, release or push exists remotely.

The final fail-closed repository validator result is recorded in
`validation.txt`.
