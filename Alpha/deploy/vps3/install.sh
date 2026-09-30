#!/usr/bin/env bash
# Alpha 影子盘(SHADOW)部署到 OVH VPS-3 —— 幂等,可重复执行;必须以 root 运行。
#
# 用法(推荐,提交号钉死,内容可复核):
#   curl -fsSL https://raw.githubusercontent.com/<org>/MetaDatabase/<SHA>/Alpha/deploy/vps3/install.sh \
#     | bash -s -- --repo https://github.com/<org>/MetaDatabase --sha <40位提交号> [--port 18730]
#
# 只写这三处:/opt/alpha、/var/lib/alpha、/etc/systemd/system/alpha*(缺失时另装 python3.12-venv)。
# 不做系统升级,不改防火墙/入侵防护/时区/数据库服务;主机上与本项目无关的一切原样不动。
# 退出码:0 部署完成并自检通过;2 环境文件里仍有待填项(单元已装好但未启用);其余为失败。
set -euo pipefail

REPO=""
SHA=""
PORT="18730"

APP=/opt/alpha/app
VENV=/opt/alpha/venv
ENV_FILE=/opt/alpha/env
BIN=/opt/alpha/bin
UNIT_DIR=/etc/systemd/system
PACK_REL=Alpha/deploy/vps3
LONG_SERVICES="alpha-trading-worker alpha-notify-worker alpha-supervisor alpha-control-page"
TIMERS="alpha-equity-snapshot alpha-preflight alpha-backup alpha-digest"

die() { echo "错误: $*" >&2; exit 1; }
say() { echo "==> $*"; }

parse_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --repo) REPO="${2:-}"; shift 2 ;;
      --sha) SHA="${2:-}"; shift 2 ;;
      --port) PORT="${2:-}"; shift 2 ;;
      *) die "未知参数: $1" ;;
    esac
  done
  [ -n "$REPO" ] || die "缺少必填参数 --repo <公开仓 https 地址>"
  [ -n "$SHA" ] || die "缺少必填参数 --sha <40 位提交号>"
  [[ "$REPO" =~ ^https://[A-Za-z0-9._/-]+$ ]] || die "--repo 必须是 https 地址"
  [[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || die "--sha 必须是 40 位小写十六进制提交号"
  [[ "$PORT" =~ ^[0-9]+$ ]] || die "--port 必须是数字"
  if [ "$PORT" -lt 1024 ] || [ "$PORT" -gt 65535 ] || [ "$PORT" -eq 8443 ]; then
    die "--port 必须在 1024-65535 且避开 8443(80/443/8443 被同机其它服务占用)"
  fi
}

check_prereqs() {
  [ "$(id -u)" -eq 0 ] || die "必须以 root 运行"
  local tool
  for tool in git curl ss systemctl systemd-run python3 python3.12; do
    command -v "$tool" >/dev/null 2>&1 || die "缺少命令 $tool"
  done
  if ! python3.12 -m venv --help >/dev/null 2>&1; then
    say "安装 python3.12-venv(唯一的系统包)"
    apt-get install -y --no-install-recommends python3.12-venv
  fi
}

ensure_user_and_dirs() {
  if ! id alpha >/dev/null 2>&1; then
    useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin alpha
  fi
  install -d -m 755 -o root -g root /opt/alpha "$BIN"
}

fetch_code() {
  say "取代码 $SHA"
  if [ ! -d "$APP/.git" ]; then
    git clone --filter=blob:none --no-checkout --sparse "$REPO" "$APP"
    git -C "$APP" sparse-checkout set Alpha
  else
    # 有人在主机上手改过已跟踪文件就中止,绝不用强制重置覆盖
    if [ -n "$(git -C "$APP" status --porcelain --untracked-files=no)" ]; then
      die "$APP 有未提交的手改,已中止(不会强制覆盖)"
    fi
  fi
  git -C "$APP" fetch --depth 1 origin "$SHA"
  git -C "$APP" checkout --detach "$SHA"
  [ -f "$APP/$PACK_REL/install.sh" ] || die "检出的提交里没有 $PACK_REL"
}

ensure_venv() {
  if [ ! -x "$VENV/bin/python" ]; then
    say "建虚拟环境 $VENV"
    python3.12 -m venv "$VENV"
  fi
  # 只装 pyproject 声明的运行依赖;不装 dev 组,也不在检出目录里构建包(避免写 egg-info)
  local deps=()
  mapfile -t deps < <("$VENV/bin/python" -c 'import tomllib;print("\n".join(tomllib.load(open("/opt/alpha/app/Alpha/pyproject.toml","rb"))["project"]["dependencies"]))')
  [ "${#deps[@]}" -gt 0 ] || die "读不到 pyproject 里的运行依赖"
  say "安装运行依赖(不留 pip 缓存)"
  "$VENV/bin/python" -m pip install --quiet --no-cache-dir --disable-pip-version-check "${deps[@]}"
  "$VENV/bin/python" -m pip check
}

ensure_env_file() {
  if [ -f "$ENV_FILE" ]; then
    say "$ENV_FILE 已存在,保持原样(绝不覆盖)"
    return
  fi
  say "生成 $ENV_FILE(root:root 600)"
  local token
  token="$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
  ( umask 077
    sed -e "s/<REQUIRED_PORT>/$PORT/" -e "s/<REQUIRED_RANDOM_TOKEN_64>/$token/" \
      "$APP/$PACK_REL/env.template" > "$ENV_FILE.new" )
  install -m 600 -o root -g root "$ENV_FILE.new" "$ENV_FILE"
  rm -f "$ENV_FILE.new"
}

pending_env_keys() {
  grep -E '^[A-Z_]+=.*<REQUIRED' "$ENV_FILE" | cut -d= -f1 || true
}

check_shadow_env() {
  # 以 alpha 身份、读同一份环境文件校验;有问题(券商账户/凭据/实盘开关)就非 0 退出,脚本中止
  systemd-run --wait --pipe --quiet --collect --uid=alpha --gid=alpha \
    --setenv=PYTHONDONTWRITEBYTECODE=1 \
    -p EnvironmentFile="$ENV_FILE" -p WorkingDirectory="$APP/Alpha" \
    "$VENV/bin/python" scripts/alpha_doctor.py --check-env
}

control_port() {
  local bind
  bind="$(sed -n 's/^ALPHA_CONTROL_BIND=//p' "$ENV_FILE" | tail -n 1)"
  [[ "$bind" =~ ^127\.0\.0\.1:([0-9]+)$ ]] || die "ALPHA_CONTROL_BIND 必须是 127.0.0.1:<端口>"
  echo "${BASH_REMATCH[1]}"
}

check_port_free() {
  local port="$1"
  if systemctl is-active --quiet alpha-control-page.service; then
    return 0
  fi
  if [ -n "$(ss -ltnH "sport = :$port")" ]; then
    die "端口 $port 已被别的进程占用,请换 --port(或改 $ENV_FILE 里的 ALPHA_CONTROL_BIND)"
  fi
}

install_units() {
  say "安装 systemd 单元(只认包内清单)"
  local src="$APP/$PACK_REL/systemd" f name
  local -a packaged=()
  for f in "$src"/*; do
    name="$(basename "$f")"
    packaged+=("$name")
    install -m 644 -o root -g root "$f" "$UNIT_DIR/$name"
  done
  # 清掉不在包内的 alpha-* 单元与覆盖目录(例如残留的自动切换/复判单元)
  local found base is_packaged p
  while IFS= read -r found; do
    [ -n "$found" ] || continue
    base="$(basename "$found")"
    is_packaged=0
    for p in "${packaged[@]}"; do
      if [ "$p" = "$base" ]; then is_packaged=1; fi
    done
    if [ "$is_packaged" -eq 0 ]; then
      say "移除包外单元 $base"
      systemctl disable --now "$base" >/dev/null 2>&1 || true
      rm -rf "${UNIT_DIR:?}/$base"
    fi
  done < <(find "$UNIT_DIR" -maxdepth 1 \( -name 'alpha-*' -o -name 'alpha.slice' \))
  systemctl daemon-reload
}

enable_units() {
  local u
  say "启用长驻服务与定时器"
  for u in $LONG_SERVICES; do
    systemctl enable "$u.service" >/dev/null
    systemctl restart "$u.service"
  done
  for u in $TIMERS; do
    systemctl enable --now "$u.timer" >/dev/null
  done
  # 让净值曲线立刻有第一个点;失败不阻断部署(体检会如实报告)
  if ! systemctl start alpha-equity-snapshot.service; then
    echo "提示: 首次净值快照未成功,稍后由定时器重试" >&2
  fi
}

write_doctor_wrapper() {
  cat > "$BIN/alpha-doctor" <<'WRAP'
#!/usr/bin/env bash
# 体检入口:以 alpha 身份、读同一份环境文件运行 alpha_doctor.py;参数原样透传。
exec systemd-run --wait --pipe --quiet --collect --uid=alpha --gid=alpha \
  --setenv=PYTHONDONTWRITEBYTECODE=1 \
  -p EnvironmentFile=/opt/alpha/env -p WorkingDirectory=/opt/alpha/app/Alpha \
  /opt/alpha/venv/bin/python scripts/alpha_doctor.py "$@"
WRAP
  chmod 755 "$BIN/alpha-doctor"
  chown root:root "$BIN/alpha-doctor"
}

doctor_core_green() {
  # 心跳、账本完整性、各单元都为绿才算过;别的红项(如刚部署还没有备份)由人话体检如实列出
  local json
  json="$("$BIN/alpha-doctor" --json 2>/dev/null)" || true
  [ -n "$json" ] || return 1
  printf '%s' "$json" | python3 -c '
import json, sys
checks = json.load(sys.stdin)["checks"]
core = [c for c in checks if c["key"].startswith(("hb:", "unit:")) or c["key"] == "db_quick_check"]
sys.exit(0 if core and all(c["ok"] for c in core) else 1)'
}

self_check() {
  local port="$1" deadline=$((SECONDS + 90)) u ok mode
  say "自检(最多等 90 秒)"
  while :; do
    ok=1
    for u in $LONG_SERVICES; do
      systemctl is-active --quiet "$u.service" || ok=0
    done
    for u in $TIMERS; do
      systemctl is-active --quiet "$u.timer" || ok=0
    done
    if [ "$ok" -eq 1 ] && [ -n "$(ss -ltnH "sport = :$port")" ]; then
      mode="$(curl -fsS --max-time 10 "http://127.0.0.1:$port/api/overview" 2>/dev/null \
        | python3 -c 'import json,sys;print(json.load(sys.stdin).get("mode_code",""))' 2>/dev/null || true)"
      if [ "$mode" = "SHADOW" ] && doctor_core_green; then
        return 0
      fi
    fi
    if [ "$SECONDS" -ge "$deadline" ]; then
      echo "自检未在 90 秒内通过,体检如下:" >&2
      "$BIN/alpha-doctor" >&2 || true
      return 1
    fi
    sleep 5
  done
}

main() {
  exec </dev/null   # 经管道执行时,子进程不许吞掉后面的脚本内容
  umask 022
  parse_args "$@"
  check_prereqs
  ensure_user_and_dirs
  fetch_code
  ensure_venv
  ensure_env_file

  local port missing
  port="$(control_port)"
  missing="$(pending_env_keys)"
  if [ -n "$missing" ]; then
    install_units
    write_doctor_wrapper
    echo "以下项还没填,服务已装好但未启用。请编辑 $ENV_FILE 后重跑本脚本:" >&2
    echo "$missing" >&2
    exit 2
  fi

  say "校验影子盘环境(不许出现券商账户/凭据/实盘开关)"
  check_shadow_env
  check_port_free "$port"
  install_units
  write_doctor_wrapper
  enable_units
  self_check "$port"
  echo "$SHA" > /opt/alpha/DEPLOYED_SHA
  say "部署完成,提交号 $SHA。体检结论:"
  "$BIN/alpha-doctor" || true
}

main "$@"
