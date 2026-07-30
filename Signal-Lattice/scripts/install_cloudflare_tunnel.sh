#!/usr/bin/env bash
set -euo pipefail
umask 077
PUBLIC_HOST="${SIGNAL_LATTICE_PUBLIC_HOST:-signal-lattice.linzezhang.com}"
TOKEN_FILE="${CLOUDFLARE_TUNNEL_TOKEN_FILE:-/etc/signal-lattice/credentials/cloudflare_tunnel_token}"
RECEIPT="${1:-/var/lib/signal-lattice/artifacts/cloudflare_tunnel_install.json}"
APPLY="${SIGNAL_LATTICE_APPLY:-0}"

emit() {
  python3 - "$RECEIPT" "$1" "$2" "$PUBLIC_HOST" <<'PY'
import hashlib,json,os,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path
out=Path(sys.argv[1]); state=sys.argv[2]; reason=sys.argv[3]; host=sys.argv[4]
p={"schema_version":"1.0.0","state":state,"reason":reason,"public_host":host,"configured_at":datetime.now(timezone.utc).isoformat(),"token_logged":False,"upstream_writeback":False,"runtime_agent_dependency":0,"runtime_llm_tokens":0}
p["receipt_sha256"]=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
out.parent.mkdir(parents=True,exist_ok=True)
fd,tmp=tempfile.mkstemp(prefix='.'+out.name+'.',dir=out.parent)
with os.fdopen(fd,'w',encoding='utf-8') as f: json.dump(p,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
os.chmod(tmp,0o600);os.replace(tmp,out)
print(json.dumps(p,ensure_ascii=False,sort_keys=True))
PY
}

if [[ "$APPLY" != "1" ]]; then
  if command -v cloudflared >/dev/null 2>&1; then
    emit READY "CLOUDFLARED_PRESENT_APPLY_REQUIRED"
  else
    emit BLOCKED "CLOUDFLARED_BINARY_REQUIRED"
    exit 2
  fi
  exit 0
fi
[[ "$(id -u)" -eq 0 ]] || { emit BLOCKED ROOT_REQUIRED; exit 2; }
command -v cloudflared >/dev/null 2>&1 || { emit BLOCKED CLOUDFLARED_BINARY_REQUIRED; exit 2; }
[[ -f "$TOKEN_FILE" && ! -L "$TOKEN_FILE" ]] || { emit BLOCKED CLOUDFLARE_TUNNEL_TOKEN_FILE_REQUIRED; exit 2; }
[[ "$(stat -c '%a' "$TOKEN_FILE")" =~ ^(400|440|600|640)$ ]] || { emit BLOCKED CLOUDFLARE_TUNNEL_TOKEN_FILE_PERMISSIONS_UNSAFE; exit 2; }
TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"
[[ ${#TOKEN} -ge 32 ]] || { unset TOKEN; emit BLOCKED CLOUDFLARE_TUNNEL_TOKEN_INVALID; exit 2; }
if systemctl list-unit-files cloudflared.service >/dev/null 2>&1 && systemctl is-active --quiet cloudflared.service; then
  unset TOKEN
  emit PASS "EXISTING_CLOUDFLARED_SERVICE_ACTIVE_NO_REPLACEMENT"
  exit 0
fi
cloudflared service install "$TOKEN" >/dev/null
unset TOKEN
systemctl daemon-reload
systemctl enable --now cloudflared.service
systemctl is-active --quiet cloudflared.service || { emit BLOCKED CLOUDFLARED_SERVICE_NOT_ACTIVE; exit 2; }
emit PASS "REMOTE_MANAGED_TUNNEL_SERVICE_ACTIVE"
