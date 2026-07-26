#!/usr/bin/env bash
set -euo pipefail

ALIAS=""
APPLY=0
CONFIG="/etc/cyberboss/workspaces.json"
BUDGET="/etc/cyberboss/workspace-budget.json"

while (($#)); do
  case "$1" in
    --alias) ALIAS="${2:-}"; shift 2 ;;
    --config) CONFIG="${2:-}"; shift 2 ;;
    --budget) BUDGET="${2:-}"; shift 2 ;;
    --apply-cache-cleanup) APPLY=1; shift ;;
    --check) shift ;;
    *) printf 'WORKSPACE_MAINTENANCE=STOP unknown_arg:%s\n' "$1"; exit 2 ;;
  esac
done

[[ "$ALIAS" == "cyberboss" ]] || {
  printf 'WORKSPACE_MAINTENANCE=STOP alias_must_be_cyberboss\n'
  exit 2
}
[[ -r "$CONFIG" && -r "$BUDGET" ]] || {
  printf 'WORKSPACE_MAINTENANCE=STOP policy_unreadable\n'
  exit 2
}

VALUES=()
while IFS= read -r value; do
  VALUES+=("$value")
done < <(
  python3 - "$CONFIG" "$BUDGET" "$ALIAS" <<'PY'
import json
import sys
from pathlib import Path

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
budget = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
alias = sys.argv[3]
workspace = (config.get("workspaces") or {}).get(alias) or {}
root = workspace.get("root")
if (
    config.get("default_alias") != "cyberboss"
    or root != "/srv/cyberboss-workspaces/cyberboss"
    or budget.get("workspace_root") != root
    or budget.get("cache_root") != "/var/lib/cyberboss/cache"
    or "--prune=now" in json.dumps(budget.get("cleanup_commands") or [])
):
    raise SystemExit(2)
print(root)
print(budget["cache_root"])
PY
)

[[ "${#VALUES[@]}" -eq 2 ]] || {
  printf 'WORKSPACE_MAINTENANCE=STOP policy_invalid\n'
  exit 2
}
WORKSPACE="${VALUES[0]}"
CACHE="${VALUES[1]}"
[[ -d "$WORKSPACE/.git" && ! -L "$WORKSPACE" ]] || {
  printf 'WORKSPACE_MAINTENANCE=STOP workspace_invalid\n'
  exit 2
}
[[ "$(realpath "$WORKSPACE")" == "/srv/cyberboss-workspaces/cyberboss" ]] || {
  printf 'WORKSPACE_MAINTENANCE=STOP workspace_realpath\n'
  exit 2
}

if ((APPLY == 0)); then
  printf 'WORKSPACE_MAINTENANCE=PASS mode=dry_run alias=cyberboss commands=3 no_prune_now=true\n'
  exit 0
fi

git -C "$WORKSPACE" worktree prune
git -C "$WORKSPACE" gc
if [[ -d "$CACHE" && ! -L "$CACHE" ]]; then
  find "$CACHE" -mindepth 1 -maxdepth 1 -type f -mtime +7 -delete
  find "$CACHE" -mindepth 1 -maxdepth 1 -type d -empty -delete
fi
python3 "$(dirname "$0")/workspace_budget.py" \
  --policy "$BUDGET" \
  --workspace-root "$WORKSPACE" \
  --cache-root "$CACHE"
printf 'WORKSPACE_MAINTENANCE=PASS mode=apply alias=cyberboss no_prune_now=true\n'
