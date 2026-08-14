#!/bin/sh
set -eu

usage() {
  printf '%s\n' 'usage: run_current_production_ssh_transport_failure_classification_diagnostic.sh --ssh-config <regular-file>'
}

if [ "$#" -ne 2 ] || [ "$1" != "--ssh-config" ]; then
  usage >&2
  exit 64
fi

if [ ! -f "$2" ] || [ -L "$2" ]; then
  printf '%s\n' 'ssh config must be a regular file' >&2
  exit 65
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHONDONTWRITEBYTECODE=1 python3 "$script_dir/current_production_ssh_transport_failure_classification_diagnostic.py" \
  --contract "$script_dir/current_production_ssh_transport_failure_classification_diagnostic_contract.json" \
  --ssh-config "$2"
