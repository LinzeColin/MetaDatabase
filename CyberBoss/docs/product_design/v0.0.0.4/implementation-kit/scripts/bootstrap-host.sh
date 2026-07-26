#!/usr/bin/env bash
set -Eeuo pipefail

APPLY=0
while (($#)); do
  case "$1" in
    --apply) APPLY=1; shift ;;
    *) echo "BOOTSTRAP=FAIL unknown_arg:$1"; exit 2 ;;
  esac
done

PACKAGES=(git curl jq sqlite3 zstd rclone ca-certificates openssl tar unzip rsync shellcheck python3 python3-yaml)
MISSING=()
for cmd in git curl jq sqlite3 zstd rclone openssl tar unzip rsync shellcheck python3; do
  command -v "$cmd" >/dev/null 2>&1 || MISSING+=("$cmd")
done

if (( APPLY )); then
  [[ "$EUID" -eq 0 ]] || { echo 'BOOTSTRAP=FAIL root_required_for_apply'; exit 2; }
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends "${PACKAGES[@]}"
  else
    echo 'BOOTSTRAP=FAIL unsupported_package_manager; install listed packages with host-native manager'
    exit 2
  fi
fi

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
CODEX_VERSION="$(codex --version 2>/dev/null || true)"

printf 'BOOTSTRAP_APPLY=%s\n' "$APPLY"
printf 'NODE_MAJOR=%s\n' "$NODE_MAJOR"
printf 'CODEX_VERSION=%s\n' "${CODEX_VERSION:-missing}"

if (( NODE_MAJOR < 22 )); then
  echo 'ACTION_REQUIRED=install_or_pin_Node.js_22_plus_using_the_target_repository_approved_source'
fi
if [[ -z "$CODEX_VERSION" ]]; then
  echo 'ACTION_REQUIRED=install_and_pin_Codex_CLI_from_official_OpenAI_distribution'
fi
if ((${#MISSING[@]})); then
  printf 'MISSING_BEFORE_APPLY=%s\n' "$(IFS=,; echo "${MISSING[*]}")"
fi

echo 'BOOTSTRAP=PASS common_dependencies_processed'
