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
# **恢复目标不能落在 /tmp 或 /var/tmp 下。**
#
# 这个包装脚本用 systemd-run 起单元，带着 `--property=PrivateTmp=yes`——
# 那意味着单元看到的 /tmp 与 /var/tmp 是**私有的 tmpfs**，单元一退出就没了。
#
# 2026-08-04 实测：`--target /tmp/xxx/restored.bin` 返回
# `{"status":"PASS", ..., "target_written": true}`，而宿主机上那个目录**是空的**。
# **真出事的时候，你会以为文件已经恢复出来了，手里却什么都没有。**
#
# PrivateTmp 本身是对的（恢复过程里的中间产物不该留在共享 /tmp），
# 所以拦的是目标路径，不是那条属性。
case "$target" in
  /tmp/*|/var/tmp/*|/tmp|/var/tmp)
    printf '%s\n' '恢复目标不能放在 /tmp 或 /var/tmp：本脚本用 PrivateTmp=yes 起单元，' >&2
    printf '%s\n' '那两个目录在单元里是私有的，跑完就没了——你会看到 PASS 而目录是空的。' >&2
    printf '%s\n' '换一个别的位置，例如 /home/<你>/sa-restore/ 或一块外接盘。' >&2
    exit 2
    ;;
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
      # **必须是 github_markdown_token，不是 github_token。**
      #
      # 2026-08-04 实测：
      #   github_token          → GraphQL: Could not resolve to a Repository
      #                           with the name 'LinzeColin/Private-Database'
      #   github_markdown_token → {"nameWithOwner":"LinzeColin/Private-Database"}
      #
      # 也就是说**备份写得进去、按文档的恢复路取不出来**——复制单元
      # （social-archive-replication.service:22）加载的一直是
      # github_markdown_token，只有这里加载了另一个看不见私有仓的令牌。
      #
      # 「副本登记成 verified」和「副本取得回来」是两件事。三份副本在库里
      # 都是 verified，而 github 那一份的取回演练直接失败：
      # GITHUB_RELEASE_READ_FAILED。
      #
      # 凭据在 systemd 里的**名字**仍然叫 github_token（下面 export 的是
      # $CREDENTIALS_DIRECTORY/github_token），改的只是它从哪个文件来。
      --property=LoadCredential=github_token:/opt/social-archive/runtime/secrets/github_markdown_token
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
