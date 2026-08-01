# SA-507 Phase B — Private-Database facts

## Goal

For one already-completed, non-user-data Social Archive fact in the production
Runtime Journal, prove the authoritative clone-free Private-Database path:
`ingest` followed by strict `verify`, with the outbox marked delivered only
after verification.

## In scope

- Production Runtime Journal, official `private_db_client.py`, and the
  `scripts/sync_private_database.py --once` path.
- The minimum credential handoff repair required to make that path real:
  a root-only `private_database_token` source secret, systemd
  `LoadCredential=`, and `GH_TOKEN` injection by the Python subprocess rather
  than an environment variable containing a file path.
- One bounded, idempotent synchronization pass and one no-op repeat check.
- Sanitized evidence that contains counts, statuses, command identities, and
  hashes only; it must not contain secrets, user content, URLs with sensitive
  query values, or absolute production host identifiers.

## Explicitly out of scope

- `backup.py`, `restore.py`, object replication, GitHub Draft releases,
  source pushes/tags, deployments, timers, connector/destination authorization,
  and any data deletion.
- Private-Database clone, checkout, Git commits, or direct local writes.
- Mounting the new credential into the Core/worker/CLI containers, or reusing
  the Vault-only archive token for `Private-Database`.

## Preconditions

1. The production `SOCIAL_ARCHIVE_PRIVATE_DB_CLIENT` resolves to the official
   clone-free client, and a dedicated `LinzeColin/Private-Database` token is
   available as the root-only `private_database_token` source secret.
2. The production Runtime Journal has at least one completed fact whose three
   object-replica receipts are all `verified`.
3. The run is performed on the production data root, not in this worktree.

## Validation

1. Read-only preflight verifies client/runtime availability and never outputs a
   secret value.
2. Focused tests prove a missing/invalid credential fails before Runtime
   mutation and that only the systemd credential copy reaches the `gh`
   subprocess.
3. `sync_private_database.py --once` reports `PASS` and a strict complete
   ledger verification.
4. A second identical run reports `NO_CHANGE` with the completed fact already
   delivered.
5. The official client `verify Private-MetaDatabase` result is captured in
   sanitized form and its count relationship is strict.

## Risks, rollback, and stop condition

The only intended durable mutations are installing the corrected unit contract,
the root-only token file, the generated non-secret host environment, and an
idempotent fact ingest plus Runtime Outbox state. Any missing client/auth,
missing eligible fact, failed ingest, or non-complete verification stops the
phase immediately; no backup, recovery, or release action is permitted. A
failed verify must leave the fact pending for safe retry rather than claiming
delivery.
