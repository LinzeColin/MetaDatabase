#!/usr/bin/env bash
set -euo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo ".env is missing. Generate it before acceptance." >&2
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required on the deployment host." >&2
  exit 2
fi
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose is required on the deployment host." >&2
  exit 2
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

run_id="$(date -u +%Y%m%dT%H%M%SZ)"
evidence_dir="evidence/target-${run_id}"
mkdir -p "$evidence_dir"
chmod 700 "$evidence_dir"

acceptance_venv="$(mktemp -d -t jobhuntos-acceptance-venv-XXXXXX)"
pytest_data_dir="$(mktemp -d -t jobhuntos-pytest-data-XXXXXX)"
credential_host="$(mktemp -t jobhuntos-acceptance-credentials-XXXXXX.json)"
live_state="$(mktemp -t jobhuntos-live-state-XXXXXX.json)"
# Docker's archive copy cannot read the hardened tmpfs mount on this target.
# Keep the short-lived 0600 credential in the private bind mount instead; cleanup removes it on every exit path.
credential_container="/data/.jobhuntos-acceptance-${run_id}.json"
acceptance_email=""
acceptance_cleanup_complete="false"

cleanup() {
  status=$?
  set +e
  unset LIVE_ACCEPTANCE_PASSWORD
  if [[ -n "$acceptance_email" && "$acceptance_cleanup_complete" != "true" ]]; then
    docker compose exec -T app python -m app.cli delete-acceptance-user --email "$acceptance_email" >/dev/null 2>&1
  fi
  docker compose exec -T app rm -f "$credential_container" >/dev/null 2>&1
  rm -f "$credential_host" "$live_state"
  rm -rf "$acceptance_venv" "$pytest_data_dir"
  exit "$status"
}
trap cleanup EXIT INT TERM

python3 -m venv "$acceptance_venv"
acceptance_python="$acceptance_venv/bin/python"
"$acceptance_python" -m pip install -r requirements-dev.txt >/dev/null
"$acceptance_python" -m pip check | tee "$evidence_dir/host-pip-check.txt"
"$acceptance_python" -m pip freeze | tee "$evidence_dir/host-installed-packages.txt"
"$acceptance_python" tools/verify_runtime.py | tee "$evidence_dir/host-runtime-versions.json"

# Install a dedicated browser; do not reuse personal profiles or inherited browser policy.
if command -v apt-get >/dev/null 2>&1; then
  if [[ $(id -u) -eq 0 ]]; then
    "$acceptance_python" -m playwright install-deps chromium >/dev/null
  elif command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
    sudo -n "$acceptance_python" -m playwright install-deps chromium >/dev/null
  fi
fi
"$acceptance_python" -m playwright install chromium >/dev/null

"$acceptance_python" tools/validate_taskpack.py --allow-production-runtime-secrets | tee "$evidence_dir/taskpack-validation.json"
# .env is intentionally loaded above for live checks only.  Unit tests must never inherit it:
# their database cleanup is destructive by design and needs a dedicated temporary data directory.
env -i \
  PATH="$PATH" \
  HOME="${HOME:-/tmp}" \
  TMPDIR="${TMPDIR:-/tmp}" \
  LANG="${LANG:-C.UTF-8}" \
  PYTHONDONTWRITEBYTECODE=1 \
  DATA_DIR="$pytest_data_dir" \
  APP_ENV=development \
  BASE_URL=http://testserver \
  ADMIN_EMAIL=owner@test.local \
  ADMIN_PASSWORD=Correct-Horse-Battery-2026 \
  SESSION_SECRET=test-session-secret-abcdefghijklmnopqrstuvwxyz-0123456789 \
  DATA_ENCRYPTION_KEY=v58zowyA7G8WmtqvK5SZbnwwQl76JJzhy1N9_Mi4uk4= \
  COOKIE_SECURE=false \
  MAINTENANCE_ENABLED=false \
  "$acceptance_python" -m pytest -q -p no:cacheprovider | tee "$evidence_dir/pytest.txt"
"$acceptance_python" tests/http_golden.py "$evidence_dir/http"
"$acceptance_python" tests/e2e_golden.py "$evidence_dir/browser-isolated"

# Parse the Compose project without writing an interpolated secret-bearing config to evidence.
docker compose config --quiet
docker compose config --services > "$evidence_dir/compose-services.txt"
docker compose config --images > "$evidence_dir/compose-images.txt"
docker compose exec -T app python tools/verify_runtime.py --expected-python 3.13.14 | tee "$evidence_dir/container-runtime-versions.json"
docker compose exec -T app python -m pip check | tee "$evidence_dir/container-pip-check.txt"
docker compose exec -T app python -m pip freeze | tee "$evidence_dir/container-installed-packages.txt"
docker compose exec -T app python -m app.cli reencrypt-sensitive | tee "$evidence_dir/container-sensitive-migration.json"
docker compose exec -T app python -m app.cli verify-sensitive-storage | tee "$evidence_dir/container-sensitive-storage-before.json"
proxy_container="${TRAEFIK_PROXY_CONTAINER:-coolify-proxy}"
docker inspect "$proxy_container" --format '{{.State.Status}}' | tee "$evidence_dir/traefik-proxy-status.txt"
grep -Fxq "running" "$evidence_dir/traefik-proxy-status.txt"
app_container="$(docker compose ps -q app)"
if [[ -z "$app_container" ]]; then
  echo "Application container is not available for Traefik route verification." >&2
  exit 1
fi
docker inspect "$app_container" --format '{{index .Config.Labels "traefik.enable"}}' | tee "$evidence_dir/traefik-route-enabled.txt"
grep -Fxq "true" "$evidence_dir/traefik-route-enabled.txt"
docker compose exec -T app python -m app.cli doctor | tee "$evidence_dir/container-doctor-before.json"

curl --silent --show-error --max-time 15 -o /dev/null -w '%{http_code} %{redirect_url}\n' "http://${DOMAIN}/" \
  | tee "$evidence_dir/http-to-https.txt"
grep -Eq '^30[1278] https://' "$evidence_dir/http-to-https.txt"

for endpoint in healthz readyz api/status; do
  curl --fail --silent --show-error --max-time 15 "${BASE_URL}/${endpoint}" > "$evidence_dir/${endpoint//\//-}-before.json"
done

# Create an isolated temporary user. Credentials remain in temporary 0600 files and process environment only.
docker compose exec -T app python -m app.cli create-acceptance-user --output "$credential_container" \
  > "$evidence_dir/acceptance-user-created.json"
docker compose cp "app:${credential_container}" "$credential_host" >/dev/null
docker compose exec -T app rm -f "$credential_container"
chmod 600 "$credential_host"

mapfile -t acceptance_values < <("$acceptance_python" - "$credential_host" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(payload["email"])
print(payload["password"])
PY
)
acceptance_email="${acceptance_values[0]}"
export LIVE_ACCEPTANCE_EMAIL="$acceptance_email"
export LIVE_ACCEPTANCE_PASSWORD="${acceptance_values[1]}"
export LIVE_ACCEPTANCE_MARKER="JHB-LIVE-${run_id}-$($acceptance_python - <<'PY'
import secrets
print(secrets.token_hex(8))
PY
)"
rm -f "$credential_host"

"$acceptance_python" tests/e2e_live_golden.py "$evidence_dir/browser-live-transaction" \
  --mode transaction --state "$live_state"

docker compose restart app >/dev/null
ready="false"
for _ in $(seq 1 60); do
  if curl --fail --silent --max-time 3 "${BASE_URL}/readyz" >/dev/null 2>&1; then
    ready="true"
    break
  fi
  sleep 1
done
if [[ "$ready" != "true" ]]; then
  echo "Application did not become ready after container restart." >&2
  exit 1
fi

"$acceptance_python" tests/e2e_live_golden.py "$evidence_dir/browser-live-readback" \
  --mode readback --state "$live_state"

docker compose exec -T app python -m app.cli delete-acceptance-user --email "$acceptance_email" \
  | tee "$evidence_dir/acceptance-user-cleanup.json"
acceptance_cleanup_complete="true"
unset LIVE_ACCEPTANCE_EMAIL LIVE_ACCEPTANCE_PASSWORD LIVE_ACCEPTANCE_MARKER
acceptance_email=""
rm -f "$live_state"

docker compose exec -T app python -m app.cli verify-sensitive-storage | tee "$evidence_dir/container-sensitive-storage-after.json"
docker compose exec -T app python -m app.cli doctor | tee "$evidence_dir/container-doctor-after.json"

for endpoint in healthz readyz api/status; do
  curl --fail --silent --show-error --max-time 15 "${BASE_URL}/${endpoint}" > "$evidence_dir/${endpoint//\//-}.json"
done

python3 - "$evidence_dir" <<'PY'
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1])
status_payload = json.loads((root / "api-status.json").read_text(encoding="utf-8"))
sync_state = str(status_payload.get("long_term_sync", {}).get("state", "unknown"))
deepseek = status_payload.get("deepseek", {}) if isinstance(status_payload.get("deepseek"), dict) else {}
ai_ready = bool(deepseek.get("ready"))
ai_configured = bool(deepseek.get("configured"))
conditions = []
if sync_state != "synced":
    conditions.append("外部长期同步尚未全部确认成功，UI 与 API 保留真实状态")
if not ai_ready:
    conditions.append(
        "DeepSeek 尚未由 Owner 在网页中粘贴密钥并完成真实连通验证"
        if not ai_configured
        else "DeepSeek 已配置但尚未达到 ready；请在网页设置页重新验证"
    )
verdict = "PASS" if not conditions else "CONDITIONAL_PASS"
summary = {
    "result": verdict,
    "core_result": "PASS",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "evidence_dir": str(root),
    "long_term_sync": sync_state,
    "deepseek": {
        "configured": ai_configured,
        "enabled": bool(deepseek.get("enabled")),
        "ready": ai_ready,
        "fast_model": deepseek.get("fast_model", ""),
        "precision_model": deepseek.get("precision_model", ""),
    },
    "condition": "；".join(conditions),
    "checks": [
        "exact dependency versions and functional compatibility",
        "deterministic rule and mocked DeepSeek integration suite",
        "DeepSeek direct-identifier redaction and safe fallback",
        "real process golden transaction",
        "isolated browser golden transaction",
        "public HTTPS isolated-user write transaction",
        "application container restart and persisted readback",
        "temporary acceptance-user cleanup",
        "encrypted backup and isolated restore",
        "sensitive field migration and storage verification",
        "container diagnostics",
        "public HTTPS health and readiness",
    ],
}
(root / "ACCEPTANCE_RESULT.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY
