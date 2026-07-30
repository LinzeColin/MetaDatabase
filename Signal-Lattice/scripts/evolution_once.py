#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from signal_lattice.calibration import load_weights, update_weights
from signal_lattice.util import atomic_write


def main() -> int:
    state = Path(os.environ.get("SIGNAL_LATTICE_STATE_DIR", "/var/lib/signal-lattice"))
    artifact_dir = Path(os.environ.get("SIGNAL_LATTICE_ARTIFACT_DIR", str(state / "artifacts")))
    outcomes_path = state / "calibration" / "outcomes.json"
    weights_path = state / "calibration" / "weights.json"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if outcomes_path.is_file():
        raw = json.loads(outcomes_path.read_text(encoding="utf-8"))
        outcomes = raw.get("outcomes")
        if not isinstance(outcomes, list):
            raise ValueError("OUTCOMES_ARRAY_REQUIRED")
        result = update_weights(load_weights(weights_path), outcomes)
        atomic_write(weights_path, json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
        verdict = "KEEP_CANDIDATE" if result.get("updates") else "KEEP_BASELINE"
        candidate_count = len(result.get("updates", []))
        reason = "CALIBRATION_OUTCOMES_APPLIED" if candidate_count else "NO_CALIBRATION_DELTA"
        calibration_receipt = result.get("receipt_sha256")
    else:
        verdict = "KEEP_BASELINE"
        candidate_count = 0
        reason = "NO_ELIGIBLE_CHALLENGER_OR_OUTCOMES"
        calibration_receipt = None
    receipt = {
        "schema_version": "1.1.0",
        "state": "PASS",
        "verdict": verdict,
        "reason": reason,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_count": candidate_count,
        "calibration_receipt_sha256": calibration_receipt,
        "runtime_agent_dependency": 0,
        "runtime_llm_tokens": 0,
        "upstream_writeback": False,
        "automatic_trading": False,
    }
    atomic_write(artifact_dir / "evolution.json", json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
