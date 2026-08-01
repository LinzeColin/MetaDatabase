#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
SELF_TEST=false; BUNDLE=false
for arg in "$@"; do
  case "$arg" in
    --self-test) SELF_TEST=true ;;
    --bundle) BUNDLE=true ;;
    *) printf '诊断停止：未知参数 %s\n' "$arg" >&2; exit 2 ;;
  esac
done
if $SELF_TEST && $BUNDLE; then
  printf '诊断停止：--self-test 是零写入静态检查，不能与 --bundle 同时使用。\n' >&2
  exit 2
fi
PYTHON=(python3)
[[ -x .venv/bin/python ]] && PYTHON=(.venv/bin/python)
if $SELF_TEST; then
  printf 'Social Archive 零写入自检\n========================\n'
  printf '解释器：'; "${PYTHON[@]}" --version
  for shell_script in scripts/install.sh scripts/doctor.sh scripts/start.sh scripts/prepare_systemd_host.sh scripts/restore_object.sh scripts/restore_object_systemd.sh; do
    /bin/bash -n "$shell_script"
  done
  "${PYTHON[@]}" - <<'PY'
from pathlib import Path

for root in (Path("src"), Path("scripts")):
    for source in root.rglob("*.py"):
        compile(source.read_text(encoding="utf-8"), str(source), "exec")
PY
  "${PYTHON[@]}" scripts/check_brand.py
  "${PYTHON[@]}" scripts/validate_compose.py --static compose.yaml
  "${PYTHON[@]}" scripts/validate_systemd.py
  "${PYTHON[@]}" scripts/validate_deployment_contract.py
  printf '自检通过：未连接 Docker、未请求 loopback/外网、未读取或写入 runtime/Secret。\n'
  exit 0
fi
core_loopback_port() {
  local value="${SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT:-}"
  if [[ -z "$value" && -f .env ]]; then
    value="$(awk -F= '$1 == "SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT" {value=$2} END {print value}' .env | tr -d '[:space:]')"
  fi
  value="${value:-18765}"
  if ! [[ "$value" =~ ^[0-9]+$ ]] || (( value < 1 || value > 65535 )); then
    printf '诊断停止：SOCIAL_ARCHIVE_CORE_LOOPBACK_PORT 必须介于 1 和 65535。\n' >&2
    exit 2
  fi
  printf '%s\n' "$value"
}
CORE_LOOPBACK_PORT="$(core_loopback_port)"
CORE_LOOPBACK_URL="http://127.0.0.1:${CORE_LOOPBACK_PORT}"
printf 'Social Archive 诊断\n===================\n'
printf '项目版本：'; cat VERSION
printf 'Docker：'; docker --version 2>/dev/null || printf '不可用\n'
printf 'Compose：'; docker compose version 2>/dev/null || printf '不可用\n'
printf 'Core API：'; curl -fsS "${CORE_LOOPBACK_URL}/health" 2>/dev/null || printf '{"status":"down"}\n'
printf '\n容器状态：\n'; docker compose ps 2>/dev/null || true
printf '\n秘密文件权限：\n'
if [[ -d runtime/secrets ]]; then
  find runtime/secrets -maxdepth 1 -type f -print0 | while IFS= read -r -d '' f; do mode=$(stat -c '%a' "$f" 2>/dev/null || stat -f '%Lp' "$f"); [[ "$mode" == "600" || "$mode" == "400" || "$mode" == "0" ]] && printf 'PASS %s\n' "$(basename "$f")" || printf 'FAIL %s mode=%s\n' "$(basename "$f")" "$mode"; done
else
  printf '未配置；未读取秘密文件。\n'
fi
if $BUNDLE; then
  out="runtime/evidence/diagnostic-$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$out"
  (docker compose ps --format json 2>/dev/null || true) > "$out/compose-ps.json"
  (curl -fsS "${CORE_LOOPBACK_URL}/health" 2>/dev/null || true) > "$out/health.json"
  (curl -fsS "${CORE_LOOPBACK_URL}/v1/status-projection" 2>/dev/null || true) > "$out/status.json"
  "${PYTHON[@]}" scripts/secret_scan.py "$out"
  tar -czf "$out.tar.gz" -C "$(dirname "$out")" "$(basename "$out")"
  printf '脱敏诊断包：%s.tar.gz\n' "$out"
fi
