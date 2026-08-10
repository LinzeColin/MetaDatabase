# Handoff to Codex Delivery Agent

Read `START_HERE.md` first. The source Candidate, frozen contract, DAG, deployment scripts and local evidence are in this package. The prior invalid v0.3 ZIP is superseded and must not be used.

Do not repeat product research. NitroSend is removed: do not wait for it, connect it, or restore it. Observe latest repository and infrastructure, then execute the first unsatisfied task. Preserve current data and a rollback point. If standard SMTP is not yet available, keep public registration closed and continue every non-email task. Secrets stay outside Git and evidence. Run `deploy/acceptance.sh`; do not report completion without the generated production `ACCEPTANCE_RESULT.json`.

## 2026-08-10 live execution checkpoint

- T00–T05 are complete on the real `https://jobhunt.linzezhang.com` deployment:
  PostgreSQL/Alembic head is live; the isolated v0.2 backup migrated with
  readback; Web, Scheduler and Worker are running; old v0.2 traffic is stopped.
  Repeated HTTPS health checks report `0.3.0`; readiness reports exactly six
  hours. Runtime state proved one completed six-hour discovery interval, and
  the synthetic authorized-source probe passed for Remotive, Arbeitnow and
  Jobicy.
- Delivery adaptations include a unique private PostgreSQL network alias,
  immutable read-only SQLite source access for the T01 snapshot, explicit
  `python3` use for host scripts, a no-Web first-cutover backup route, a durable
  legacy rollback reference, and disabled inherited HTTP healthchecks for the
  non-HTTP Scheduler/Worker loops. The application image also includes
  `deploy/`, so the deployed mail-deferment probe is executable. Local taskpack
  verification, the deployed mail-deferment probe, and 27 pytest tests pass.
- `ALLOW_REGISTRATION=false`; standard SMTP is not configured, so real
  registration/verification/reset and full HTTPS acceptance remain
  `EMAIL_ONLY_BLOCKED`. A host-local SMTP bridge was discovered but is backed
  by a `nitrosend_secret` mount, so it is explicitly excluded; NitroSend
  remains absent from this project.
- The production-browser entrypoint now returns a structured
  `EMAIL_ONLY_BLOCKED` preflight before it creates a synthetic account or sends
  email when registration, standard SMTP, an acceptance recipient or an IMAP
  mailbox is missing. This is not production acceptance and cannot create a
  root `ACCEPTANCE_RESULT.json`. The real target preflight wrote
  `evidence/target-email.json` with all four conditions absent and both
  `email_delivery_sent=false` and `synthetic_accounts_created=false`.
- DeepSeek has no configured platform key. The probe reports `BLOCKED` without
  exposing a key and the deterministic fallback passed; do not migrate or reuse
  the old user key without separate authorization.
- `production_state_probe.py` now claims production only when its own state
  checks pass; a failing state slice cannot be presented as a production-ready
  result merely because it ran inside the production environment.
- Private-Database received a non-PII v0.3 runtime projection through the
  authorized local client. Server-side recurring sync cannot be enabled because
  its GitHub client is not authenticated. R2 has no configured remote and stays
  disabled under the zero-charge policy; the existing free-tier guard reports
  storage at 56% of its allowance, so no new periodic R2 load is permitted.
  A current v0.3 encrypted backup passed verify-only recovery. A
  status-registration change is prepared and validated in the separate
  `LinzeHomeHub` worktree, but must not be deployed before core acceptance PASS.
  The optional operations probe now sets `production_claimed` only when all of
  its checks pass, so a blocked status/Private-Database/R2 integration cannot
  be mistaken for a production-complete claim.
