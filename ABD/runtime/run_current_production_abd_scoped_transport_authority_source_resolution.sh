#!/bin/sh
set -eu

usage() {
  printf '%s\n' 'usage: run_current_production_abd_scoped_transport_authority_source_resolution.sh --facts <regular-file>'
}

if [ "$#" -ne 2 ] || [ "$1" != "--facts" ]; then
  usage >&2
  exit 64
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHONDONTWRITEBYTECODE=1 python3 "$script_dir/current_production_abd_scoped_transport_authority_source_resolution.py" \
  --contract "$script_dir/current_production_abd_scoped_transport_authority_source_resolution_contract.json" \
  --facts "$2"
