#!/usr/bin/env python3
"""Initialize a timestamped bottleneck-serenity-skill research case."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import re
import uuid
from datetime import date
from pathlib import Path
from typing import Any

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ARTIFACT_SCHEMA_VERSION = "1.0"
SKILL_VERSION = "0.0.0.1"


def _canonical_date(value: str, label: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"{label} must be a canonical YYYY-MM-DD date") from exc
    if parsed.isoformat() != value:
        raise SystemExit(f"{label} must be a canonical YYYY-MM-DD date")
    return value


def _opportunity_template() -> dict[str, Any]:
    path = Path(__file__).with_name("score_opportunity.py")
    spec = importlib.util.spec_from_file_location("bss_score_opportunity", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load opportunity template from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return copy.deepcopy(module.TEMPLATE)


def _research_config_template() -> dict[str, Any]:
    path = Path(__file__).parents[1] / "templates" / "research_config.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot load research config template from {path}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"Research config template must be a JSON object: {path}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", help="lowercase hyphenated case slug")
    parser.add_argument("--output", default="research", help="parent output directory")
    parser.add_argument("--as-of", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--source-cutoff", help="YYYY-MM-DD; defaults to --as-of")
    parser.add_argument("--request-id", help="request UUID; generated when omitted")
    parser.add_argument("--query", default="", help="research question")
    parser.add_argument("--previous-version", help="prior immutable version identifier")
    args = parser.parse_args()
    if not SLUG_RE.match(args.slug):
        raise SystemExit("slug must contain lowercase letters, digits, and internal hyphens")

    as_of = _canonical_date(args.as_of, "--as-of")
    source_cutoff = _canonical_date(args.source_cutoff or as_of, "--source-cutoff")
    if source_cutoff > as_of:
        raise SystemExit("--source-cutoff cannot be later than --as-of")
    if args.previous_version is not None and not args.previous_version.strip():
        raise SystemExit("--previous-version must be a non-empty identifier")
    request_id = args.request_id or str(uuid.uuid4())
    try:
        request_id = str(uuid.UUID(request_id))
    except ValueError as exc:
        raise SystemExit("--request-id must be a UUID") from exc
    metadata = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "skill_version": SKILL_VERSION,
        "as_of": as_of,
        "source_cutoff": source_cutoff,
        "previous_version": args.previous_version,
    }

    thesis_id = f"{args.slug}-{as_of.replace('-', '')}"
    root = Path(args.output) / thesis_id
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty directory: {root}")
    (root / "versions").mkdir(parents=True, exist_ok=True)

    config = _research_config_template()
    config.update(metadata)
    config.update(
        {
            "request_id": request_id,
            "thesis_id": thesis_id,
            "query": args.query,
        }
    )
    (root / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (root / "system_map.md").write_text(
        "# System map\n\n## Funded demand\n\n## Roles before tickers\n\n## Dependency graph\n\n## Constraint hypotheses\n",
        encoding="utf-8",
    )
    (root / "evidence.json").write_text(
        json.dumps({**metadata, "claims": []}, indent=2) + "\n",
        encoding="utf-8",
    )
    opportunity = _opportunity_template()
    opportunity.update(metadata)
    opportunity["thesis_id"] = thesis_id
    opportunity["notes"] = ["Draft scaffold only; replace all illustrative fields with sourced research."]
    (root / "opportunity.json").write_text(
        json.dumps(opportunity, indent=2) + "\n", encoding="utf-8"
    )
    decision = {
        **metadata,
        "request_id": request_id,
        "thesis_id": thesis_id,
        "mode": "scan",
        "status": "draft",
        "decision": None,
        "evidence_file": "evidence.json",
    }
    (root / "decision.json").write_text(
        json.dumps(decision, indent=2) + "\n", encoding="utf-8"
    )
    (root / "memo.md").write_text("# Decision memo\n", encoding="utf-8")
    (root / "monitoring.csv").write_text(
        "schema_version,skill_version,as_of,source_cutoff,previous_version,"
        "indicator,source,cadence,expected_range,alert_threshold,thesis_implication,last_checked\n",
        encoding="utf-8",
    )
    print(root)


if __name__ == "__main__":
    main()
