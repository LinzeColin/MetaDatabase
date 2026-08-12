#!/bin/sh
set -eu

if [ "$#" -ne 0 ]; then
  printf '%s\n' 'usage: run_current_production_local_outbound_policy_classification_diagnostic.sh' >&2
  exit 64
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHONDONTWRITEBYTECODE=1 python3 "$script_dir/current_production_local_outbound_policy_classification_diagnostic.py" \
  --contract "$script_dir/current_production_local_outbound_policy_classification_diagnostic_contract.json"
