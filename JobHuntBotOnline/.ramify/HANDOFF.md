# Handoff to Codex Delivery Agent

Read `START_HERE.md` first. The source Candidate, frozen contract, DAG, deployment scripts and local evidence are in this package. The prior invalid v0.3 ZIP is superseded and must not be used.

Do not repeat product research. NitroSend is removed: do not wait for it, connect it, or restore it. Observe latest repository and infrastructure, then execute the first unsatisfied task. Preserve current data and a rollback point. If standard SMTP is not yet available, keep public registration closed and continue every non-email task. Secrets stay outside Git and evidence. Do not run `deploy/acceptance.sh`, browser E2E, or any other real-email action unless the Owner grants a new one-time authorization and explicitly sets `RUN_REAL_EMAIL_ACCEPTANCE=true`; the script fails closed without that flag.

## 2026-08-11 VPS3 operational checkpoint — email safety pause

- The live target is VPS3 (`vps-bab7f9dc`) at
  `https://jobhunt.linzezhang.com`. PostgreSQL, Web, Scheduler and Worker are
  running; `/readyz` reports `refresh_hours=6`.
- The Owner prohibited further real email. `ALLOW_REGISTRATION=false` and
  `RUN_REAL_EMAIL_ACCEPTANCE=false` are live and the public `/register` route
  is closed. T06 and the real-email portion of T08 are
  `EMAIL_ONLY_BLOCKED`; do not create test users, send verification/reset
  messages, or claim an email was sent.
- A prior root `ACCEPTANCE_RESULT.json` was invalidated and removed after the
  safety pause. There is currently no fresh target root production PASS, so
  T10 must not be marked complete and no full-production claim is allowed.
- All verified non-email functions remain available: PostgreSQL migration,
  restart readback, encrypted-backup verification, platform DeepSeek probe
  without key exposure, authorized job discovery, and the strict six-hour
  refresh are recorded by target evidence. NitroSend is absent and remains
  prohibited.
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

## Next authorized action

Continue non-email maintenance only. A future real-email production acceptance
requires a new explicit Owner authorization, `ALLOW_REGISTRATION=true`, and
`RUN_REAL_EMAIL_ACCEPTANCE=true`; only then may T06/T08 be rerun and a new
root `ACCEPTANCE_RESULT.json` be considered for T10.
