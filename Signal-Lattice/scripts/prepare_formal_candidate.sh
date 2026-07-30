#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENT_INPUT="${1:-}"
META_INPUT="${2:-}"
if [[ -z "$AGENT_INPUT" || -z "$META_INPUT" ]]; then
  echo "usage: $0 /path/to/AgentDatabase-or-bundle /path/to/MetaDatabase-or-bundle" >&2
  exit 64
fi
ARTIFACT_DIR="${SIGNAL_LATTICE_PREPARE_ARTIFACT_DIR:-/tmp/signal-lattice-formal-prepare}"
mkdir -p "$ARTIFACT_DIR"
MATERIALIZED_ROOT="$(mktemp -d -t signal-lattice-upstream.XXXXXX)"
cleanup() { rm -rf "$MATERIALIZED_ROOT"; }
trap cleanup EXIT INT TERM
cd "$ROOT"

rm -rf evidence/formal_review/receipts
rm -f evidence/formal_review/review_chain.json \
      evidence/formal_review/review_input.json \
      evidence/owner_gate/frozen_replay_1.json \
      evidence/owner_gate/frozen_replay_2.json \
      evidence/owner_gate/frozen_replay_comparison.json \
      evidence/owner_gate/stop_and_freeze.json \
      evidence/owner_gate/state_transition_owner_gate.json \
      evidence/skill_router/pass_c.json

python3 scripts/prebuild.py --root "$ROOT" --output "$ARTIFACT_DIR/prebuild-before-freeze.json"
python3 scripts/materialize_upstream_inputs.py \
  --root "$ROOT" \
  --agent-input "$AGENT_INPUT" \
  --meta-input "$META_INPUT" \
  --output-root "$MATERIALIZED_ROOT" \
  --receipt "$ARTIFACT_DIR/upstream-inputs.json"
readarray -t RESOLVED_PATHS < <(python3 - "$ARTIFACT_DIR/upstream-inputs.json" <<'PY2'
import json, sys
data=json.load(open(sys.argv[1]))
if data.get("state") != "PASS":
    raise SystemExit("UPSTREAM_INPUTS_NOT_MATERIALIZED")
print(data["agent"]["materialized_path"])
print(data["meta"]["materialized_path"])
PY2
)
AGENT_CHECKOUT="${RESOLVED_PATHS[0]}"
META_CHECKOUT="${RESOLVED_PATHS[1]}"
python3 scripts/build_upstream_seal.py \
  --root "$ROOT" \
  --agent "$AGENT_CHECKOUT" \
  --meta "$META_CHECKOUT" \
  --output "$ROOT/evidence/upstream"
python3 scripts/build_quant_seal.py "$ROOT/evidence/quant/quant_seal.json"
python3 scripts/freeze_candidate_contracts.py \
  --root "$ROOT" \
  --output "$ROOT/evidence/owner_gate/candidate_freeze.json"
python3 scripts/build_subject_lock.py \
  --root "$ROOT" \
  --state FROZEN \
  --output "$ROOT/SUBJECT_LOCK.json"
python3 scripts/build_manifest.py --root "$ROOT" --output "$ROOT/MANIFEST.json"
python3 scripts/verify_package.py --root "$ROOT" --manifest "$ROOT/MANIFEST.json"
python3 scripts/build_review_input.py \
  --root "$ROOT" \
  --output "$ROOT/evidence/formal_review/review_input.json"
python3 scripts/transition_canonical_state.py \
  --root "$ROOT" \
  --target BUILDER_READINESS \
  --output "$ROOT/evidence/owner_gate/state_transition_builder_readiness.json"
python3 scripts/verify_package.py --root "$ROOT" --manifest "$ROOT/MANIFEST.json"

python3 - "$ROOT" "$ARTIFACT_DIR/prepare_formal_candidate.json" <<'PY'
import json, sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2])
subject=json.loads((root/'SUBJECT_LOCK.json').read_text())
state=json.loads((root/'CANONICAL_STATE.json').read_text())
payload={
  'schema_version':'1.0.0',
  'state':'READY_FOR_INDEPENDENT_REVIEW',
  'version':subject.get('version'),
  'subject_sha256':subject.get('subject_sha256'),
  'current_phase':state.get('current_phase'),
  'review_input':'evidence/formal_review/review_input.json',
  'runtime_agent_dependency':0,
  'runtime_llm_token_budget':0,
}
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
print(json.dumps(payload,ensure_ascii=False,sort_keys=True))
PY
