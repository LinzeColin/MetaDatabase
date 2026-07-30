#!/usr/bin/env bash
set -euo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="0.0.0.1.40"
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

step "任务包与零运行依赖验证"
python3 "$ROOT/scripts/verify_northstar_repair_authorization.py" --receipt "$ROOT/evidence/repair/northstar_repair_authorization.json" --version "$VERSION"
python3 "$ROOT/scripts/verify_zero_runtime.py"

step "运行目录与服务账户"
SIGNAL_LATTICE_APPLY=1 bash "$ROOT/scripts/provision_runtime.sh" > "$ARTIFACTS/provision.json"
getent passwd cloudflared >/dev/null || useradd --system --home /nonexistent --shell /usr/sbin/nologin cloudflared
install -d -m 0750 -o root -g cloudflared /etc/signal-lattice/credentials
INGEST_TOKEN_FILE="${SIGNAL_LATTICE_INGEST_TOKEN_FILE:-/etc/signal-lattice/credentials/ingest_api_token}"
if [[ ! -s "$INGEST_TOKEN_FILE" ]]; then
  umask 077
  python3 - "$INGEST_TOKEN_FILE" <<'PY'
import os,secrets,sys,tempfile
from pathlib import Path
p=Path(sys.argv[1]);p.parent.mkdir(parents=True,exist_ok=True)
fd,tmp=tempfile.mkstemp(prefix='.'+p.name+'.',dir=p.parent)
with os.fdopen(fd,'w') as f:f.write(secrets.token_urlsafe(48)+'\n');f.flush();os.fsync(f.fileno())
os.chmod(tmp,0o640);os.replace(tmp,p)
PY
fi
chown root:signal-lattice "$INGEST_TOKEN_FILE"; chmod 0640 "$INGEST_TOKEN_FILE"

step "配置文件"
install -d -m 0750 /etc/signal-lattice
if [[ ! -f "$ENV_FILE" ]]; then
  install -m 0640 -o root -g signal-lattice "$ROOT/config/runtime.env.example" "$ENV_FILE"
  echo "CONFIG_CREATED_WITH_SAFE_DEFAULTS:$ENV_FILE"
fi
# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a
CF_ENV_FILE="${SIGNAL_LATTICE_CLOUDFLARE_ENV_FILE:-/etc/signal-lattice/credentials/cloudflare_api.env}"
if [[ -f "$CF_ENV_FILE" ]]; then
  [[ ! -L "$CF_ENV_FILE" ]] || fail CLOUDFLARE_ENV_SYMLINK_FORBIDDEN
  [[ "$(stat -c '%a' "$CF_ENV_FILE")" =~ ^(400|600)$ ]] || fail CLOUDFLARE_ENV_PERMISSIONS_UNSAFE
  # shellcheck disable=SC1090
  set -a; source "$CF_ENV_FILE"; set +a
fi
[[ "${SIGNAL_LATTICE_RECOMMENDATION_MODE:-}" =~ ^(RESEARCH_AND_NO_ACTION|HUMAN_DECISION_SUPPORT)$ ]] || fail INVALID_RECOMMENDATION_MODE
[[ "$PUBLIC_URL" == "https://signal-lattice.linzezhang.com" ]] || fail UNAPPROVED_PUBLIC_URL

step "确定性 Wheel 与原子安装"
WHEEL_DIR="$(mktemp -d)"; trap 'rm -rf "$WHEEL_DIR"' EXIT
python3 "$ROOT/scripts/build_wheel.py" --output-dir "$WHEEL_DIR" --receipt "$ARTIFACTS/wheel.json"
WHEEL="$(find "$WHEEL_DIR" -maxdepth 1 -name '*.whl' -type f -print -quit)"
[[ -n "$WHEEL" ]] || fail WHEEL_MISSING
bash "$ROOT/scripts/install_release.sh" "$WHEEL" | tee "$ARTIFACTS/install.txt"
cp "$INSTALL_ROOT/current/release.json" "$ARTIFACTS/release.json"
chmod 0600 "$ARTIFACTS/release.json"

step "cloudflared 固定版本安装"
bash "$ROOT/scripts/install_cloudflared_binary.sh" | tee "$ARTIFACTS/cloudflared_binary.json"

step "Cloudflare Tunnel 与 DNS"
if [[ ! -s "$TOKEN_FILE" ]]; then
  if [[ -n "${CLOUDFLARE_API_TOKEN:-}" && -n "${CLOUDFLARE_ACCOUNT_ID:-}" && -n "${CLOUDFLARE_ZONE_ID:-}" ]]; then
    python3 "$ROOT/scripts/configure_cloudflare_tunnel.py" \
      --hostname signal-lattice.linzezhang.com \
      --origin http://127.0.0.1:8787 \
      --tunnel-name signal-lattice \
      --token-file "$TOKEN_FILE" \
      --receipt "$ARTIFACTS/cloudflare_tunnel_config.json"
  else
    fail CLOUDFLARE_TUNNEL_TOKEN_OR_API_CREDENTIALS_REQUIRED
  fi
else
  python3 - "$TOKEN_FILE" "$ARTIFACTS/cloudflare_tunnel_config.json" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
p=Path(sys.argv[1]); out=Path(sys.argv[2])
if p.is_symlink() or p.stat().st_size < 32: raise SystemExit('UNSAFE_TUNNEL_TOKEN_FILE')
payload={"schema_version":"1.0.0","state":"PASS","source":"EXISTING_TOKEN_FILE","token_file":str(p),"token_sha256":hashlib.sha256(p.read_bytes().strip()).hexdigest(),"secret_emitted":False}
copy=dict(payload);payload['receipt_sha256']=hashlib.sha256(json.dumps(copy,sort_keys=True,separators=(',',':')).encode()).hexdigest();out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');os.chmod(out,0o600)
PY
fi
chown root:cloudflared "$TOKEN_FILE"; chmod 0640 "$TOKEN_FILE"
cp "$ARTIFACTS/cloudflare_tunnel_config.json" "$ARTIFACTS/cloudflare_tunnel_install.json"
chmod 0600 "$ARTIFACTS/cloudflare_tunnel_install.json"

step "systemd 安装与启动"
bash "$ROOT/scripts/install_systemd.sh" | tee "$ARTIFACTS/systemd_install.json"
systemctl restart signal-lattice-api.service signal-lattice-worker.service signal-lattice-cloudflared.service
systemctl start signal-lattice-source-sync.service signal-lattice-status.service
systemctl is-active --quiet signal-lattice-api.service || fail API_NOT_ACTIVE
systemctl is-active --quiet signal-lattice-worker.service || fail WORKER_NOT_ACTIVE
systemctl is-active --quiet signal-lattice-cloudflared.service || fail CLOUDFLARED_NOT_ACTIVE

step "本地 API 验证"
python3 - "$ARTIFACTS/local_health.json" <<'PY'
import json,urllib.request,sys,time
from pathlib import Path
url='http://127.0.0.1:8787/api/v1/status';last=''
for _ in range(30):
 try:
  with urllib.request.urlopen(url,timeout=3) as r:d=json.load(r)
  if d.get('project_id')=='signal-lattice' and d.get('version')=='0.0.0.1.40':
   Path(sys.argv[1]).write_text(json.dumps({'state':'PASS','status':d},ensure_ascii=False,indent=2,sort_keys=True)+'\n');break
 except Exception as e:last=repr(e);time.sleep(.5)
else: raise SystemExit('LOCAL_API_NOT_READY:'+last)
PY

step "目标数据库备份与恢复验证"
python3 "$ROOT/scripts/target_backup_recovery.py" --source "$STATE/runtime.db" --backup "$STATE/backups/deployment-verified.db" --output "$ARTIFACTS/target_backup_recovery.json"

step "来源与输入同步"
set +e
"$INSTALL_ROOT/current/venv/bin/python" "$INSTALL_ROOT/current/scripts/source_sync_once.py" > "$ARTIFACTS/source_sync.stdout.json"
SOURCE_RC=$?
set -e
if [[ $SOURCE_RC -ne 0 && $SOURCE_RC -ne 3 ]]; then fail SOURCE_SYNC_EXECUTION_FAILED; fi
python3 "$ROOT/scripts/status_publish_once.py"

step "公网 URL 验证"
for _ in $(seq 1 60); do
  if python3 "$ROOT/scripts/verify_public_release.py" --url "$PUBLIC_URL" --version "$VERSION" --output "$ARTIFACTS/public_release.json" >/dev/null 2>&1; then break; fi
  sleep 2
done
python3 "$ROOT/scripts/verify_public_release.py" --url "$PUBLIC_URL" --version "$VERSION" --output "$ARTIFACTS/public_release.json"
python3 "$ROOT/scripts/capture_public_screenshot.py" --url "$PUBLIC_URL" --output "$ARTIFACTS/signal-lattice-live.png" || true

step "运行时零 Agent／零 Token 与自愈审计"
"$INSTALL_ROOT/current/venv/bin/python" "$INSTALL_ROOT/current/scripts/runtime_audit.py" --output "$ARTIFACTS/runtime_audit.json"

step "Status 业务线证据与最终 Closure"
python3 "$ROOT/scripts/generate_status_evidence.py" --artifact-dir "$ARTIFACTS" --output-dir "$STATUS_EVIDENCE" --summary "$ARTIFACTS/status_evidence_summary.json"
python3 "$ROOT/scripts/build_business_line_evidence.py" --target --evidence-root "$STATUS_EVIDENCE" --output "$ARTIFACTS/business_line_target.json"
bash "$ROOT/scripts/status_closure.sh" "$ARTIFACTS/business_line_target.json" "$ARTIFACTS/status_closure.json"

step "最终交付结果"
python3 "$ROOT/scripts/build_delivery_result.py" --public-receipt "$ARTIFACTS/public_release.json" --status-closure "$ARTIFACTS/status_closure.json" --version "$VERSION" --output "$ARTIFACTS/DELIVERY_RESULT.json" --markdown "$ARTIFACTS/DELIVERY_RESULT.md" --screenshot "$ARTIFACTS/signal-lattice-live.png"
python3 "$ROOT/scripts/verify_deployment_claim.py" --result "$ARTIFACTS/DELIVERY_RESULT.json" --version "$VERSION"

echo "DEPLOYED_AND_VERIFIED:$PUBLIC_URL"
echo "PUBLIC_URL=$PUBLIC_URL"
echo "STATUS_URL=https://status.linzezhang.com"
