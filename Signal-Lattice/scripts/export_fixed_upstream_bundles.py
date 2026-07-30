#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from signal_lattice.upstream_inputs import export_bundle, write_self_hashed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--agent", type=Path, required=True)
    parser.add_argument("--meta", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    baseline = json.loads((root / "machine/facts/upstream_baseline.json").read_text())
    agent_commit = baseline["agent_database"]["commit"]
    meta_commit = baseline["meta_database"]["commit"]
    agent = export_bundle(
        args.agent.resolve(),
        agent_commit,
        output / f"AgentDatabase-{agent_commit}.bundle",
        source_name="AgentDatabase",
    )
    meta = export_bundle(
        args.meta.resolve(),
        meta_commit,
        output / f"MetaDatabase-{meta_commit}.bundle",
        source_name="MetaDatabase",
    )
    payload = {
        "schema_version": "1.0.0",
        "state": "PASS",
        "agent": agent,
        "meta": meta,
        "upstream_write_allowed": False,
        "network_required_for_consumption": False,
        "developer_research_required": False,
    }
    receipt = write_self_hashed(args.receipt, payload)
    print(json.dumps({"state": "PASS", "receipt_sha256": receipt["receipt_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
