#!/bin/sh
set -eu

usage() {
  printf '%s\n' 'usage: run_current_production_rebuild_metadata_source_repair_provenance_reconciliation_diagnostic.sh --repo-root <directory> --observed-on <YYYY-MM-DD>'
}

if [ "$#" -ne 4 ] || [ "$1" != "--repo-root" ] || [ "$3" != "--observed-on" ]; then
  usage >&2
  exit 64
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHONDONTWRITEBYTECODE=1 python3 "$script_dir/current_production_rebuild_metadata_source_repair_provenance_reconciliation_diagnostic.py" \
  --contract "$script_dir/current_production_rebuild_metadata_source_repair_provenance_reconciliation_diagnostic_contract.json" \
  --repo-root "$2" \
  --repair-contract "$script_dir/current_production_blue_release_repair_contract.json" \
  --repair-source "$script_dir/current_production_blue_release_repair.py" \
  --observed-on "$4"
