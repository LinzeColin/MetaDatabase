# Handoff to Codex Delivery Agent

Read `START_HERE.md` first. The source candidate, frozen contract, DAG,
deployment scripts, and local evidence are in this package. The prior invalid
v0.3 ZIP is superseded and must not be used.

Do not repeat product research. NitroSend is removed: do not wait for it,
connect it, or restore it. Observe the latest repository and infrastructure,
then execute the first unsatisfied task. Preserve current data and a rollback
point. Secrets stay outside Git and evidence.

## 2026-08-11 VPS3 checkpoint — email safety hold

- The live target is VPS3 (`vps-bab7f9dc`) at
  `https://jobhunt.linzezhang.com`. PostgreSQL, Web, Scheduler, and Worker are
  healthy; HTTPS `/readyz` reports `status=ready` and `refresh_hours=6`.
- The Owner permits controlled email but rejected the earlier burst of three
  messages in ten minutes. Treat that as a hard safety boundary: never
  auto-retry a real email acceptance run and never send at a shorter cadence.
- One controlled real acceptance attempt was made after SMTP/IMAP preflight.
  It sent exactly one genuine verification message to the dedicated synthetic
  A recipient, then completed verification, onboarding, recommendations, and
  application preparation for that synthetic account. The process was stopped
  before any second request after it did not finish promptly. Database
  aggregate evidence confirms exactly one new `EmailDelivery` with `sent`
  status; no second or third delivery was made.
- The exact synthetic A account was deleted by its dedicated recipient lookup;
  a follow-up count is zero. Delivery audit rows remain intentionally. No B
  account was created. Do not delete any wider user set or erase delivery
  audit records.
- Live `.env` has `ALLOW_REGISTRATION=true` because standard SMTP exists, but
  `RUN_REAL_EMAIL_ACCEPTANCE=false`. The application enforces a 30-minute
  per-recipient interval and a maximum of three deliveries per 24 hours.
  The persisted real-email guard has consumed the prior run ID and holds a
  24-hour cooldown; it must not be cleared or bypassed.
- Commit `6e8404f3b` deployed the application-level anti-burst controls.
  Commit `b0cc17d81` deployed bounded IMAP connection/retry behavior. Commit
  `70c728835` is synchronized into the VPS3 release copy and requires every
  future acceptance request to wait 30 minutes plus a non-removable 30-second
  boundary buffer (configurable only up to 300 seconds). This avoids a
  millisecond collision with the application limiter. These updates do not
  send email and do not require a service restart.
- Commit `97b522dd4` is deployed through the normal encrypted
  backup, Alembic, and service-restart path. PostgreSQL is now at
  `0002_delivery_lookup`; new delivery audit rows persist the existing keyed
  email lookup so account deletion and re-registration cannot reset the
  recipient limit. Historical rows whose user FK had already been cleared
  remain intentionally unlinked: recovering their lookup from a masked
  address would weaken the privacy boundary. Future acceptance must use fresh
  synthetic recipients.
- Commit `8ee2e3690` is deployed through the same backup/build/restart path.
  It reserves every `production_claimed=true` result for the root
  `ACCEPTANCE_RESULT.json` on the production target: state, operations,
  migration, and browser-email component evidence now remain explicitly
  non-final, and the finalizer rejects any non-root evidence that claims
  production. An isolated, network-disabled source suite passed before deploy;
  the post-deploy state probe is `PASS` with `production_claimed=false`.
  The fresh predeploy encrypted backup is structurally readable.
- Commit `32c14ced2` is deployed through the same backup/build/restart path.
  Resume parsing now leaves unknown role families, locations, and work modes
  empty instead of supplying defaults. Both onboarding and settings enforce
  explicit server-side confirmation of work authorization, current/future
  Sponsorship, location, role, and work mode; explicit `uncertain`
  Sponsorship remains a pending qualification when a job provides none.
  Tenant negative coverage now also proves private manual jobs, application
  evidence/notes, and exports do not cross accounts. The isolated,
  network-disabled source suite and post-deploy state/backup readbacks passed.
- Commit `9b983a2d0` is deployed through the same backup/build/restart path.
  An administrator-set user AI quota of `0` now blocks DeepSeek before a
  provider client can be created; it no longer falls through to the platform
  default quota. The platform status assertion confirms that it reports only
  configuration state and limits, never a DeepSeek Secret. The full isolated,
  network-disabled source suite, HTTPS ready readback, state probe, and fresh
  encrypted-backup verify-only readback passed. This deployment does not send
  email.
- A read-only, recipient-free delivery audit found 28 historical `sent` rows in
  the 48-hour window ending `2026-08-11T02:36:00Z`, including a maximum of six
  messages in one ten-minute bucket. That prior burst is unacceptable. It is
  historical evidence only: the post-deployment count is zero, the persisted
  cooldown remains active, and no automatic retry is permitted.
- A disposable VPS3 container ran all 42 source tests with a read-only source
  mount and `--network none`; all passed. The target taskpack verifier also
  passes in deployment-runtime mode. A disposable PostgreSQL 0001-to-0002
  upgrade, downgrade, and re-upgrade backfilled only a synthetic keyed lookup;
  the live encrypted predeploy backup is structurally readable. No SMTP
  connection, browser acceptance, or public registration action occurred in
  those checks.
- There is no root `ACCEPTANCE_RESULT.json`. The prior partial mail run is not
  a production receipt: T10 remains incomplete and a full-production PASS
  must not be claimed.

## Verified non-email state

- PostgreSQL migration, restart readback, encrypted-backup verification,
  platform DeepSeek probe without key exposure, authorized job discovery, and
  strict six-hour scheduling have target evidence. The post-deploy state probe
  passed at `0002_delivery_lookup` with the exact six-hour invariant. NitroSend
  is absent and prohibited, not a blocker.
- T09 remains non-authoritative operational evidence only. The corrected VPS3
  Status registration is on draft LinzeHomeHub PR #86 at `484aedc`
  (`codex/jobhuntbot-status-registration`); its current `dual-plane`,
  `deterministic`, and `browser` GitHub checks all passed. A current public
  snapshot readback returns `registered=false` for JobHuntBot Online, so it is
  still not deployed. No public Status deployment was executed. Do not treat
  the draft as deployed evidence or replace it with a stale VPS1 collector.
- Private-Database readback is current at `2026-08-11T05:07:46Z` under
  `Private-MetaDatabase/JobHuntBotOnline/operations/v0.3.0/latest.json` with
  schema `jobhuntbot-ops-projection-v2`, `EMAIL_ONLY_BLOCKED`,
  `production_claimed=false`, deployed code commit `9b983a2d0`, verified
  predeploy backup, and no business data, PII, or Secrets. PostgreSQL remains
  the sole business-data authority.
- The deployed `evidence/target-private-db.json` is a deliberately narrower
  readback adapter: its subsystem `verdict=PASS` means Private-Database sync
  and readback succeeded, while `overall_product_verdict=EMAIL_ONLY_BLOCKED`
  and `production_claimed=false` preserve the real overall state. Do not copy
  the overall verdict into the subsystem verdict: `tools/ops_probe.py` would
  correctly treat that as a blocked PDB integration. A current probe confirms
  PDB `PASS`, Status `BLOCKED`, R2 `NOT_CONFIGURED`, and overall noncritical
  `BLOCKED`; no PII, business data, or Secret was written to the adapter.
- R2 is deliberately `NOT_CONFIGURED`. No JobHuntBot-specific bucket or
  credential is authorized, and no R2 operation, InfrequentAccess setting,
  recurring task, or cross-project credential reuse was performed. The target
  ops probe records Private-Database `PASS`, Status `BLOCKED`, and R2
  `NOT_CONFIGURED`; its overall result is noncritical `BLOCKED` with
  `production_claimed=false`.
- The JobHuntBot source and all email safeguards are on draft PR #176
  (`codex/jobhuntbot-online-v030-r2`). Do not mark it ready, merge it, or use
  an old `ACCEPTANCE_COMMIT` value as a completion receipt.

## Next authorized action

Do not send another email automatically. After the stored cooldown has
expired, obtain a deliberate go-ahead, generate a fresh run ID and fresh
dedicated synthetic A/B recipients, preflight again, and run one paced
acceptance attempt only. If it does not reach a real root
`ACCEPTANCE_RESULT.json` with `core_verdict=PASS` and no open P0/P1, leave the
result as `EMAIL_ONLY_BLOCKED`/non-final rather than claiming completion.

The remaining T09 status gate also needs PR #86 to be reviewed, deployed, and
observed in the public snapshot. Do not claim this noncritical operation item
is complete before that live readback.
