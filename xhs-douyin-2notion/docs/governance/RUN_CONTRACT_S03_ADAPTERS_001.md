# Run Contract — `RUN-X2N-S03-A001`

## Identity and authorization

- Task: `TSK.x2n.adapters.001`
- Phase: `PH.X2N.3.1`
- Stage: `STG.X2N.3`
- Task base: `ee5d251ca30eab226c4df75c53965f312c2d9b05`
- Branch: `codex/xhs-douyin-2notion-v0001-s03-adapters001`
- Run kind: one DAG Task only

The Task base is the public Stage 2 merge commit from PR 78. The final x2n run
`29922576589` and Dual-Plane run `29922576674` both completed successfully before
this Run. This new Stage 3 transition fact does not rewrite the historical G2
pre-upload evidence, which remains an immutable account of its earlier execution.

## Objective and bounded scope

Implement the credential-free foundation for Owner-managed login state:

1. a launcher that selects only fixed OS Chrome candidates and a platform Profile
   below logical `X2N_DATA_ROOT/runtime/browser_profiles/`;
2. a five-minute, enum-only live session observation with blocked user action for
   missing, stale, expired, verification-required or platform-changed state;
3. an eight-component `x2n doctor` report using the existing Health/Error Contract,
   exact `ok/degraded/blocked` states and path-free executable remediation;
4. a single cross-process Adapter mutex, non-waiting durable low-frequency gate and
   no automatic retry;
5. a deletion guard under which auth/network/DOM/empty/partial results cannot remove
   a relation, and two consecutive complete successes can only create a
   `tombstone_candidate`.

The Run may change the Companion Profile/session/runtime/CLI modules, public-safe
synthetic fixtures, Stage 3.1 policy, verifier, compact evidence and required state
documentation. It must not enter `TSK.x2n.adapters.002`, implement any list iterator,
read/export Cookie or credentials, accept an arbitrary executable/Profile path/URL,
enable remote debugging, automate login/CAPTCHA, scroll, mutate account state, call a
platform, launch Owner Chrome during acceptance, migrate SQLite, alter the Native v1
action contract, process media, call Notion/models, run a real Canary, upload GitHub,
or touch external shared authentication material.

## Public Code / Private Runtime decisions

- Profile contents and session checkpoint/rate files are Private Runtime only,
  `0700/0600`, symlink-rejected, excluded from ordinary backup and never emitted.
- The launcher opens an internal new tab only; the Owner manually navigates and logs
  in. No platform login URL is automatically requested and no credential value is
  accepted.
- A future Adapter may record only `{platform, signal, observed_at}` after a live page
  probe. The Companion never infers login by opening Chrome Cookie storage.
- Missing human input follows the PRD reversible default: synthetic development
  completes while real Profile login, account execution and Canary remain `NOT_RUN`.
- Profile/session failure disables batch Adapter capability while preserving the
  already accepted current-page fallback and Canonical Store.

## Acceptance

- `ACC.x2n.batch.001`: auth expired, HTTP error, DOM change, empty response and partial
  scan each produce relation `removed=0`; first complete success produces candidate
  `0`; second consecutive complete success produces only `tombstone_candidate`;
  physical deletion and automatic Content deletion remain `0`.
- `ACC.x2n.ops.004`: Extension, Native Host, Companion, DB, FFmpeg, Provider, Notion and
  Adapter each return `ok/degraded/blocked`. Missing FFmpeg, Notion and Provider are
  degraded without claiming Canonical unavailable; Native Host missing and DB Busy
  block core operation; Profile not logged in blocks Adapter only. Every non-ok row has
  a stable code and minimal path-free command/action.
- `ACC.x2n.gov.002`: current source, fixture, build/release candidate and compact
  evidence scans find Secret `0`, Private Content `0`, Browser State `0`, Profile path
  `0`, local user path `0`, SQLite/media Runtime artifact `0`.

Completion status is only `PASS_CI_SYNTH_SCOPED`. Owner Profile login, real account,
platform calls and Owner Canary are `NOT_RUN`; `G3=NOT_RUN` and Stage 3 upload remains
forbidden.

## Verification commands

```bash
.venv/bin/python -B scripts/run_adapters_001_acceptance.py
.venv/bin/python -B scripts/verify_adapters_001.py \
  --verify-worktree --allow-external-main-dirty
.venv/bin/python -B scripts/ci/run_lane.py --lane full --repetitions 2 \
  --reports-dir build/s03-adapters001-final
.venv/bin/python -B scripts/verify_adapters_001.py \
  --verify-worktree --allow-external-main-dirty \
  --lane-report build/s03-adapters001-final/software-lane.json --write-evidence
.venv/bin/python -B scripts/verify_adapters_001.py \
  --verify-worktree --allow-external-main-dirty --skip-external \
  --lane-report build/s03-adapters001-final/software-lane.json --require-evidence
.venv/bin/python -B -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python -B -m unittest discover -s apps/companion/tests -p 'test_*.py'
```

The final full lane runs every blocking Gate twice. Any silent blocking skip, real
browser/account/platform execution, Cookie/Profile/credential read, Profile path or
Runtime artifact in public output, mutex bypass, reduced interval, automatic retry,
non-authoritative deletion, failed remediation contract or flaky Gate fails the Run.

## Risk, rollback and stop conditions

- Risk: Profile path exposure, symlink/permission drift, concurrent adapters corrupting
  session state, stale health treated as login, wall-clock rollback or verification
  bypass temptation.
- Rollback: disable all batch flags, close the dedicated Profile, revert this local Task
  commit and preserve Stage 2 current-page capture plus Canonical data.
- Stop: any implementation needs platform verification bypass, Cookie/credential
  export, arbitrary browser command/path/URL, Profile files in Git, real account action,
  unresolved deletion ambiguity, Stage 3 task overlap or premature remote upload.
