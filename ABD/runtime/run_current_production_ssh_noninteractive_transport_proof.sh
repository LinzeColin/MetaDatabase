#!/bin/sh
set -eu

usage() {
  printf '%s\n' 'usage: run_current_production_ssh_noninteractive_transport_proof.sh --ssh-config <regular-file> --observed-on <YYYY-MM-DD>'
}

if [ "$#" -ne 4 ] || [ "$1" != "--ssh-config" ] || [ "$3" != "--observed-on" ]; then
  usage >&2
  exit 64
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHONDONTWRITEBYTECODE=1 python3 "$script_dir/current_production_ssh_noninteractive_transport_proof.py" \
  --contract "$script_dir/current_production_ssh_noninteractive_transport_proof_contract.json" \
  --local-route-policy-contract "$script_dir/current_production_ssh_local_route_policy_diagnostic_contract.json" \
  --ssh-config "$2" \
  --observed-on "$4"
