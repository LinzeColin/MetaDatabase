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
for required in pyproject.toml compose.yaml .env.example scripts/setup_wizard.py scripts/ensure_api_token.py scripts/status_server.py scripts/build_extension_package.py; do
  [[ -f "$required" ]] || fail "安装源文件缺失：$required"
done
if $DRY_RUN; then
  printf '预检通过：Python、Git、Docker/Compose 和安装源文件均可用。\n'
  printf '未创建 .env、runtime、Secret、venv、Docker network 或镜像；未运行向导。\n'
  exit 0
fi
mkdir -p runtime/{data,secrets,import,exports,vendor-src,evidence} runtime/vendor-output/{cli,xhs,kuaishou,douk}
# Core (uid/gid 10001) and the CLI sidecar (uid 10002, shared gid 10001)
# both need the explicit bind mounts.  Docker does not preserve image ownership
# for host paths created by root, so provision their ownership before startup.
if [[ "$(id -u)" == "0" ]]; then
  chown -R 10001:10001 runtime/data runtime/import runtime/vendor-output
  chmod 2770 runtime/data runtime/import runtime/vendor-output runtime/vendor-output/{cli,xhs,kuaishou,douk}
fi
chmod 700 runtime/secrets
# 这份清单必须覆盖 compose.yaml 里**每一个** file-based secret。
# Compose 对缺文件是硬错：少一个，docker compose up 直接起不来，
# 报的还是 Docker 自己的错，看不出是哪一环没建。
# 空占位是安全的——应用读到空值会返回 503 + 中文说明，而不是静默当成"没配也能跑"。
for name in r2_access_key_id r2_secret_access_key oci_access_key_id oci_secret_access_key github_token github_markdown_token private_database_token social_archive_api_token cli_worker_token instagram_session notion_token obsidian_rest_token karakeep_api_token linkwarden_api_token google_oauth_client_secret github_oauth_client_secret credential_age_identity x_oauth_token reddit_oauth_token; do
  [[ -e "runtime/secrets/$name" ]] || : > "runtime/secrets/$name"
  chmod 600 "runtime/secrets/$name"
done
# **挂进容器的那些，容器必须读得到。**
#
# 这条不变量此前**只存在于一句注释里**（scripts/prepare_systemd_host.sh:205
# 写着「/run/secrets/* 10001:10001 0640」），没有任何一行代码去落实它。
# 生产上那些 0640 是不知哪一次手敲出来的，而 instagram_session 被漏掉了，
# 一直是 0600。
#
# 后果：cli-tools 跑在 uid 10002 / gid 10001，0600 owner=10001 一点权限都不给。
# 2026-08-04 实测，Instagram 连接器返回
# `[Errno 13] Permission denied: '/run/secrets/instagram_session'`
# ——**不管有没有配 session，它从来就没能工作过。**
#
# 名单从 compose.yaml 自己读，不在这里再抄一份：抄的那份必然漂开。
mounted="$("$PYTHON" - <<'PYMOUNTED'
import pathlib, re
text = pathlib.Path("compose.yaml").read_text(encoding="utf-8")
# 服务块里的 secrets 引用（含 `- source: x` 形式）。定义块在文件末尾的顶层
# `secrets:` 里，那里是 `name: {file: …}`，不带前导 `- `，天然不会被这条匹配到。
names = set(re.findall(r"^\s+-\s+(?:source:\s*)?([a-z0-9_]+)\s*$", text, re.M))
print(" ".join(sorted(names)))
PYMOUNTED
)"
for name in $mounted; do
  [[ -e "runtime/secrets/$name" ]] || continue
  chmod 640 "runtime/secrets/$name"
done
if [[ "$(id -u)" == "0" ]]; then
  for name in $mounted; do
    [[ -e "runtime/secrets/$name" ]] || continue
    chown 10001:10001 "runtime/secrets/$name"
  done
fi
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
# Keep the host-side package current for the local API/download route.  The
# Dockerfile repeats this build inside the image so a clean checkout cannot
# inherit a stale generated ZIP.
"$PYTHON" scripts/build_extension_package.py
docker network inspect social-archive-readers >/dev/null 2>&1 || docker network create social-archive-readers >/dev/null
docker compose build core-api core-worker cli-tools
printf '\n安装完成。下一步只需运行：bash scripts/start.sh\n'
