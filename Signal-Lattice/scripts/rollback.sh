#!/usr/bin/env bash
set -euo pipefail
umask 027
ROOT="${SIGNAL_LATTICE_INSTALL_ROOT:-/opt/signal-lattice}"
STATE_DIR="${SIGNAL_LATTICE_STATE_DIR:-/var/lib/signal-lattice}"
RELEASES="$ROOT/releases"
TARGET="${1:-$ROOT/previous}"
[[ -e "$TARGET" ]] || { echo PREVIOUS_RELEASE_NOT_AVAILABLE >&2; exit 2; }
TARGET="$(readlink -f "$TARGET")"
[[ "$TARGET" == "$RELEASES/"* ]] || { echo RELEASE_OUTSIDE_ALLOWED_ROOT >&2; exit 2; }
[[ -d "$TARGET" && -x "$TARGET/venv/bin/signal-lattice" && -f "$TARGET/release.json" ]] || { echo INVALID_RELEASE >&2; exit 2; }
CURRENT_TARGET="$(readlink -f "$ROOT/current" 2>/dev/null || true)"
env -u PYTHONPATH -u PYTHONHOME SIGNAL_LATTICE_STATE_DIR="${TMPDIR:-/tmp}/signal-lattice-rollback-smoke" \
  SIGNAL_LATTICE_WEB_DIR="$TARGET/web" "$TARGET/venv/bin/signal-lattice" verify-runtime
ln -sfn "$TARGET" "$ROOT/current.new"
mv -Tf "$ROOT/current.new" "$ROOT/current"
if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
  systemctl restart signal-lattice-api.service signal-lattice-worker.service
fi
install -d -m 0750 "$STATE_DIR/artifacts"
python3 - "$STATE_DIR/artifacts/rollback_receipt.json" "$CURRENT_TARGET" "$TARGET" <<'PY'
import json,os,sys,tempfile
from pathlib import Path
out=Path(sys.argv[1]);receipt={"schema_version":"1.0.0","state":"PASS","from":sys.argv[2] or None,"to":sys.argv[3]}
fd,tmp=tempfile.mkstemp(prefix='.'+out.name+'.',dir=out.parent)
with os.fdopen(fd,'w') as f:json.dump(receipt,f,ensure_ascii=False,indent=2,sort_keys=True);f.flush();os.fsync(f.fileno())
os.chmod(tmp,0o600);os.replace(tmp,out)
print(json.dumps(receipt,ensure_ascii=False,sort_keys=True))
PY
