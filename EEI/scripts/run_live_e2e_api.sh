#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

if [[ "${EEI_ALLOW_DB_RESET_FOR_E2E:-}" != "1" ]]; then
  echo "ERROR: EEI_ALLOW_DB_RESET_FOR_E2E=1 is required for live E2E database reset" >&2
  exit 1
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is required for live E2E API" >&2
  exit 1
fi

# Isolation guard (2026-07-16 incident): the live E2E stack used to
# downgrade/reseed whatever DATABASE_URL pointed at and once wiped the local
# production database (owner-signed published facts, the 2016+ backfill and
# the job queue; restored from the S7PDT03 backup). The reset below now runs
# against a DEDICATED database derived from DATABASE_URL - the production
# database is never touched by this script.
E2E_DB_NAME="${EEI_E2E_DB_NAME:-eei_e2e}"
E2E_DATABASE_URL=$(.venv/bin/python - "$DATABASE_URL" "$E2E_DB_NAME" <<'PY'
import sys
from urllib.parse import urlparse, urlunparse

url, db_name = sys.argv[1], sys.argv[2]
parts = urlparse(url)
print(urlunparse(parts._replace(path=f"/{db_name}")))
PY
)

if [[ "$E2E_DATABASE_URL" == "$DATABASE_URL" ]]; then
  echo "ERROR: E2E database URL must differ from the production DATABASE_URL" >&2
  exit 1
fi

.venv/bin/python - "$DATABASE_URL" "$E2E_DB_NAME" <<'PY'
import sys
from urllib.parse import urlparse, urlunparse

import psycopg

url, db_name = sys.argv[1], sys.argv[2]
admin_url = urlunparse(urlparse(url)._replace(path="/postgres"))
with psycopg.connect(admin_url, connect_timeout=10, autocommit=True) as conn:
    exists = conn.execute(
        "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
    ).fetchone()
    if not exists:
        conn.execute(f'CREATE DATABASE "{db_name}"')
        print(f"created dedicated E2E database: {db_name}")
    else:
        print(f"dedicated E2E database present: {db_name}")
PY

export DATABASE_URL="$E2E_DATABASE_URL"
echo "live E2E stack bound to dedicated database: ${E2E_DB_NAME}"

.venv/bin/python scripts/migrate.py downgrade --all
.venv/bin/python scripts/migrate.py upgrade
.venv/bin/python scripts/load_seed_catalogs.py
.venv/bin/python scripts/load_synthetic_fixtures.py
.venv/bin/python scripts/load_curated_ingestion_anchors.py
.venv/bin/python scripts/load_sec_normalized_fixtures.py \
  --mode fixture \
  --database-url "${DATABASE_URL}" \
  --allow-database-write

exec .venv/bin/python -m uvicorn apps.api.app.main:app --host 127.0.0.1 --port 8000
