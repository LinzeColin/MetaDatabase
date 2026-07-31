#!/usr/bin/env bash
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="0.0.0.1.41"
STATE="${SIGNAL_LATTICE_STATE_DIR:-/var/lib/signal-lattice}"
ARTIFACTS="${SIGNAL_LATTICE_ARTIFACT_DIR:-$STATE/artifacts}"
INSTALL_ROOT="${SIGNAL_LATTICE_INSTALL_ROOT:-/opt/signal-lattice}"
ENV_FILE="${SIGNAL_LATTICE_ENV_FILE:-/etc/signal-lattice/runtime.env}"
STATUS_EVIDENCE="${SIGNAL_LATTICE_STATUS_EVIDENCE_ROOT:-$STATE/status-evidence}"
PUBLIC_URL="${SIGNAL_LATTICE_PUBLIC_URL:-https://signal-lattice.linzezhang.com}"
TOKEN_FILE="${CLOUDFLARE_TUNNEL_TOKEN_FILE:-/etc/signal-lattice/credentials/cloudflare_tunnel_token}"
mkdir -p "$ARTIFACTS"
step(){ printf '\n==> %s\n' "$1"; }
fail(){ echo "DEPLOYMENT_BLOCKED:$1" >&2; exit 2; }
[[ "$(id -u)" -eq 0 ]] || fail ROOT_REQUIRED

step "Status Tier-0 预检"
bash "$ROOT/scripts/status_preflight.sh" deployment "$ARTIFACTS/status_preflight.json"

step "任务包、版本与零运行依赖验证"
python3 "$ROOT/scripts/verify_zero_runtime.py"
python3 "$ROOT/scripts/verify_version_lock.py" --root "$ROOT" --output "$ARTIFACTS/version_lock.json"

step "运行目录与服务账户"
SIGNAL_LATTICE_APPLY=1 bash "$ROOT/scripts/provision_runtime.sh" > "$ARTIFACTS/provision.json"
getent passwd cloudflared >/dev/null || useradd --system --home /nonexistent --shell /usr/sbin/nologin cloudflared
install -d -m 0750 -o root -g cloudflared /etc/signal-lattice/credentials
INGEST_TOKEN_FILE="${SIGNAL_LATTICE_INGEST_TOKEN_FILE:-/etc/signal-lattice/credentials/ingest_api_token}"
if [[ ! -s "$INGEST_TOKEN_FILE" ]]; then
  python3 - "$INGEST_TOKEN_FILE" <<'PY'
import os,secrets,sys,tempfile
from pathlib import Path
p=Path(sys.argv[1]);p.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix='.'+p.name+'.',dir=p.parent)
with os.fdopen(fd,'w') as f:f.write(secrets.token_urlsafe(48)+'\n');f.flush();os.fsync(f.fileno())
os.chmod(tmp,0o640);os.replace(tmp,p)
PY
fi
chown root:signal-lattice "$INGEST_TOKEN_FILE"; chmod 0640 "$INGEST_TOKEN_FILE"

step "生产配置"
# Both dedicated service accounts need to traverse this parent directory, while
# their individual files remain group-readable only in their own subdirectories.
install -d -m 0711 -o root -g root /etc/signal-lattice
if [[ ! -f "$ENV_FILE" ]]; then install -m 0640 -o root -g signal-lattice "$ROOT/config/runtime.env.example" "$ENV_FILE"; fi
python3 - "$ENV_FILE" <<'PY'
import os, sys, tempfile
from pathlib import Path

env_file = Path(sys.argv[1])
canonical = "SIGNAL_LATTICE_UPSTREAM_SPARSE_PATH=Signal-Lattice/Stock_Skill"
lines = env_file.read_text(encoding="utf-8").splitlines()
updated = []
seen = False
for line in lines:
    if line.startswith("SIGNAL_LATTICE_UPSTREAM_SPARSE_PATH="):
        if not seen:
            updated.append(canonical)
            seen = True
        continue
    updated.append(line)
if not seen:
    updated.append(canonical)
body = "\n".join(updated) + "\n"
if body != env_file.read_text(encoding="utf-8"):
    before = env_file.stat()
    fd, temporary = tempfile.mkstemp(prefix="." + env_file.name + ".", dir=env_file.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, before.st_mode & 0o777)
        os.chown(temporary, before.st_uid, before.st_gid)
        os.replace(temporary, env_file)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
PY
# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a
[[ "${SIGNAL_LATTICE_ENV:-}" == production ]] || fail PRODUCTION_ENV_REQUIRED
[[ "${SIGNAL_LATTICE_MARKET_PROVIDER:-}" == moomoo ]] || fail MOOMOO_PROVIDER_REQUIRED
[[ "${SIGNAL_LATTICE_MARKET_LICENSE_CONFIRMED:-0}" == 1 ]] || fail MARKET_DATA_LICENSE_CONFIRMATION_REQUIRED
[[ "${SIGNAL_LATTICE_RECOMMENDATION_MODE:-}" == HUMAN_DECISION_SUPPORT ]] || fail HUMAN_DECISION_SUPPORT_MODE_REQUIRED
[[ "$PUBLIC_URL" == "https://signal-lattice.linzezhang.com" ]] || fail UNAPPROVED_PUBLIC_URL
CF_ENV_FILE="${SIGNAL_LATTICE_CLOUDFLARE_ENV_FILE:-/etc/signal-lattice/credentials/cloudflare_api.env}"
if [[ -f "$CF_ENV_FILE" ]]; then
  [[ ! -L "$CF_ENV_FILE" ]] || fail CLOUDFLARE_ENV_SYMLINK_FORBIDDEN
  [[ "$(stat -c '%a' "$CF_ENV_FILE")" =~ ^(400|600)$ ]] || fail CLOUDFLARE_ENV_PERMISSIONS_UNSAFE
  # shellcheck disable=SC1090
  set -a; source "$CF_ENV_FILE"; set +a
fi

step "确定性 Wheel 与原子安装"
WHEEL_DIR="$(mktemp -d)"; trap 'rm -rf "$WHEEL_DIR"' EXIT
python3 "$ROOT/scripts/build_wheel.py" --output-dir "$WHEEL_DIR" --receipt "$ARTIFACTS/wheel.json"
WHEEL="$(find "$WHEEL_DIR" -maxdepth 1 -name '*.whl' -type f -print -quit)"; [[ -n "$WHEEL" ]] || fail WHEEL_MISSING
bash "$ROOT/scripts/install_release.sh" "$WHEEL" | tee "$ARTIFACTS/install.txt"
cp "$INSTALL_ROOT/current/release.json" "$ARTIFACTS/release.json"; chmod 0600 "$ARTIFACTS/release.json"

step "Moomoo 只读行情 SDK 与 OpenD 验证"
"$INSTALL_ROOT/current/venv/bin/pip" install --disable-pip-version-check --no-input -r "$INSTALL_ROOT/current/requirements/providers-moomoo.txt" > "$ARTIFACTS/moomoo_sdk_install.txt"
# The SDK is installed after the root-built release is activated; normalize its
# read/execute bits again so the dedicated cycle account can import it.
chmod -R a+rX "$INSTALL_ROOT/current/venv"
"$INSTALL_ROOT/current/venv/bin/python" "$INSTALL_ROOT/current/scripts/verify_moomoo_opend.py" --universe "$INSTALL_ROOT/current/config/universe.json" --output "$ARTIFACTS/moomoo_opend.json"

step "Cloudflare Tunnel"
bash "$ROOT/scripts/install_cloudflared_binary.sh" | tee "$ARTIFACTS/cloudflared_binary.json"
if [[ ! -s "$TOKEN_FILE" ]]; then
  if [[ -n "${CLOUDFLARE_API_TOKEN:-}" && -n "${CLOUDFLARE_ACCOUNT_ID:-}" && -n "${CLOUDFLARE_ZONE_ID:-}" ]]; then
    python3 "$ROOT/scripts/configure_cloudflare_tunnel.py" --hostname signal-lattice.linzezhang.com --origin http://127.0.0.1:8787 --tunnel-name signal-lattice --token-file "$TOKEN_FILE" --receipt "$ARTIFACTS/cloudflare_tunnel_config.json"
  else fail CLOUDFLARE_TUNNEL_TOKEN_OR_API_CREDENTIALS_REQUIRED; fi
else
  python3 - "$TOKEN_FILE" "$ARTIFACTS/cloudflare_tunnel_config.json" <<'PY'
import hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
token=Path(sys.argv[1]); out=Path(sys.argv[2])
p={"schema_version":"1.0.0","state":"PASS","mode":"EXISTING_TOKEN_FILE","hostname":"signal-lattice.linzezhang.com","origin":"http://127.0.0.1:8787","token_file":str(token),"token_sha256":hashlib.sha256(token.read_bytes()).hexdigest(),"verified_at":datetime.now(timezone.utc).isoformat()}
p["receipt_sha256"]=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(p,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
PY
fi
cp "$ARTIFACTS/cloudflare_tunnel_config.json" "$ARTIFACTS/cloudflare_tunnel_install.json"
chown root:cloudflared "$TOKEN_FILE"; chmod 0640 "$TOKEN_FILE"

step "systemd 安装与启动"
bash "$ROOT/scripts/install_systemd.sh" | tee "$ARTIFACTS/systemd_install.json"
systemctl restart signal-lattice-api.service signal-lattice-cloudflared.service
systemctl start signal-lattice-cycle.service
systemctl start signal-lattice-status.service
systemctl is-active --quiet signal-lattice-api.service || fail API_NOT_ACTIVE
systemctl is-active --quiet signal-lattice-cloudflared.service || fail CLOUDFLARED_NOT_ACTIVE
systemctl is-enabled --quiet signal-lattice-cycle.timer || fail MINUTE_CYCLE_TIMER_NOT_ENABLED
systemctl is-active --quiet signal-lattice-cycle.timer || fail MINUTE_CYCLE_TIMER_NOT_ACTIVE

step "本地北极星链路验证"
python3 - "$ARTIFACTS/local_northstar.json" <<'PY'
import json,sys,urllib.request
from pathlib import Path
base='http://127.0.0.1:8787'
with urllib.request.urlopen(base+'/api/v1/system/status',timeout=5) as r: status=json.load(r)
with urllib.request.urlopen(base+'/api/v1/cycles/latest',timeout=5) as r: cycle=json.load(r)
with urllib.request.urlopen(base+'/api/v1/recommendations',timeout=5) as r: rec=json.load(r)
current=rec.get('current') or {};checks={
 'version':status.get('version')=='0.0.0.1.41','cycle':cycle.get('state')=='COMPLETED',
 'all_skills':cycle.get('completed_skill_count')==cycle.get('active_skill_count') and cycle.get('active_skill_count',0)>=5,
 'failed_zero':cycle.get('failed_skill_count')==0,'one_recommendation':len(rec.get('items') or [])==1,
 'not_system_blocked':current.get('action')!='SYSTEM_BLOCKED','production_data':current.get('market_data_production_eligible') is True,
 'zero_agent':status.get('runtime_agent_dependency')==0,'zero_token':status.get('runtime_llm_tokens')==0,
}
payload={'state':'PASS' if all(checks.values()) else 'BLOCKED','checks':checks,'cycle_id':cycle.get('cycle_id'),'current':current}
Path(sys.argv[1]).write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
if payload['state']!='PASS':raise SystemExit('LOCAL_NORTH_STAR_NOT_READY')
PY

step "目标数据库备份与恢复验证"
"$INSTALL_ROOT/current/venv/bin/python" "$INSTALL_ROOT/current/scripts/target_backup_recovery.py" --source "$STATE/runtime.db" --backup "$STATE/backups/deployment-verified.db" --output "$ARTIFACTS/target_backup_recovery.json"

step "公网北极星验收"
for _ in $(seq 1 20); do
  if python3 "$ROOT/scripts/verify_public_release.py" --url "$PUBLIC_URL" --version "$VERSION" --output "$ARTIFACTS/public_release.json" >/dev/null 2>&1; then break; fi
  sleep 1
done
python3 "$ROOT/scripts/verify_public_release.py" --url "$PUBLIC_URL" --version "$VERSION" --output "$ARTIFACTS/public_release.json"
python3 "$ROOT/scripts/capture_public_screenshot.py" --url "$PUBLIC_URL" --output "$ARTIFACTS/signal-lattice-live.png" || true

step "运行审计、Status Closure 与交付结果"
"$INSTALL_ROOT/current/venv/bin/python" "$INSTALL_ROOT/current/scripts/runtime_audit.py" --output "$ARTIFACTS/runtime_audit.json"
"$INSTALL_ROOT/current/venv/bin/python" "$INSTALL_ROOT/current/scripts/status_publish_once.py"
"$INSTALL_ROOT/current/venv/bin/python" "$INSTALL_ROOT/current/scripts/generate_status_evidence.py" --artifact-dir "$ARTIFACTS" --output-dir "$STATUS_EVIDENCE" --summary "$ARTIFACTS/status_evidence_summary.json"
"$INSTALL_ROOT/current/venv/bin/python" "$INSTALL_ROOT/current/scripts/build_business_line_evidence.py" --target --evidence-root "$STATUS_EVIDENCE" --output "$ARTIFACTS/business_line_target.json"
bash "$ROOT/scripts/status_closure.sh" "$ARTIFACTS/business_line_target.json" "$ARTIFACTS/status_closure.json"
python3 "$ROOT/scripts/build_delivery_result.py" --public-receipt "$ARTIFACTS/public_release.json" --status-closure "$ARTIFACTS/status_closure.json" --version "$VERSION" --output "$ARTIFACTS/DELIVERY_RESULT.json" --markdown "$ARTIFACTS/DELIVERY_RESULT.md" --screenshot "$ARTIFACTS/signal-lattice-live.png"
python3 "$ROOT/scripts/verify_deployment_claim.py" --result "$ARTIFACTS/DELIVERY_RESULT.json" --version "$VERSION"

echo "NORTH_STAR_DEPLOYED_AND_PUBLICLY_VERIFIED:$PUBLIC_URL"
echo "PUBLIC_URL=$PUBLIC_URL"
echo "STATUS_URL=https://status.linzezhang.com"
