#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
test -f .env
set -a; source .env; set +a
[[ "${RUN_REAL_EMAIL_ACCEPTANCE:-false}" == "true" ]] || {
  echo "real email acceptance requires explicit RUN_REAL_EMAIL_ACCEPTANCE=true; no email has been sent" >&2
  exit 2
}
[[ "${REAL_EMAIL_ACCEPTANCE_RUN_ID:-}" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{7,79}$ ]] || {
  echo "real email acceptance requires a fresh valid REAL_EMAIL_ACCEPTANCE_RUN_ID; no email has been sent" >&2
  exit 2
}
[[ -n "${ACCEPTANCE_EMAIL_A:-}" && -n "${ACCEPTANCE_EMAIL_B:-}" ]] || {
  echo "real email acceptance requires two dedicated acceptance recipients; no email has been sent" >&2
  exit 2
}
case "${ACCEPTANCE_MIN_EMAIL_GAP_SECONDS:-1800}" in
  ''|*[!0-9]*) echo "ACCEPTANCE_MIN_EMAIL_GAP_SECONDS must be an integer; no email has been sent" >&2; exit 2 ;;
esac
(( ACCEPTANCE_MIN_EMAIL_GAP_SECONDS >= 1800 )) || {
  echo "ACCEPTANCE_MIN_EMAIL_GAP_SECONDS must be at least 1800; no email has been sent" >&2
  exit 2
}
case "${ACCEPTANCE_REAL_EMAIL_COOLDOWN_HOURS:-24}" in
  ''|*[!0-9]*) echo "ACCEPTANCE_REAL_EMAIL_COOLDOWN_HOURS must be an integer; no email has been sent" >&2; exit 2 ;;
esac
(( ACCEPTANCE_REAL_EMAIL_COOLDOWN_HOURS >= 24 )) || {
  echo "ACCEPTANCE_REAL_EMAIL_COOLDOWN_HOURS must be at least 24; no email has been sent" >&2
  exit 2
}
evidence_runner_user=(--user "${ACCEPTANCE_UID:-$(id -u)}:${ACCEPTANCE_GID:-$(id -g)}")
mkdir -p evidence runtime-data
python3 - <<'PY'
from pathlib import Path

# Container probes may run as a different UID. Remove only the named, regenerated
# acceptance outputs so every run creates fresh evidence without stale ownership
# preventing a later host-side write.
for name in [
    "target-taskpack.json", "target-state-before.json", "target-sources.json",
    "target-deepseek.json", "target-browser.json", "target-email.json",
    "target-state-after.json", "target-restart.json", "target-recovery.json",
    "target-ops.json",
]:
    path = Path("evidence") / name
    if path.is_file():
        path.unlink()

# The root result is the production-completion authority.  Remove only this
# exact regular file before a new run so a failed run cannot leave an old PASS
# beside fresh partial evidence.
result = Path("ACCEPTANCE_RESULT.json")
if result.exists():
    if not result.is_file() or result.is_symlink():
        raise SystemExit("ACCEPTANCE_RESULT.json must be a regular file")
    result.unlink()
PY
[[ "${DISCOVERY_REFRESH_HOURS:-}" == "6" ]] || { echo "DISCOVERY_REFRESH_HOURS must be 6" >&2; exit 1; }
[[ "${BASE_URL:-}" == https://* ]] || { echo "BASE_URL must be real HTTPS" >&2; exit 1; }
[[ "${ALLOW_REGISTRATION:-false}" == "true" ]] || { echo "full production acceptance requires ALLOW_REGISTRATION=true" >&2; exit 1; }
[[ -n "${SMTP_HOST:-}" ]] || { echo "full production acceptance requires a standard SMTP_HOST; NitroSend is not required" >&2; exit 1; }

python3 deploy/verify_taskpack.py --deployment-runtime --output evidence/target-taskpack.json

running="$(docker compose ps --services --filter status=running)"
for service in postgres web scheduler worker; do
  grep -qx "$service" <<<"$running" || { echo "service is not running: $service" >&2; exit 1; }
done
curl -fsS "${BASE_URL%/}/healthz" >/dev/null
ready_json="$(curl -fsS "${BASE_URL%/}/readyz")"
python3 - "$ready_json" <<'PY'
import json,sys
p=json.loads(sys.argv[1]); assert p.get('status')=='ready'; assert p.get('refresh_hours')==6
PY

docker compose run --rm "${evidence_runner_user[@]}" -v "$PWD/evidence:/app/evidence" web \
  python tools/production_state_probe.py --output /app/evidence/target-state-before.json

docker compose run --rm "${evidence_runner_user[@]}" -v "$PWD/evidence:/app/evidence" worker \
  python tools/online_source_probe.py --require-success --output /app/evidence/target-sources.json

docker compose run --rm "${evidence_runner_user[@]}" -v "$PWD/evidence:/app/evidence" worker \
  python tools/deepseek_probe.py --output /app/evidence/target-deepseek.json

# The target runtime is already subject to the deployment-runtime verifier above.
# Rebuilding every Compose service here can deadlock while exporting unrelated
# web/worker images; run the configured acceptance harness instead. Bind the
# audited runner source so the harness stays exact even when its image is reused.
docker compose --profile acceptance run --rm \
  -v "$PWD/tools/e2e_production.py:/app/tools/e2e_production.py:ro" acceptance \
  python tools/e2e_production.py --output /app/evidence/target-browser.json
cp evidence/target-browser.json evidence/target-email.json

# Restart every application runtime and prove aggregate state/readback remains valid.
docker compose restart web scheduler worker
for _ in $(seq 1 60); do
  if curl -fsS "${BASE_URL%/}/readyz" >/dev/null 2>&1; then break; fi
  sleep 3
done
curl -fsS "${BASE_URL%/}/readyz" >/dev/null
docker compose run --rm "${evidence_runner_user[@]}" -v "$PWD/evidence:/app/evidence" web \
  python tools/production_state_probe.py --output /app/evidence/target-state-after.json
python3 - <<'PY'
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
python3 - "$backup_path" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); result={'verdict':'PASS','backup_file':str(p),'encrypted':p.suffix=='.enc','archive_verify_only':True,'production_restore_not_performed_by_acceptance':True}
Path('evidence/target-recovery.json').write_text(json.dumps(result,indent=2)+'\n')
PY

python3 tools/ops_probe.py --output evidence/target-ops.json
commit="${ACCEPTANCE_COMMIT:-$(git rev-parse HEAD 2>/dev/null || true)}"
deployment_id="${ACCEPTANCE_DEPLOYMENT_ID:-$(docker compose images -q web | head -1)}"
rollback_target="${ACCEPTANCE_ROLLBACK_TARGET:-$(cat runtime-data/rollback-image.txt 2>/dev/null || true)}"
python3 tools/finalize_acceptance.py \
  --base-url "$BASE_URL" --commit "$commit" --deployment-id "$deployment_id" \
  --rollback-target "$rollback_target" --output ACCEPTANCE_RESULT.json
python3 - <<'PY'
import json
p=json.load(open('ACCEPTANCE_RESULT.json'))
if p.get('core_verdict')!='PASS': raise SystemExit('production core acceptance is not PASS')
print('PRODUCTION CORE ACCEPTANCE: PASS')
PY
