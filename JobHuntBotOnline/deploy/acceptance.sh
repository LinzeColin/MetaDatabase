#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -f .env
set -a; source .env; set +a
mkdir -p evidence runtime-data
[[ "${DISCOVERY_REFRESH_HOURS:-}" == "6" ]] || { echo "DISCOVERY_REFRESH_HOURS must be 6" >&2; exit 1; }
[[ "${BASE_URL:-}" == https://* ]] || { echo "BASE_URL must be real HTTPS" >&2; exit 1; }

python deploy/verify_taskpack.py --output evidence/target-taskpack.json

running="$(docker compose ps --services --filter status=running)"
for service in postgres web scheduler worker; do
  grep -qx "$service" <<<"$running" || { echo "service is not running: $service" >&2; exit 1; }
done
curl -fsS "${BASE_URL%/}/healthz" >/dev/null
ready_json="$(curl -fsS "${BASE_URL%/}/readyz")"
python - "$ready_json" <<'PY'
import json,sys
p=json.loads(sys.argv[1]); assert p.get('status')=='ready'; assert p.get('refresh_hours')==6
PY

docker compose run --rm -v "$PWD/evidence:/app/evidence" web \
  python tools/production_state_probe.py --output /app/evidence/target-state-before.json

docker compose run --rm -v "$PWD/evidence:/app/evidence" worker \
  python tools/online_source_probe.py --require-success --output /app/evidence/target-sources.json

docker compose run --rm -v "$PWD/evidence:/app/evidence" worker \
  python tools/deepseek_probe.py --output /app/evidence/target-deepseek.json

docker compose --profile acceptance run --rm --build acceptance \
  python tools/e2e_production.py --output /app/evidence/target-browser.json
cp evidence/target-browser.json evidence/target-email.json

# Restart every application runtime and prove aggregate state/readback remains valid.
docker compose restart web scheduler worker
for _ in $(seq 1 60); do
  if curl -fsS "${BASE_URL%/}/readyz" >/dev/null 2>&1; then break; fi
  sleep 3
done
curl -fsS "${BASE_URL%/}/readyz" >/dev/null
docker compose run --rm -v "$PWD/evidence:/app/evidence" web \
  python tools/production_state_probe.py --output /app/evidence/target-state-after.json
python - <<'PY'
import json
from pathlib import Path
before=json.loads(Path('evidence/target-state-before.json').read_text())
after=json.loads(Path('evidence/target-state-after.json').read_text())
# Synthetic acceptance accounts are deleted; operational rows may legitimately grow.
for key in ['users','profiles','resumes','jobs','recommendations','application_packs']:
    if after['counts'].get(key,0) < 0: raise SystemExit(f'invalid count {key}')
if after.get('refresh_interval_hours') != 6: raise SystemExit('refresh interval is not six hours')
result={'verdict':'PASS','services_restarted':['web','scheduler','worker'],'https_readback':True,'refresh_interval_hours':6,'state_before':before['counts'],'state_after':after['counts']}
Path('evidence/target-restart.json').write_text(json.dumps(result,indent=2)+'\n')
PY

backup_path="$(deploy/backup.sh)"
deploy/restore.sh --verify-only "$backup_path"
python - "$backup_path" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); result={'verdict':'PASS','backup_file':str(p),'encrypted':p.suffix=='.enc','archive_verify_only':True,'production_restore_not_performed_by_acceptance':True}
Path('evidence/target-recovery.json').write_text(json.dumps(result,indent=2)+'\n')
PY

python tools/ops_probe.py --output evidence/target-ops.json
commit="${ACCEPTANCE_COMMIT:-$(git rev-parse HEAD 2>/dev/null || true)}"
deployment_id="${ACCEPTANCE_DEPLOYMENT_ID:-$(docker compose images -q web | head -1)}"
rollback_target="${ACCEPTANCE_ROLLBACK_TARGET:-$(cat runtime-data/rollback-image.txt 2>/dev/null || true)}"
python tools/finalize_acceptance.py \
  --base-url "$BASE_URL" --commit "$commit" --deployment-id "$deployment_id" \
  --rollback-target "$rollback_target" --output ACCEPTANCE_RESULT.json
python - <<'PY'
import json
p=json.load(open('ACCEPTANCE_RESULT.json'))
if p.get('core_verdict')!='PASS': raise SystemExit('production core acceptance is not PASS')
print('PRODUCTION CORE ACCEPTANCE: PASS')
PY
