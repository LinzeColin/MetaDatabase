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
# **两类密钥，两种正确权限。**
#
# 原来这里一律要求 600/400/0，于是 2026-08-04 在生产上打出 16 个 FAIL
# ——而那 16 个文件全都是**对的**：挂进容器的密钥必须是 0640，
# 容器（core 跑 uid 10001、cli-tools 跑 uid 10002 / gid 10001）只能靠组权限读。
# 这条不变量写在 scripts/prepare_systemd_host.sh:205，由 install.sh 落实。
#
# 一个总是喊狼来了的诊断，用不了几次就会被人整段跳过。
#
# 挂载名单从 compose.yaml 读，不在这里抄第二份——抄的那份必然漂开
# （instagram_session 就是那么被漏掉的）。
if [[ -d runtime/secrets ]]; then
  MOUNTED="$("${PYTHON[@]}" - <<'PYMOUNTED'
import pathlib, re
text = pathlib.Path("compose.yaml").read_text(encoding="utf-8")
print(" ".join(sorted(set(re.findall(r"^\s+-\s+(?:source:\s*)?([a-z0-9_]+)\s*$", text, re.M)))))
PYMOUNTED
)"
  find runtime/secrets -maxdepth 1 -type f -print0 | while IFS= read -r -d '' f; do
    name="$(basename "$f")"
    mode=$(stat -c '%a' "$f" 2>/dev/null || stat -f '%Lp' "$f")
    if [[ " $MOUNTED " == *" $name "* ]]; then
      # 挂进容器的：必须给组读，且不许给别人
      case "$mode" in
        640|440) printf 'PASS %s mode=%s（挂进容器，组可读）\n' "$name" "$mode" ;;
        *) printf 'FAIL %s mode=%s —— 挂进容器的密钥必须是 0640，否则容器读不到\n' "$name" "$mode" ;;
      esac
    else
      case "$mode" in
        600|400|0) printf 'PASS %s mode=%s（仅宿主使用）\n' "$name" "$mode" ;;
        *) printf 'FAIL %s mode=%s —— 仅宿主使用的密钥不该给组或别人\n' "$name" "$mode" ;;
      esac
    fi
  done
else
  printf '未配置；未读取秘密文件。\n'
fi

printf '\n备份私钥（这一条永远提醒）：\n'
# **三份副本，一把钥匙。**
#
# 2026-08-04 实测：制品 552 个各有三份已验证副本，运行库索引有两份远程副本，
# 而解开它们的 age 私钥**全机只有一份**（按内容哈希全盘搜，命中 1 处）。
# 备份与复制脚本一处都不提它——**这是对的**，私钥绝不能进它保护的那些仓。
#
# 后果直说：这台机器毁了，三个云上那些副本**一份也解不开**。
#
# 产品无法验证你有没有在别处存过这把钥匙（那正是它安全的原因），
# 所以这一条不做「通过/失败」，只做**永远提醒**。
if [[ -f runtime/secrets/age_identity.txt ]]; then
  printf '  备份私钥在：runtime/secrets/age_identity.txt（%s 字节）\n' "$(stat -c '%s' runtime/secrets/age_identity.txt 2>/dev/null || stat -f '%z' runtime/secrets/age_identity.txt)"
  printf '  这把钥匙**只在这台机器上**。机器毁了，R2/OCI/GitHub 上的副本一份也解不开。\n'
  printf '  在别处存一份（打印出来放抽屉、或存进密码管理器都行）。**别把它放进任何一个对象仓。**\n'
else
  printf '  没找到 runtime/secrets/age_identity.txt —— 现有备份将无法解密。\n'
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
