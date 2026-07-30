#!/usr/bin/env bash
set -euo pipefail
umask 027
VERSION="0.0.0.1.39"
WHEEL="${1:?wheel path required}"
ROOT="${SIGNAL_LATTICE_INSTALL_ROOT:-/opt/signal-lattice}"
PYTHON_BIN="${SIGNAL_LATTICE_PYTHON:-python3}"
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
  for candidate in python3.12 python3.11; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi
"$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3, 11), "Signal Lattice requires Python >= 3.11"'
RELEASE="$ROOT/releases/$VERSION"
WHEEL_ABS="$(cd "$(dirname "$WHEEL")" && pwd)/$(basename "$WHEEL")"
[[ -f "$WHEEL_ABS" ]] || { echo WHEEL_NOT_FOUND >&2; exit 2; }
WHEEL_SHA="$(sha256sum "$WHEEL_ABS" | awk '{print $1}')"
RECEIPT="$RELEASE/release.json"

if [[ -d "$RELEASE" ]]; then
  if [[ -f "$RECEIPT" ]] && "$PYTHON_BIN" - "$RECEIPT" "$WHEEL_SHA" "$VERSION" <<'PY'
import json,sys
p,expected,version=sys.argv[1:]
d=json.load(open(p))
raise SystemExit(0 if d.get('wheel_sha256')==expected and d.get('version')==version and d.get('state')=='INSTALLED' else 1)
PY
  then
    [[ -x "$RELEASE/venv/bin/signal-lattice" ]] || { echo EXISTING_RELEASE_INCOMPLETE >&2; exit 4; }
    [[ ! -d "$ROOT/current" || -L "$ROOT/current" ]] || { echo CURRENT_TARGET_NOT_SYMLINK >&2; exit 4; }
    ln -sfn "$RELEASE" "$ROOT/current.new"
    mv -f "$ROOT/current.new" "$ROOT/current"
    echo ALREADY_INSTALLED
    exit 0
  fi
  echo VERSION_COLLISION >&2
  exit 4
fi

install -d -m 0755 "$ROOT/releases"
TMP_RELEASE="$ROOT/releases/.${VERSION}.tmp.$$"
trap 'rm -rf "$TMP_RELEASE"' EXIT
[[ ! -e "$TMP_RELEASE" ]] || { echo TEMP_RELEASE_EXISTS >&2; exit 5; }
install -d -m 0755 "$TMP_RELEASE"
"$PYTHON_BIN" -m venv "$TMP_RELEASE/venv"
env -u PYTHONPATH -u PYTHONHOME PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
  "$TMP_RELEASE/venv/bin/python" -m pip install --no-index --no-deps --force-reinstall "$WHEEL_ABS"
cp -a "$(cd "$(dirname "$0")/.." && pwd)/web" "$TMP_RELEASE/web"
cp -a "$(cd "$(dirname "$0")/.." && pwd)/db" "$TMP_RELEASE/db"
cp -a "$(cd "$(dirname "$0")/.." && pwd)/scripts" "$TMP_RELEASE/scripts"
"$PYTHON_BIN" - "$TMP_RELEASE/release.json" "$VERSION" "$WHEEL_SHA" "$(basename "$WHEEL_ABS")" <<'PY'
import json,os,sys,tempfile
from pathlib import Path
out=Path(sys.argv[1]);payload={'schema_version':'1.0.0','state':'INSTALLED','version':sys.argv[2],'wheel_sha256':sys.argv[3],'wheel_name':sys.argv[4]}
fd,tmp=tempfile.mkstemp(prefix='.release.',dir=out.parent)
with os.fdopen(fd,'w') as f:json.dump(payload,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
os.chmod(tmp,0o644);os.replace(tmp,out)
PY
SMOKE_STATE="$(mktemp -d)"
trap 'rm -rf "$TMP_RELEASE" "$SMOKE_STATE"' EXIT
env -u PYTHONPATH -u PYTHONHOME SIGNAL_LATTICE_STATE_DIR="$SMOKE_STATE" \
  SIGNAL_LATTICE_WEB_DIR="$TMP_RELEASE/web" "$TMP_RELEASE/venv/bin/signal-lattice" verify-runtime
mv "$TMP_RELEASE" "$RELEASE"
trap 'rm -rf "$SMOKE_STATE"' EXIT
[[ ! -d "$ROOT/current" || -L "$ROOT/current" ]] || { echo CURRENT_TARGET_NOT_SYMLINK >&2; exit 4; }
ln -sfn "$RELEASE" "$ROOT/current.new"
mv -f "$ROOT/current.new" "$ROOT/current"
echo INSTALLED
