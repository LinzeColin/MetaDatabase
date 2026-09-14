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
VERSION="$("$PYTHON" - "$PROJECT_ROOT/pyproject.toml" <<'PY'
import sys
import tomllib
with open(sys.argv[1], "rb") as handle:
    print(tomllib.load(handle)["project"]["version"])
PY
)"
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
WHEEL="${1:?wheel path required}"
RELEASE="$ROOT/releases/$VERSION"
WHEEL_ABS="$(cd "$(dirname "$WHEEL")" && pwd)/$(basename "$WHEEL")"
[[ -f "$WHEEL_ABS" ]] || { echo WHEEL_NOT_FOUND >&2; exit 2; }
WHEEL_SHA="$(sha256sum "$WHEEL_ABS" | awk '{print $1}')"
RECEIPT="$RELEASE/release.json"

activate_current() {
  "$PYTHON" - "$ROOT/current.new" "$ROOT/current" "$ROOT/previous" "$ROOT/releases" <<'PY'
import os, sys
from pathlib import Path

staged, active, previous, releases = (Path(value) for value in sys.argv[1:])
if not staged.is_symlink():
    raise SystemExit("CURRENT_STAGING_LINK_INVALID")
if active.exists() and not active.is_symlink():
    raise SystemExit("CURRENT_TARGET_NOT_SYMLINK")
if active.is_symlink():
    old_release = active.resolve()
    if old_release.parent != releases or not old_release.is_dir():
        raise SystemExit("CURRENT_RELEASE_OUTSIDE_ALLOWED_ROOT")
    previous_new = previous.with_name("previous.new")
    if previous_new.exists() or previous_new.is_symlink():
        previous_new.unlink()
    os.symlink(old_release, previous_new)
    os.replace(previous_new, previous)
os.replace(staged, active)
PY
}

# A Python virtual environment is not relocatable because console-script shebangs
# contain the absolute interpreter path. Build directly in the immutable final
# release directory, keep the active `current` symlink untouched until all smoke
# checks pass, and delete the incomplete release on any failure.
if [[ -d "$RELEASE" ]]; then
  if [[ -f "$RECEIPT" ]] && "$PYTHON" - "$RECEIPT" "$WHEEL_SHA" "$VERSION" <<'PY'
import json,sys
p,expected,version=sys.argv[1:]
d=json.load(open(p))
raise SystemExit(0 if d.get('wheel_sha256')==expected and d.get('version')==version and d.get('state')=='INSTALLED' else 1)
PY
  then
    [[ -x "$RELEASE/venv/bin/signal-lattice" ]] || { echo EXISTING_RELEASE_INCOMPLETE >&2; exit 4; }
    env -u PYTHONPATH -u PYTHONHOME "$RELEASE/venv/bin/signal-lattice" --help >/dev/null
    ln -sfn "$RELEASE" "$ROOT/current.new"
    activate_current
    echo ALREADY_INSTALLED
    exit 0
  fi
  echo VERSION_COLLISION >&2
  exit 4
fi

install -d -m 0755 "$ROOT/releases"
install -d -m 0755 "$RELEASE"
SMOKE_STATE="$(mktemp -d)"
cleanup_failed_release() {
  status=$?
  rm -rf "$SMOKE_STATE"
  if [[ $status -ne 0 ]]; then
    rm -rf "$RELEASE"
  fi
  exit $status
}
trap cleanup_failed_release EXIT

"$PYTHON" -m venv "$RELEASE/venv"
env -u PYTHONPATH -u PYTHONHOME PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 \
  "$RELEASE/venv/bin/python" -m pip install --no-index --no-deps --force-reinstall "$WHEEL_ABS"
cp -a "$PROJECT_ROOT/web" "$RELEASE/web"
cp -a "$PROJECT_ROOT/db" "$RELEASE/db"
cp -a "$PROJECT_ROOT/scripts" "$RELEASE/scripts"
cp -a "$PROJECT_ROOT/config" "$RELEASE/config"
cp -a "$PROJECT_ROOT/requirements" "$RELEASE/requirements"

# The immutable release is built by root but executed by the dedicated service
# account.  It contains no credentials; make its code and directories readable
# and traversable without weakening the separately protected runtime state.
chmod -R a+rX "$RELEASE"

# Run smoke checks from the final absolute path before making it active. This
# detects broken console-script shebangs and source-tree PYTHONPATH leakage.
env -u PYTHONPATH -u PYTHONHOME SIGNAL_LATTICE_STATE_DIR="$SMOKE_STATE" \
  SIGNAL_LATTICE_WEB_DIR="$RELEASE/web" "$RELEASE/venv/bin/signal-lattice" verify-runtime
[[ "$(env -u PYTHONPATH -u PYTHONHOME "$RELEASE/venv/bin/signal-lattice" --version)" == "$VERSION" ]] || {
  echo RELEASE_VERSION_MISMATCH >&2
  exit 5
}
env -u PYTHONPATH -u PYTHONHOME "$RELEASE/venv/bin/signal-lattice" --help >/dev/null

"$PYTHON" - "$RECEIPT" "$VERSION" "$WHEEL_SHA" "$(basename "$WHEEL_ABS")" <<'PY'
import json,os,sys,tempfile
from pathlib import Path
out=Path(sys.argv[1])
payload={
    'schema_version':'1.1.0',
    'state':'INSTALLED',
    'version':sys.argv[2],
    'wheel_sha256':sys.argv[3],
    'wheel_name':sys.argv[4],
    'install_path':str(out.parent),
    'relocatable_venv':False,
    'console_script_verified':True,
}
fd,tmp=tempfile.mkstemp(prefix='.release.',dir=out.parent)
with os.fdopen(fd,'w') as f:
    json.dump(payload,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
os.chmod(tmp,0o644);os.replace(tmp,out)
PY

ln -sfn "$RELEASE" "$ROOT/current.new"
activate_current
rm -rf "$SMOKE_STATE"
trap - EXIT
echo INSTALLED
