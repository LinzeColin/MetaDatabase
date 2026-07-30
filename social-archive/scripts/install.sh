#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    *) printf '安装停止：未知参数 %s\n' "$arg" >&2; exit 2 ;;
  esac
done
cd "$ROOT"
fail(){ printf '安装停止：%s\n' "$1" >&2; exit 2; }
command -v git >/dev/null || fail '缺少 Git。请先安装系统 Git。'
command -v age >/dev/null || fail '缺少 age。请先安装 age 命令后再继续。'
command -v age-keygen >/dev/null || fail '缺少 age-keygen。请先安装 age 命令包后再继续。'
PYTHON=''
for candidate in python3.13 python3.12 python3; do
  command -v "$candidate" >/dev/null 2>&1 || continue
  if "$candidate" - <<'PYVER' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 12) else 1)
PYVER
  then
    PYTHON="$candidate"
    break
  fi
done
[[ -n "$PYTHON" ]] || fail '需要 Python 3.12 或更高版本（可使用 python3.12）。'
command -v docker >/dev/null || fail '缺少 Docker。OVH Ubuntu 请按 Docker 官方仓库安装 Docker Engine 与 Compose plugin。'
docker compose version >/dev/null 2>&1 || fail '缺少 docker compose plugin。'
for required in pyproject.toml compose.yaml .env.example scripts/setup_wizard.py scripts/generate_pairing_code.py scripts/status_server.py; do
  [[ -f "$required" ]] || fail "安装源文件缺失：$required"
done
if $DRY_RUN; then
  printf '预检通过：Python、Git、Docker/Compose 和安装源文件均可用。\n'
  printf '未创建 .env、runtime、Secret、配对码、venv、Docker network 或镜像；未运行向导。\n'
  exit 0
fi
mkdir -p runtime/{secrets,import,exports,vendor-src,evidence} runtime/vendor-output/{cli,xhs,kuaishou,douk}
# Core (uid/gid 10001) and the CLI sidecar (uid 10002, shared gid 10001)
# both need the explicit bind mounts.  Docker does not preserve image ownership
# for host paths created by root, so provision their ownership before startup.
if [[ "$(id -u)" == "0" ]]; then
  chown -R 10001:10001 runtime/import runtime/vendor-output
  chmod 2770 runtime/import runtime/vendor-output runtime/vendor-output/{cli,xhs,kuaishou,douk}
fi
chmod 700 runtime/secrets
for name in r2_access_key_id r2_secret_access_key oci_access_key_id oci_secret_access_key github_token social_archive_api_token social_archive_pairing_code cli_worker_token instagram_session notion_token obsidian_rest_token karakeep_api_token linkwarden_api_token; do
  [[ -e "runtime/secrets/$name" ]] || : > "runtime/secrets/$name"
  chmod 600 "runtime/secrets/$name"
done
"$PYTHON" - <<'PYSECRETS'
from pathlib import Path
import secrets
root=Path('runtime/secrets');root.mkdir(parents=True,exist_ok=True)
for generated in ('social_archive_api_token','cli_worker_token'):
    path=root/generated
    if not path.read_text(encoding='utf-8').strip(): path.write_text(secrets.token_urlsafe(32)+'\n',encoding='utf-8')
    path.chmod(0o600)
def ensure(path:Path, lines:list[str]):
    if not path.exists() or not path.read_text(encoding='utf-8').strip():
        path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    path.chmod(0o600)
ensure(root/'karakeep.env',[
    'NEXTAUTH_URL=http://localhost:3000',
    f'NEXTAUTH_SECRET={secrets.token_hex(32)}',
    'MEILI_ADDR=http://karakeep-meilisearch:7700',
    f'MEILI_MASTER_KEY={secrets.token_hex(32)}',
    'BROWSER_WEB_URL=http://karakeep-chrome:9222',
    'DATA_DIR=/data',
])
pw=secrets.token_hex(24)
ensure(root/'linkwarden.env',[
    'POSTGRES_DB=linkwarden','POSTGRES_USER=linkwarden',f'POSTGRES_PASSWORD={pw}',
    f'DATABASE_URL=postgresql://linkwarden:{pw}@linkwarden-postgres:5432/linkwarden',
    'NEXTAUTH_URL=http://localhost:3001',f'NEXTAUTH_SECRET={secrets.token_hex(32)}',
])
PYSECRETS
PAIRING_CODE="$("$PYTHON" scripts/generate_pairing_code.py --code-file runtime/secrets/social_archive_pairing_code --token-file runtime/secrets/social_archive_api_token --ttl-seconds 600)"
[[ -f .env ]] || cp .env.example .env
"$PYTHON" scripts/setup_wizard.py --non-interactive
if [[ -t 0 && "${SOCIAL_ARCHIVE_SKIP_WIZARD:-0}" != "1" ]]; then
  "$PYTHON" scripts/setup_wizard.py
fi
"$PYTHON" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e '.[test]'
.venv/bin/python scripts/vendor_sync.py --resolve-only --enabled-defaults
# cli-tools copies the pinned Apache-2.0 Bilibili CLI from a named build
# context.  It must therefore be checked out before the image build; the
# default vendor pass deliberately resolves only source-less pip sidecars.
.venv/bin/python scripts/vendor_sync.py --source bilibili_cli --resolve-and-lock
docker network inspect social-archive-readers >/dev/null 2>&1 || docker network create social-archive-readers >/dev/null
docker compose build core-api core-worker cli-tools
printf '\n安装完成。当前一次性配对码：%s\n下一步只需运行：bash scripts/start.sh\n' "$PAIRING_CODE"
