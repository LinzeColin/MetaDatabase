#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate the JS/Python scoring parity fixture (S10PAT01).

Emits a deterministic grid of relationship_score_metrics inputs with the
Python-computed outputs. The Worker-side port replays the grid and must
match every field exactly; any drift blocks release (S10PA stop condition:
评分数学 JS 移植未与 Python 对拍).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from apps.api.app.scoring import relationship_score_metrics  # noqa: E402

OUTPUT = REPO_ROOT / "apps" / "cloudflare-public" / "tests" / "scoring_parity_fixture.json"

# Rounding-adversarial confidences on top of a dense uniform grid: values
# whose double expansion sits at or near the 2-decimal tie boundary.
TRICKY_CONFIDENCES = [
    0.885, 0.125, 0.845, 0.005, 0.015, 0.025, 0.335, 0.665,
    2 / 3, 1 / 3, 0.844999999999, 0.8450000000001, 0.9999, 0.0001,
]


def build_cases() -> list[dict]:
    confidences = [round(i / 200, 6) for i in range(201)] + TRICKY_CONFIDENCES
    combos = [
        # (sources, met, review, publication, fact_version, evidence, minimum)
        (0, False, "unreviewed", "candidate", False, False, 2),
        (1, False, "unreviewed", "ready_for_review", False, True, 2),
        (2, True, "human_verified", "published", True, True, 2),
        (3, True, "human_verified", "published", True, True, 2),
        (1, True, "human_verified", "published", True, True, 1),
        (2, True, "machine_verified", "published", True, True, 3),
        (0, False, "", "unpublished", False, False, 2),
        (5, True, "human_verified", "published", False, True, 2),
    ]
    cases = []
    for confidence in confidences:
        for sources, met, review, publication, fact, evidence, minimum in combos:
            inputs = {
                "confidence": confidence,
                "independent_source_count": sources,
                "source_threshold_met": met,
                "review_status": review,
                "publication_status": publication,
                "fact_version_present": fact,
                "evidence_present": evidence,
                "minimum_independent_sources": minimum,
            }
            cases.append(
                {
                    "inputs": inputs,
                    "expected": relationship_score_metrics(**inputs),
                }
            )
    return cases


def main() -> int:
    cases = build_cases()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "schema_version": "scoring-parity-fixture-v1",
                "metric": "relationship_score_metrics",
                "case_count": len(cases),
                "cases": cases,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"PARITY_FIXTURE cases={len(cases)} -> {OUTPUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
