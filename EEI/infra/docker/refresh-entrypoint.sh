#!/bin/sh
# EEI refresh worker entrypoint.
#
# Order: wait for DB -> run migrations -> ensure the sec_edgar source row exists
# -> SAFETY GUARD (refuse to run if the system-of-record is empty, so a first
# publish can never wipe the live Cloudflare D1) -> exec the refresh command.
#
# Everything here is idempotent and safe to re-run on container restart.
set -eu

echo "[entrypoint] EEI refresh worker starting (user=$(id -un), cwd=$(pwd))"

: "${DATABASE_URL:?DATABASE_URL is required}"
# SEC fair-access identity; the pipeline fails closed without it (good), but we
# surface it early so a misconfig is obvious in the logs.
if [ -z "${SEC_USER_AGENT:-}" ]; then
  echo "[entrypoint] WARNING: SEC_USER_AGENT is unset — enrich/gleif will fail closed until it is set."
fi

# 1) Wait for Postgres to accept connections (capped DB can be slow to start).
echo "[entrypoint] waiting for database ..."
python - <<'PY'
import os, sys, time
import psycopg
url = os.environ["DATABASE_URL"]
deadline = time.time() + 120
while True:
    try:
        with psycopg.connect(url, connect_timeout=5) as c:
            c.execute("SELECT 1")
        print("[entrypoint] database is up")
        break
    except Exception as exc:  # noqa: BLE001
        if time.time() > deadline:
            print(f"[entrypoint] FATAL: database not reachable: {exc}", file=sys.stderr)
            sys.exit(1)
        time.sleep(2)
PY

# 2) Migrations (idempotent; applies only pending versions). Skippable so a
#    second co-tenant container (the watcher) doesn't race the refresh
#    container's migrate on first boot — the refresh service owns migrations.
if [ "${EEI_SKIP_MIGRATE:-0}" = "1" ]; then
  echo "[entrypoint] EEI_SKIP_MIGRATE=1 — skipping migrations (owned by the refresh service)"
else
  echo "[entrypoint] applying migrations ..."
  python scripts/migrate.py upgrade
fi

# 3) Ensure the sec_edgar source row exists. collect_universe/enrich_sec call
#    source_id_for('sec_edgar') and fail if it is missing; on a freshly migrated
#    DB (no dump restored yet) it will not exist. ON CONFLICT keeps it idempotent
#    and never disturbs a restored dump.
echo "[entrypoint] ensuring sec_edgar source row ..."
python - <<'PY'
import os
import psycopg
with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as conn:
    conn.execute(
        """
        INSERT INTO sources (code, name, base_url, source_tier, active)
        VALUES ('sec_edgar', 'SEC EDGAR official filings',
                'https://data.sec.gov', 1, true)
        ON CONFLICT (code) DO NOTHING
        """
    )
    conn.commit()
    n = conn.execute(
        "SELECT count(*) FROM entities WHERE status = 'research_target'"
    ).fetchone()[0]
    print(f"[entrypoint] research_target entities in system-of-record: {n}")
PY

# 4) SAFETY GUARD — never let a first publish wipe the live D1.
#    publish_to_cloud_channel DELETEs then re-inserts the whole D1 surface from
#    the local export. If this DB is empty, the export is empty and a republish
#    would blow away the live graph. Refuse to start unless the DB is seeded
#    (restore the pg_dump first), or the operator explicitly opts out.
if [ "${EEI_ABORT_IF_EMPTY_UNIVERSE:-1}" = "1" ]; then
  COUNT="$(python - <<'PY'
import os, psycopg
with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as c:
    print(c.execute("SELECT count(*) FROM entities WHERE status='research_target'").fetchone()[0])
PY
)"
  if [ "${COUNT:-0}" -lt "1" ]; then
    echo "[entrypoint] FATAL: system-of-record is EMPTY (0 research_target entities)."
    echo "[entrypoint] Refusing to start the refresh loop: the first publish would DELETE the live"
    echo "[entrypoint] Cloudflare D1 surface and replace it with nothing."
    echo "[entrypoint] Restore the local pg_dump into this database first (see RUNBOOK), or set"
    echo "[entrypoint] EEI_ABORT_IF_EMPTY_UNIVERSE=0 to intentionally bootstrap from scratch."
    exit 2
  fi
fi

echo "[entrypoint] exec: $*"
exec "$@"
