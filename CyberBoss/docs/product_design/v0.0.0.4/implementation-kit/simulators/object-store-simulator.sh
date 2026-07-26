#!/usr/bin/env bash
set -Eeuo pipefail
STORE="${SIM_OBJECT_STORE_ROOT:-/tmp/cyberboss-object-store}"
COMMAND="${1:-}"
KEY="${2:-}"
SOURCE="${3:-}"
[[ "$KEY" != /* && "$KEY" != *'..'* ]] || { echo 'OBJECT_STORE=FAIL invalid_key'; exit 2; }
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
  *) echo 'usage: object-store-simulator.sh put|get|list <key> [source-or-destination]'; exit 2 ;;
esac
