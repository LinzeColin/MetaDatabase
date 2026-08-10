# Delivery and Acceptance

## Delivery sequence

1. Run `python tools/verify_taskpack.py --output evidence/predeploy-taskpack.json`.
2. Observe latest repository/environment and capture `evidence/target-current-truth.json`.
3. Create rollback point and verified backup before any migration.
4. Generate `.env`, inject SMTP/DeepSeek/IMAP secrets, and keep all secret values outside Git.
5. Apply Alembic. When a v0.2 database exists, run `tools/migrate_v02_sqlite.py` before switching traffic.
6. Deploy Web, Scheduler and Worker.
7. Run `deploy/acceptance.sh` on the real HTTPS deployment.
8. Only after core PASS, register operations and commit/push the exact Candidate.

## Production acceptance inputs

The target `.env` must provide dedicated disposable acceptance mailboxes or plus aliases:

- `ACCEPTANCE_EMAIL_A`, `ACCEPTANCE_EMAIL_B`, `ACCEPTANCE_ACCOUNT_PASSWORD`
- `ACCEPTANCE_IMAP_HOST`, `ACCEPTANCE_IMAP_PORT`, `ACCEPTANCE_IMAP_USERNAME`, `ACCEPTANCE_IMAP_PASSWORD`
- `ACCEPTANCE_IMAP_FOLDER`, optional `ACCEPTANCE_EMAIL_PLUS_ALIAS=true`

These are test credentials, not candidate data. They are never copied into evidence.

## Verdict

- `PASS`: every critical Acceptance passes on the exact deployment, no P0/P1.
- `FAIL`: a required behavior is reproducibly wrong.
- `BLOCKED`: real permission, identity, Secret, network or evidence is unavailable.
- Local evidence can support implementation quality but cannot become a production verdict.
