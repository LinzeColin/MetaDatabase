#!/bin/sh
set -eu

usage() {
  printf '%s\n' 'usage: run_current_production_ssh_local_route_policy_diagnostic.sh --ssh-config <regular-file>'
}

if [ "$#" -ne 2 ] || [ "$1" != "--ssh-config" ]; then
  usage >&2
  exit 64
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHONDONTWRITEBYTECODE=1 python3 "$script_dir/current_production_ssh_local_route_policy_diagnostic.py" \
  --contract "$script_dir/current_production_ssh_local_route_policy_diagnostic_contract.json" \
  --ssh-config "$2"
