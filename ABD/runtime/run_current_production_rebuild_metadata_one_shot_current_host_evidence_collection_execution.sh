#!/bin/sh
set -eu

usage() {
  printf '%s\n' 'usage: run_current_production_rebuild_metadata_one_shot_current_host_evidence_collection_execution.sh --repo-root <directory> --ssh-config <regular-file> --observed-on <YYYY-MM-DD>'
}

if [ "$#" -ne 6 ] || [ "$1" != "--repo-root" ] || [ "$3" != "--ssh-config" ] || [ "$5" != "--observed-on" ]; then
  usage >&2
  exit 64
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHONDONTWRITEBYTECODE=1 python3 "$script_dir/current_production_rebuild_metadata_one_shot_current_host_evidence_collection_execution.py" \
  --contract "$script_dir/current_production_rebuild_metadata_one_shot_current_host_evidence_collection_execution_contract.json" \
  --repo-root "$2" \
  --collection-run-contract "$script_dir/current_production_rebuild_metadata_current_host_evidence_collection_run_contract_diagnostic_contract.json" \
  --acquisition-contract "$script_dir/current_production_rebuild_metadata_current_host_evidence_acquisition_contract_diagnostic_contract.json" \
  --admission-contract "$script_dir/current_production_rebuild_metadata_repair_execution_admission_contract_diagnostic_contract.json" \
  --core-preflight-contract "$script_dir/current_production_core_execution_preflight_contract.json" \
  --local-route-policy-contract "$script_dir/current_production_ssh_local_route_policy_diagnostic_contract.json" \
  --ssh-config "$4" \
  --observed-on "$6"
