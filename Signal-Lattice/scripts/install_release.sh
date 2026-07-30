#!/usr/bin/env bash
set -euo pipefail
umask 027
VERSION="0.0.0.1.40"
WHEEL="${1:?wheel path required}"
ROOT="${SIGNAL_LATTICE_INSTALL_ROOT:-/opt/signal-lattice}"
BASE_RELEASE="$ROOT/releases/$VERSION"
RELEASE="$BASE_RELEASE"
SOURCE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WHEEL_ABS="$(cd "$(dirname "$WHEEL")" && pwd)/$(basename "$WHEEL")"
[[ -f "$WHEEL_ABS" ]] || { echo WHEEL_NOT_FOUND >&2; exit 2; }
WHEEL_SHA="$(sha256sum "$WHEEL_ABS" | awk '{print $1}')"
REPAIR_REPLACE="${SIGNAL_LATTICE_REPAIR_REPLACE:-0}"
REPAIR_OF_WHEEL_SHA=""
RELEASE_PAYLOAD_SHA=""
RECEIPT="$BASE_RELEASE/release.json"

if [[ -d "$BASE_RELEASE" ]]; then
  if [[ -f "$RECEIPT" ]] && python3 - "$RECEIPT" "$WHEEL_SHA" "$VERSION" <<'PY'
import json,sys
p,expected,version=sys.argv[1:]
d=json.load(open(p))
raise SystemExit(0 if d.get('wheel_sha256')==expected and d.get('version')==version and d.get('state')=='INSTALLED' else 1)
PY
  then
    if [[ "$REPAIR_REPLACE" != "1" ]]; then
      [[ -x "$BASE_RELEASE/venv/bin/signal-lattice" ]] || { echo EXISTING_RELEASE_INCOMPLETE >&2; exit 4; }
      ln -sfn "$BASE_RELEASE" "$ROOT/current.new"
      mv -Tf "$ROOT/current.new" "$ROOT/current"
      echo ALREADY_INSTALLED
      exit 0
    fi
  fi
  if [[ "$REPAIR_REPLACE" != "1" || "${SIGNAL_LATTICE_APPLY:-0}" != "1" || "$(id -u)" -ne 0 ]]; then
    echo VERSION_COLLISION >&2
    exit 4
  fi
  REPAIR_OF_WHEEL_SHA="$(python3 - "$RECEIPT" "$VERSION" <<'PY'
import json,re,sys
p,version=sys.argv[1:]
d=json.load(open(p))
sha=str(d.get('wheel_sha256',''))
if d.get('state')!='INSTALLED' or d.get('version')!=version or not re.fullmatch(r'[0-9a-f]{64}',sha):
    raise SystemExit(2)
print(sha)
PY
)" || { echo EXISTING_RELEASE_INVALID_FOR_REPAIR >&2; exit 4; }
  RELEASE_PAYLOAD_SHA="$(python3 - "$SOURCE_ROOT" <<'PY'
import hashlib,sys
from pathlib import Path

root=Path(sys.argv[1])
digest=hashlib.sha256()
for section in ("web", "db", "scripts", "config"):
    base=root/section
    if not base.is_dir():
        raise SystemExit(2)
    for path in sorted(base.rglob("*")):
        if path.is_dir() or path.is_symlink() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative=path.relative_to(root).as_posix().encode("utf-8")
        content=path.read_bytes()
        digest.update(len(relative).to_bytes(8,"big"));digest.update(relative)
        digest.update(len(content).to_bytes(8,"big"));digest.update(content)
print(digest.hexdigest())
PY
)" || { echo RELEASE_PAYLOAD_HASH_FAILED >&2; exit 4; }
  RELEASE="$ROOT/releases/${VERSION}.repair-${WHEEL_SHA}-${RELEASE_PAYLOAD_SHA}"
  RECEIPT="$RELEASE/release.json"
  if [[ -d "$RELEASE" ]]; then
    if [[ -f "$RECEIPT" ]] && python3 - "$RECEIPT" "$WHEEL_SHA" "$VERSION" "$RELEASE_PAYLOAD_SHA" <<'PY'
import json,sys
p,expected,version,payload_sha=sys.argv[1:]
d=json.load(open(p))
raise SystemExit(0 if d.get('wheel_sha256')==expected and d.get('version')==version and d.get('state')=='INSTALLED' and d.get('release_payload_sha256')==payload_sha else 1)
PY
    then
      [[ -x "$RELEASE/venv/bin/signal-lattice" ]] || { echo EXISTING_REPAIR_RELEASE_INCOMPLETE >&2; exit 4; }
      ln -sfn "$RELEASE" "$ROOT/current.new"
      mv -Tf "$ROOT/current.new" "$ROOT/current"
      echo REPAIR_ALREADY_INSTALLED
      exit 0
    fi
    echo REPAIR_RELEASE_COLLISION >&2
    exit 4
  fi
fi

install -d -m 0755 "$ROOT/releases"
TMP_RELEASE="$ROOT/releases/.${RELEASE##*/}.tmp.$$"
trap 'rm -rf "$TMP_RELEASE"' EXIT
[[ ! -e "$TMP_RELEASE" ]] || { echo TEMP_RELEASE_EXISTS >&2; exit 5; }
install -d -m 0755 "$TMP_RELEASE"
python3 -m venv "$TMP_RELEASE/venv"
env -u PYTHONPATH -u PYTHONHOME PIP_NO_INDEX=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
  "$TMP_RELEASE/venv/bin/python" -m pip install --no-index --no-deps --force-reinstall "$WHEEL_ABS"
cp -a "$SOURCE_ROOT/web" "$TMP_RELEASE/web"
cp -a "$SOURCE_ROOT/db" "$TMP_RELEASE/db"
cp -a "$SOURCE_ROOT/scripts" "$TMP_RELEASE/scripts"
cp -a "$SOURCE_ROOT/config" "$TMP_RELEASE/config"
# The release contains code and safe defaults only; credentials remain under /etc.
# The service account must be able to traverse the immutable venv and read package code.
find "$TMP_RELEASE" -type d -exec chmod a+rx {} +
find "$TMP_RELEASE" -type f -exec chmod a+r {} +
python3 - "$TMP_RELEASE/release.json" "$VERSION" "$WHEEL_SHA" "$(basename "$WHEEL_ABS")" "$REPAIR_OF_WHEEL_SHA" "$RELEASE_PAYLOAD_SHA" <<'PY'
import json,os,sys,tempfile
from pathlib import Path
out=Path(sys.argv[1]);payload={'schema_version':'1.0.0','state':'INSTALLED','version':sys.argv[2],'wheel_sha256':sys.argv[3],'wheel_name':sys.argv[4]}
if sys.argv[5]:payload['repair_of_wheel_sha256']=sys.argv[5]
if sys.argv[6]:payload['release_payload_sha256']=sys.argv[6]
fd,tmp=tempfile.mkstemp(prefix='.release.',dir=out.parent)
with os.fdopen(fd,'w') as f:json.dump(payload,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
os.chmod(tmp,0o644);os.replace(tmp,out)
PY
SMOKE_STATE="$(mktemp -d)"
trap 'rm -rf "$TMP_RELEASE" "$SMOKE_STATE"' EXIT
env -u PYTHONPATH -u PYTHONHOME SIGNAL_LATTICE_STATE_DIR="$SMOKE_STATE" \
  SIGNAL_LATTICE_WEB_DIR="$TMP_RELEASE/web" "$TMP_RELEASE/venv/bin/signal-lattice" verify-runtime
# pip generates console-script shebangs using the temporary venv's absolute path.
# Rewrite the one shipped entrypoint before the atomic directory move so the installed
# release never points at a removed .tmp release directory.
python3 - "$TMP_RELEASE/venv/bin/signal-lattice" "$TMP_RELEASE" "$RELEASE" <<'PY'
from pathlib import Path
import sys

entry, temporary, release = map(Path, sys.argv[1:])
raw = entry.read_bytes()
temporary_bin = str(temporary / "venv" / "bin").encode()
release_bin = str(release / "venv" / "bin").encode()
# distlib uses a direct Python shebang for ordinary paths but emits a /bin/sh
# launcher when the interpreter path exceeds the kernel shebang limit.  Both
# formats contain exactly one controlled temporary venv path.
if not raw.startswith(b"#!") or raw.count(temporary_bin) != 1:
    raise SystemExit("RELOCATABLE_ENTRYPOINT_UNEXPECTED")
entry.write_bytes(raw.replace(temporary_bin, release_bin))
PY
mv "$TMP_RELEASE" "$RELEASE"
trap 'rm -rf "$SMOKE_STATE"' EXIT
env -u PYTHONPATH -u PYTHONHOME SIGNAL_LATTICE_STATE_DIR="$SMOKE_STATE" \
  SIGNAL_LATTICE_WEB_DIR="$RELEASE/web" "$RELEASE/venv/bin/signal-lattice" verify-runtime
if [[ -n "$REPAIR_OF_WHEEL_SHA" ]]; then
  ln -sfn "$BASE_RELEASE" "$ROOT/previous.new"
  mv -Tf "$ROOT/previous.new" "$ROOT/previous"
fi
ln -sfn "$RELEASE" "$ROOT/current.new"
mv -Tf "$ROOT/current.new" "$ROOT/current"
if [[ -n "$REPAIR_OF_WHEEL_SHA" ]]; then
  echo REPAIRED
else
  echo INSTALLED
fi
