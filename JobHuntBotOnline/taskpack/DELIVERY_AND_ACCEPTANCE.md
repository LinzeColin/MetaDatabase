# Delivery and Acceptance

## Delivery sequence

1. Run `python3 tools/verify_taskpack.py --output evidence/predeploy-taskpack.json`.
2. Observe latest repository/environment and capture `evidence/target-current-truth.json`.
3. Create rollback point and verified backup before any migration.
4. Generate `.env`. NitroSend is removed. If any standard SMTP relay is already available, inject it securely; otherwise keep `ALLOW_REGISTRATION=false` and continue every non-email task. Inject DeepSeek/acceptance-mailbox secrets outside Git.
5. Apply Alembic. When a v0.2 database exists, run `tools/migrate_v02_sqlite.py` before switching traffic.
6. Deploy Web, Scheduler and Worker; absence of NitroSend or SMTP must not stop these steps.
7. Before full public production acceptance, configure any standard SMTP relay, set `ALLOW_REGISTRATION=true`, and run `deploy/acceptance.sh` on the real HTTPS deployment. Real-mail acceptance is one-shot: it needs `RUN_REAL_EMAIL_ACCEPTANCE=true` plus a fresh `REAL_EMAIL_ACCEPTANCE_RUN_ID`.
8. Only after core PASS, register operations and commit/push the exact Candidate.

For the observed v0.2 single-container deployment, set `LEGACY_COMPOSE_FILE`
and `LEGACY_SERVICE=app` while migrating. The deploy script waits until the
PostgreSQL migration is ready, stops only the old public service immediately
before starting the new routed Web service, and restores that old service if
the new runtime cannot become ready. Clear the legacy settings only after the
v0.3 recovery gate is complete.

For a v0.2 SQLite source operating with WAL, restore the fresh encrypted T01
backup into an isolated migration snapshot and set `V02_SQLITE_PATH` and
`V02_DATA_ROOT` to that snapshot. Do not mount the live SQLite main file by
itself: its WAL may contain uncheckpointed rows and is not a migration source.

## Runtime verification boundary

`tools/verify_taskpack.py` is strict by default: a distributable TaskPack must
not carry runtime Secret files or undeclared generated output. Deployment
scripts invoke it with `--deployment-runtime` only after `.env` has been
created. That mode permits exactly `.env`, `OWNER_LOGIN.txt`,
`secrets/postgres_password.txt`, `runtime-data/` output, and the DAG-defined
target evidence; each permitted Secret file must be mode `0600` or `0400` and
remains outside Git. Any other inventory drift still fails verification.

## Production acceptance inputs

The target `.env` uses provider-neutral SMTP; NitroSend is not accepted or required. Full production acceptance must provide two independent, dedicated acceptance inboxes explicitly. Automatic plus-alias fallback is disabled, and two addresses with the same local-part root (for example `owner+one@…` and `owner+two@…`) are rejected before any mail is sent. This conservatively prevents a single inbox from receiving the three lifecycle messages.

- `ACCEPTANCE_EMAIL_A`, `ACCEPTANCE_EMAIL_B`, `ACCEPTANCE_ACCOUNT_PASSWORD`
- `ACCEPTANCE_IMAP_HOST`, `ACCEPTANCE_IMAP_PORT`, `ACCEPTANCE_IMAP_USERNAME`, `ACCEPTANCE_IMAP_PASSWORD`
- `ACCEPTANCE_IMAP_FOLDER`, `ACCEPTANCE_IMAP_CONNECT_TIMEOUT_SECONDS=20`, `RUN_REAL_EMAIL_ACCEPTANCE=true`, fresh `REAL_EMAIL_ACCEPTANCE_RUN_ID`
- `ACCEPTANCE_MIN_EMAIL_GAP_SECONDS>=1800`, `ACCEPTANCE_EMAIL_REQUEST_SAFETY_SECONDS=30`, `ACCEPTANCE_REAL_EMAIL_COOLDOWN_HOURS>=24`

The harness reserves at most three real messages, waits at least 30 minutes plus a 30-second application-rate-limit buffer between requests, bounds every IMAP connection to 20 seconds, and persists a 24-hour cooldown before it opens Chromium. These are test credentials, not candidate data. They are never copied into evidence.

## Verdict

- `PASS`: every critical Acceptance passes on the exact deployment, no P0/P1.
- `FAIL`: a required behavior is reproducibly wrong.
- `BLOCKED`: real permission, identity, Secret, network or evidence is unavailable.
- Local evidence can support implementation quality but cannot become a production verdict.
