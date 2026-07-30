#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RECEIPTS_DIR="${1:-}"
ROUND_ONE="${2:-}"
ROUND_TWO="${3:-}"
if [[ -z "$RECEIPTS_DIR" || -z "$ROUND_ONE" || -z "$ROUND_TWO" ]]; then
  echo "usage: $0 /path/to/24-review-receipts /path/to/no-change-round-1.json /path/to/no-change-round-2.json" >&2
  exit 64
fi
cd "$ROOT"

rm -rf evidence/formal_review/receipts
mkdir -p evidence/formal_review/receipts evidence/owner_gate/no_change_rounds
find "$RECEIPTS_DIR" -maxdepth 1 -type f -name '*.json' -print0 | sort -z | xargs -0 -I{} cp -- "{}" evidence/formal_review/receipts/
cp -- "$ROUND_ONE" evidence/owner_gate/no_change_rounds/round-1.json
cp -- "$ROUND_TWO" evidence/owner_gate/no_change_rounds/round-2.json

python3 scripts/build_review_chain.py \
  --subject-lock SUBJECT_LOCK.json \
  --review-input evidence/formal_review/review_input.json \
  --receipts-dir evidence/formal_review/receipts \
  --output evidence/formal_review/review_chain.json
python3 scripts/frozen_replay.py \
  --root "$ROOT" \
  --review-chain evidence/formal_review/review_chain.json \
  --output evidence/owner_gate/frozen_replay_1.json
python3 scripts/frozen_replay.py \
  --root "$ROOT" \
  --review-chain evidence/formal_review/review_chain.json \
  --output evidence/owner_gate/frozen_replay_2.json
python3 scripts/verify_frozen_replays.py \
  --first evidence/owner_gate/frozen_replay_1.json \
  --second evidence/owner_gate/frozen_replay_2.json \
  --output evidence/owner_gate/frozen_replay_comparison.json
python3 scripts/build_stop_and_freeze.py \
  --subject-lock SUBJECT_LOCK.json \
  --review-chain evidence/formal_review/review_chain.json \
  --replay-comparison evidence/owner_gate/frozen_replay_comparison.json \
  --round-receipt evidence/owner_gate/no_change_rounds/round-1.json \
  --round-receipt evidence/owner_gate/no_change_rounds/round-2.json \
  --output evidence/owner_gate/stop_and_freeze.json
python3 scripts/transition_canonical_state.py \
  --root "$ROOT" \
  --target OWNER_GATE \
  --output evidence/owner_gate/state_transition_owner_gate.json
python3 scripts/verify_formal_gate.py \
  --root "$ROOT" \
  --output evidence/owner_gate/formal_gate.json
python3 scripts/build_skill_pass_c.py \
  --root "$ROOT" \
  --output evidence/skill_router/pass_c.json
python3 scripts/verify_package.py --root "$ROOT" --manifest "$ROOT/MANIFEST.json"

python3 - "$ROOT" <<'PY'
import json, sys
from pathlib import Path
root=Path(sys.argv[1])
subject=json.loads((root/'SUBJECT_LOCK.json').read_text())
state=json.loads((root/'CANONICAL_STATE.json').read_text())
payload={
  'state':'READY_FOR_USER_APPROVAL',
  'version':subject.get('version'),
  'subject_sha256':subject.get('subject_sha256'),
  'current_phase':state.get('current_phase'),
  'owner_gate':state.get('owner_gate'),
  'final_zip_generated':False,
}
print(json.dumps(payload,ensure_ascii=False,sort_keys=True))
PY
