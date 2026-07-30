#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from signal_lattice.config import Settings
from signal_lattice.db import RuntimeDB
from signal_lattice.skill_adapters import normalize_skill_artifact
from signal_lattice.source_sync import conditional_get
from signal_lattice.recommendation import validate_market_snapshot
from signal_lattice.util import atomic_write


def load_json(path: Path) -> dict:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 5_000_000:
        raise ValueError(f"INPUT_UNSAFE:{path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"INPUT_OBJECT_REQUIRED:{path.name}")
    return value


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    settings = Settings.from_env(root)
    db = RuntimeDB(settings.state_dir / "runtime.db", root / "db/schema.sql")
    artifact_dir = settings.artifact_dir
    artifact_dir.mkdir(parents=True, exist_ok=True)
    registry = load_json(root / "config/source_registry.json")
    etag_file = settings.state_dir / "source-etags.json"
    etags = load_json(etag_file) if etag_file.is_file() else {}
    observed = []
    errors = []
    for source in registry.get("sources", []):
        skill_id = str(source.get("skill_id", ""))
        url = str(source.get("url", ""))
        if not skill_id or not url:
            errors.append("INVALID_SOURCE_REGISTRY_ROW")
            continue
        try:
            result = conditional_get(url, etags.get(skill_id), max_bytes=5_000_000, timeout=20)
            if result.etag:
                etags[skill_id] = result.etag
            if result.body is not None:
                digest = hashlib.sha256(result.body).hexdigest()
                snapshot_path = settings.state_dir / "skill-sources" / skill_id / f"{digest}.md"
                snapshot_path.parent.mkdir(parents=True, exist_ok=True)
                if not snapshot_path.exists():
                    atomic_write(snapshot_path, result.body)
                db.upsert_skill_snapshot({
                    "skill_id": skill_id,
                    "source_commit": "DYNAMIC_MAIN_OBSERVATION",
                    "content_sha256": digest,
                    "lifecycle_state": "OBSERVED",
                    "compatibility_state": "REFERENCE_ONLY_UNTIL_ADAPTER_OUTPUT",
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                })
                observed.append({"skill_id": skill_id, "state": result.state, "content_sha256": digest})
            else:
                observed.append({"skill_id": skill_id, "state": result.state})
        except Exception as exc:  # fail-soft per source; overall receipt records degradation
            errors.append(f"{skill_id}:{type(exc).__name__}:{str(exc)[:200]}")
    atomic_write(etag_file, json.dumps(etags, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))

    input_dir = settings.state_dir / "skill-inputs"
    ingested_signals = []
    rejected_signals = []
    input_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(input_dir.glob("*.json")):
        try:
            payload = load_json(path)
            signal = normalize_skill_artifact(payload, skill_id=payload.get("skill_id"))
            db.upsert_skill_signal(signal)
            ingested_signals.append({"path": path.name, "skill_id": signal["skill_id"], "symbol": signal["symbol"], "market": signal["market"], "source_digest": signal["source_digest"]})
        except Exception as exc:
            rejected_signals.append({"path": path.name, "reason": type(exc).__name__ + ":" + str(exc)[:200]})

    market_dir = settings.state_dir / "market-data"
    ingested_market = []
    rejected_market = []
    market_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(market_dir.glob("*.json")):
        try:
            snapshot = validate_market_snapshot(load_json(path))
            db.upsert_market_snapshot(snapshot)
            ingested_market.append({"path": path.name, "symbol": snapshot["symbol"], "market": snapshot["market"], "source_digest": snapshot["source_digest"]})
        except Exception as exc:
            rejected_market.append({"path": path.name, "reason": type(exc).__name__ + ":" + str(exc)[:200]})

    state = "PASS" if not errors and not rejected_signals and not rejected_market else "DEGRADED"
    receipt = {
        "schema_version": "2.0.0",
        "state": state,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "source_observations": observed,
        "source_errors": errors,
        "ingested_skill_signals": ingested_signals,
        "rejected_skill_signals": rejected_signals,
        "ingested_market_snapshots": ingested_market,
        "rejected_market_snapshots": rejected_market,
        "upstream_write_allowed": False,
        "runtime_agent_dependency": 0,
        "runtime_llm_tokens": 0,
    }
    atomic_write(artifact_dir / "source_sync.json", json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"))
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0 if state == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
