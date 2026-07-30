#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.upstream_inputs import materialize_input, write_self_hashed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--agent-input", type=Path, required=True)
    parser.add_argument("--meta-input", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    baseline = json.loads((root / "machine/facts/upstream_baseline.json").read_text())
    try:
        agent = materialize_input(
            args.agent_input,
            baseline["agent_database"]["commit"],
            output_root / "AgentDatabase",
            source_name="AgentDatabase",
        )
        meta = materialize_input(
            args.meta_input,
            baseline["meta_database"]["commit"],
            output_root / "MetaDatabase",
            source_name="MetaDatabase",
        )
        state = "PASS"
        reason = "FIXED_UPSTREAM_INPUTS_MATERIALIZED"
    except Exception as exc:
        # Remove any partially materialized checkout before publishing the blocker.
        for name in ("AgentDatabase", "MetaDatabase"):
            path = output_root / name
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
        agent = None
        meta = None
        state = "BLOCKED"
        reason = f"UPSTREAM_INPUT_MATERIALIZATION_FAILED:{type(exc).__name__}:{exc}"
    payload = {
        "schema_version": "1.0.0",
        "state": state,
        "reason_code": reason,
        "agent": agent,
        "meta": meta,
        "upstream_write_allowed": False,
        "runtime_agent_dependency": 0,
        "runtime_llm_token_budget": 0,
    }
    receipt = write_self_hashed(args.receipt, payload)
    print(json.dumps({"state": state, "reason_code": reason, "receipt_sha256": receipt["receipt_sha256"]}, sort_keys=True))
    return 0 if state == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
