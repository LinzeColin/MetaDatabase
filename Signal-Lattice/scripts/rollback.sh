#!/usr/bin/env bash
set -euo pipefail
umask 027
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RELEASE_CONTRACT="$PROJECT_ROOT/deploy/V2_RELEASE_CONTRACT.json"
PYTHON="${SIGNAL_LATTICE_PYTHON:-python3}"
"$PYTHON" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else "PYTHON_3_11_OR_NEWER_REQUIRED")
PY
ROOT="${SIGNAL_LATTICE_INSTALL_ROOT:-$("$PYTHON" - "$RELEASE_CONTRACT" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["install_root"])
PY
)}"
ROOT="$("$PYTHON" - "$ROOT" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).resolve())
PY
)"
STATE_DIR="${SIGNAL_LATTICE_STATE_DIR:-$("$PYTHON" - "$RELEASE_CONTRACT" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["state_dir"])
PY
)}"
RELEASES="$ROOT/releases"
TARGET="${1:-$ROOT/previous}"
[[ -e "$TARGET" ]] || { echo PREVIOUS_RELEASE_NOT_AVAILABLE >&2; exit 2; }
TARGET="$("$PYTHON" - "$TARGET" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]).resolve())
PY
)"
[[ "$TARGET" == "$RELEASES/"* ]] || { echo RELEASE_OUTSIDE_ALLOWED_ROOT >&2; exit 2; }
[[ -d "$TARGET" && -x "$TARGET/venv/bin/signal-lattice" && -f "$TARGET/release.json" ]] || { echo INVALID_RELEASE >&2; exit 2; }
TARGET_VERSION="$("$PYTHON" - "$TARGET/release.json" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])
PY
)"
[[ "$TARGET_VERSION" == "$(basename "$TARGET")" ]] || { echo RELEASE_RECEIPT_VERSION_MISMATCH >&2; exit 2; }
CURRENT_TARGET="$("$PYTHON" - "$ROOT/current" <<'PY'
import sys
from pathlib import Path
target = Path(sys.argv[1])
print(target.resolve() if target.exists() else "")
PY
)"
SMOKE_STATE="$(mktemp -d)"
cleanup_smoke_state() {
  rm -rf "$SMOKE_STATE"
}
trap cleanup_smoke_state EXIT
env -u PYTHONPATH -u PYTHONHOME SIGNAL_LATTICE_STATE_DIR="$SMOKE_STATE" \
  SIGNAL_LATTICE_WEB_DIR="$TARGET/web" "$TARGET/venv/bin/signal-lattice" verify-runtime
ln -sfn "$TARGET" "$ROOT/current.new"
"$PYTHON" - "$ROOT/current.new" "$ROOT/current" <<'PY'
import os
import sys
from pathlib import Path

staged, active = (Path(value) for value in sys.argv[1:])
if not staged.is_symlink():
    raise SystemExit("CURRENT_STAGING_LINK_INVALID")
if active.exists() and not active.is_symlink():
    raise SystemExit("CURRENT_TARGET_NOT_SYMLINK")
os.replace(staged, active)
PY
if [[ "${SIGNAL_LATTICE_RESTART_SERVICES:-1}" == "1" ]] && command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload
  systemctl restart signal-lattice-v2-api.service
  systemctl start signal-lattice-v2-loop.service
fi
install -d -m 0750 "$STATE_DIR/artifacts"
"$PYTHON" - "$STATE_DIR/artifacts/rollback_receipt.json" "$CURRENT_TARGET" "$TARGET" <<'PY'
import json,os,sys,tempfile
from pathlib import Path
out=Path(sys.argv[1]);receipt={"schema_version":"1.0.0","state":"PASS","from":sys.argv[2] or None,"to":sys.argv[3]}
fd,tmp=tempfile.mkstemp(prefix='.'+out.name+'.',dir=out.parent)
with os.fdopen(fd,'w') as f:json.dump(receipt,f,ensure_ascii=False,indent=2,sort_keys=True);f.flush();os.fsync(f.fileno())
os.chmod(tmp,0o600);os.replace(tmp,out)
print(json.dumps(receipt,ensure_ascii=False,sort_keys=True))
PY
