#!/usr/bin/env bash
set -Eeuo pipefail
STORE_ROOT="${SIM_OBJECT_STORE_ROOT:-/tmp/cyberboss-object-store}"
PROVIDER="${SIM_OBJECT_STORE_PROVIDER:-r2}"
CONFIGURED_BUCKET="${SIM_OBJECT_STORE_BUCKET:-cyberboss-cold}"
REQUEST_BUCKET="${SIM_OBJECT_STORE_REQUEST_BUCKET:-cyberboss-cold}"
PREFIX="${SIM_OBJECT_STORE_PREFIX:-ovh-singapore-vps-1/}"
COMMAND="${1:-}"
KEY="${2:-}"
SOURCE="${3:-}"
[[ "$PROVIDER" == "r2" ]] || { echo 'OBJECT_STORE=FAIL unsupported_provider'; exit 2; }
[[ "$REQUEST_BUCKET" == "$CONFIGURED_BUCKET" && "$CONFIGURED_BUCKET" == "cyberboss-cold" ]] || {
  echo 'OBJECT_STORE=FAIL out_of_scope_bucket'
  exit 2
}
if [[ "$COMMAND" == "list" && -z "$KEY" ]]; then
  KEY="$PREFIX"
fi
[[ "$KEY" != /* && "$KEY" != *'..'* && "$KEY" == "$PREFIX"* ]] || {
  echo 'OBJECT_STORE=FAIL out_of_scope_key'
  exit 2
}
STORE="$STORE_ROOT/$PROVIDER/$CONFIGURED_BUCKET"
TARGET="$STORE/$KEY"
case "$COMMAND" in
  put)
    [[ -r "$SOURCE" ]] || { echo 'OBJECT_STORE=FAIL source_unreadable'; exit 2; }
    [[ ! -e "$TARGET" ]] || { echo 'OBJECT_STORE=FAIL immutable_key_exists'; exit 1; }
    install -d -m 0750 "$(dirname "$TARGET")"
    cp -- "$SOURCE" "$TARGET"
    chmod 0440 "$TARGET"
    printf 'OBJECT_STORE=PASS action=put key=%s sha256=%s\n' "$KEY" "$(sha256sum "$TARGET" | awk '{print $1}')"
    ;;
  get)
    [[ -r "$TARGET" ]] || { echo 'OBJECT_STORE=FAIL key_missing'; exit 1; }
    [[ -n "$SOURCE" ]] || { echo 'OBJECT_STORE=FAIL destination_required'; exit 2; }
    cp -- "$TARGET" "$SOURCE"
    printf 'OBJECT_STORE=PASS action=get key=%s sha256=%s\n' "$KEY" "$(sha256sum "$SOURCE" | awk '{print $1}')"
    ;;
  list)
    if [[ -d "$STORE" ]]; then
      while IFS= read -r path; do
        printf '%s\n' "${path#"$STORE"/}"
      done < <(find "$STORE" -type f 2>/dev/null) | sort
    fi
    echo 'OBJECT_STORE=PASS action=list'
    ;;
  *) echo 'usage: object-store-simulator.sh put|get|list <scoped-key> [source-or-destination]'; exit 2 ;;
esac
