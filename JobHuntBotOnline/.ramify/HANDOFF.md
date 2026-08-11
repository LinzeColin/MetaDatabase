# Handoff to Codex Delivery Agent

Read `START_HERE.md` first. The source Candidate, frozen contract, DAG, deployment scripts and local evidence are in this package. The prior invalid v0.3 ZIP is superseded and must not be used.

Do not repeat product research. NitroSend is removed: do not wait for it, connect it, or restore it. Observe latest repository and infrastructure, then execute the first unsatisfied task. Preserve current data and a rollback point. If standard SMTP is not yet available, keep public registration closed and continue every non-email task. Secrets stay outside Git and evidence. Do not run `deploy/acceptance.sh`, browser E2E, or any other real-email action unless the Owner grants a new one-time authorization and explicitly sets `RUN_REAL_EMAIL_ACCEPTANCE=true`; the script fails closed without that flag.

## 2026-08-11 VPS3 operational checkpoint — controlled email safety

- The live target is VPS3 (`vps-bab7f9dc`) at
  `https://jobhunt.linzezhang.com`. PostgreSQL, Web, Scheduler and Worker are
  running; `/readyz` reports `refresh_hours=6`.
- The Owner permits real mail only when it is controlled, and explicitly
  rejected the prior burst of three messages in ten minutes.
  `ALLOW_REGISTRATION=false` and `RUN_REAL_EMAIL_ACCEPTANCE=false` remain live
  and the public `/register` route is closed. This candidate adds a
  recipient-level 30-minute cooldown, a 24-hour cap of three delivery
  attempts, two distinct dedicated acceptance addresses, a one-use run ID,
  a 30-minute acceptance gap, and a persistent 24-hour acceptance cooldown.
  No new real-email action was run while introducing those controls.
- A prior root `ACCEPTANCE_RESULT.json` was invalidated and removed after the
  safety pause. There is currently no fresh target root production PASS, so
  T10 must not be marked complete and no full-production claim is allowed.
- All verified non-email functions remain available: PostgreSQL migration,
  restart readback, encrypted-backup verification, platform DeepSeek probe
  without key exposure, authorized job discovery, and the strict six-hour
  refresh are recorded by target evidence. NitroSend is absent and remains
  prohibited.
- Current VPS3 database aggregates confirm one discovery-enabled profile, four
  completed scheduled runs, and all three observed adjacent intervals within
  6:00:36–6:01:04; there is no overdue discovery schedule. These aggregates
  contain no user identifier, email, resume, or candidate fact.
- The complete local source test suite passed 31/31 in a disposable VPS3
  container with a read-only source mount and `--network none`; this exercised
  authentication, tenant isolation, resume/onboarding, discovery, application
  preparation, migration, recovery tooling, and the email-closed path without
  sending mail or contacting any external service.
- T09 was re-established with non-authoritative operational evidence only:
  `https://status.linzezhang.com/data/snapshot.json` now registers JobHuntBot
  Online on VPS3 and states the email pause; Private-Database
  `Private-MetaDatabase/JobHuntBotOnline/operations/v0.3.0/latest.json` was
  read back with no business data, PII, or Secrets. PostgreSQL remains the
  sole business-data authority.
- R2 is deliberately `NOT_CONFIGURED`. No JobHuntBot-specific bucket or
  credential is authorized, and no R2 operation, InfrequentAccess setting,
  recurring task, or cross-project credential reuse was performed. The target
  `evidence/target-ops.json` is therefore noncritical `BLOCKED` with Status
  and Private-Database checks PASS and `production_claimed=false`.
- Status-source correction is on draft PR #86
  (`codex/jobhuntbot-status-registration`); it contains only the VPS3 and
  email-pause registration. Do not replace the VPS3 collector with a stale
  VPS1 version.
- The JobHuntBot source and email fail-closed guard are on draft PR #176
  (`codex/jobhuntbot-online-v030-r2`). The target's historical
  `ACCEPTANCE_COMMIT` value must not be used as a completion receipt because
  its associated root acceptance result is absent.

## 2026-08-11 anti-burst deployment receipt

- Commit `6e8404f3b` is deployed to the VPS3 release directory. The release
  directory is intentionally a deployment copy rather than a Git checkout;
  the exact committed files were staged there before the normal backup,
  build, Alembic, Web, Scheduler and Worker deployment sequence.
- A disposable VPS3 container ran the deployed source with a read-only mount
  and `--network none`: all 36 tests passed. No SMTP connection, real mailbox,
  browser acceptance, or public registration action occurred in that run.
- Runtime readback reports `email_min_interval_seconds=1800`,
  `email_max_per_user_per_24h=3`, and `allow_registration=false`.
  HTTPS `/readyz` is healthy with `refresh_hours=6`, public `/register`
  remains HTTP 403, and encrypted-backup verification passed.
- `deploy/acceptance.sh` was invoked only with the live default opt-out. It
  exited 2 before evidence cleanup or browser startup, reporting that no email
  had been sent. The root `ACCEPTANCE_RESULT.json` remains absent.

## Next authorized action

The anti-burst controls are deployed and public registration stays closed. A
future real-email production acceptance requires two dedicated acceptance
inboxes, `ALLOW_REGISTRATION=true`,
`RUN_REAL_EMAIL_ACCEPTANCE=true`, and a fresh
`REAL_EMAIL_ACCEPTANCE_RUN_ID`; only then may T06/T08 be rerun and a new root
`ACCEPTANCE_RESULT.json` be considered for T10.
