#!/usr/bin/env bash
# Run one object recovery through a collected, root-only systemd credential
# scope.  This is intentionally an operator command, not a timer or service.
set -euo pipefail

ROOT="/opt/social-archive"
HOST_ENV="/etc/social-archive/social-archive.env"

usage() {
  printf '%s\n' '用法：sudo bash scripts/restore_object_systemd.sh --artifact-id <ID> --from-store r2|oci|github [--target <全新隔离目录>] [--verify-only] [--dry-run]'
}

artifact_id=""
store=""
target=""
verify_only=0
dry_run=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --artifact-id)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      artifact_id="$2"
      shift 2
      ;;
    --from-store)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      store="$2"
      shift 2
      ;;
    --target)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      target="$2"
      shift 2
      ;;
    --verify-only)
      verify_only=1
      shift
      ;;
    --dry-run)
      dry_run=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

[[ "$(id -u)" == "0" ]] || { printf '%s\n' '恢复包装器必须由 root 运行，以便 PID 1 读取 root-only source secret。' >&2; exit 3; }
[[ -d "$ROOT" && -x "$ROOT/.venv/bin/python" && -f "$ROOT/scripts/restore_object.py" ]] || { printf '%s\n' 'Social Archive 恢复入口未安装。' >&2; exit 3; }
[[ -f "$HOST_ENV" ]] || { printf '%s\n' '缺少受控宿主环境文件。' >&2; exit 3; }
[[ -n "$artifact_id" ]] || { printf '%s\n' '必须指定 artifact ID。' >&2; exit 2; }
case "$store" in
  r2|oci|github) ;;
  *) printf '%s\n' '恢复目标只能是 r2、oci 或 github。' >&2; exit 2 ;;
esac
if [[ "$verify_only" != "1" && -z "$target" ]]; then
  printf '%s\n' '实际恢复必须指定新的空目录；只读验证请显式使用 --verify-only。' >&2
  exit 2
fi
command -v systemd-run >/dev/null || { printf '%s\n' '缺少 systemd-run。' >&2; exit 3; }

credential_properties=()
case "$store" in
  r2)
    credential_properties=(
      --property=LoadCredential=r2_access_key_id:/opt/social-archive/runtime/secrets/r2_access_key_id
      --property=LoadCredential=r2_secret_access_key:/opt/social-archive/runtime/secrets/r2_secret_access_key
    )
    ;;
  oci)
    credential_properties=(
      --property=LoadCredential=oci_access_key_id:/opt/social-archive/runtime/secrets/oci_access_key_id
      --property=LoadCredential=oci_secret_access_key:/opt/social-archive/runtime/secrets/oci_secret_access_key
    )
    ;;
  github)
    credential_properties=(
      --property=LoadCredential=github_token:/opt/social-archive/runtime/secrets/github_token
    )
    ;;
esac

bootstrap='set -euo pipefail
set -a
. /etc/social-archive/social-archive.env
set +a
case "$1" in
  r2)
    export SOCIAL_ARCHIVE_R2_ACCESS_KEY_ID_FILE="$CREDENTIALS_DIRECTORY/r2_access_key_id"
    export SOCIAL_ARCHIVE_R2_SECRET_ACCESS_KEY_FILE="$CREDENTIALS_DIRECTORY/r2_secret_access_key"
    ;;
  oci)
    export SOCIAL_ARCHIVE_OCI_ACCESS_KEY_ID_FILE="$CREDENTIALS_DIRECTORY/oci_access_key_id"
    export SOCIAL_ARCHIVE_OCI_SECRET_ACCESS_KEY_FILE="$CREDENTIALS_DIRECTORY/oci_secret_access_key"
    ;;
  github)
    export SOCIAL_ARCHIVE_GITHUB_TOKEN_FILE="$CREDENTIALS_DIRECTORY/github_token"
    ;;
esac
if [[ "$4" == "1" && "$5" == "1" ]]; then
  exec /opt/social-archive/.venv/bin/python /opt/social-archive/scripts/restore_object.py --artifact-id "$2" --from-store "$1" --verify-only --dry-run
elif [[ "$4" == "1" ]]; then
  exec /opt/social-archive/.venv/bin/python /opt/social-archive/scripts/restore_object.py --artifact-id "$2" --from-store "$1" --verify-only
elif [[ "$5" == "1" ]]; then
  exec /opt/social-archive/.venv/bin/python /opt/social-archive/scripts/restore_object.py --artifact-id "$2" --from-store "$1" --target "$3" --dry-run
fi
exec /opt/social-archive/.venv/bin/python /opt/social-archive/scripts/restore_object.py --artifact-id "$2" --from-store "$1" --target "$3"'

exec systemd-run --wait --collect --pipe \
  --property=Type=exec \
  --property=WorkingDirectory="$ROOT" \
  --property=NoNewPrivileges=yes \
  --property=PrivateTmp=yes \
  "${credential_properties[@]}" \
  /bin/bash -c "$bootstrap" social-archive-object-recovery "$store" "$artifact_id" "$target" "$verify_only" "$dry_run"
