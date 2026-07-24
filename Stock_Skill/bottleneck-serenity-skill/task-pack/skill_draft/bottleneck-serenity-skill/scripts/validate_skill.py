#!/usr/bin/env python3
"""Validate the local structure of the bottleneck-serenity-skill skill."""
from __future__ import annotations

import re
import sys
from pathlib import Path

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REQUIRED_PATHS = [
    "SKILL.md",
    "references/methodology.md",
    "references/scoring_model.md",
    "references/source_policy.md",
    "scripts/score_opportunity.py",
    "scripts/validate_current_eval_binding.py",
    "scripts/validate_evidence.py",
    "scripts/validate_forward_test.py",
    "scripts/validate_historical_e2e.py",
    "scripts/validate_security_evals.py",
    "scripts/validate_trigger_evals.py",
    "scripts/analyze_portfolio_clusters.py",
    "schemas/opportunity.schema.json",
    "evals/current_eval_binding.json",
    "evals/current_binding/trigger_executor.json",
    "evals/current_binding/security_executor_a.json",
    "evals/current_binding/security_executor_b.json",
    "evals/current_binding/security_executor_c.json",
    "evals/current_binding/judge_a.json",
    "evals/current_binding/judge_b.json",
    "evals/forward_test/baseline_result.json",
    "evals/forward_test/remediation_01.json",
    "evals/forward_test/trial_02_result.json",
    "evals/forward_test/context_manifest.json",
    "evals/forward_test/historical_post_remediation_revalidation.json",
    "evals/forward_test/judge_a.json",
    "evals/forward_test/judge_b.json",
    "evals/forward_test/preregistration.json",
    "evals/forward_test/raw_output.md",
    "evals/forward_test/remediation.json",
    "evals/forward_test/result.json",
    "evals/forward_test/trace.json",
    "evals/prompts.csv",
]


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md must start with YAML front matter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("SKILL.md front matter closing delimiter missing")
    data: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.startswith((" ", "\t")):
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip().strip('"')
    return data


def main() -> None:
    root = (Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()).resolve()
    skill_path = root / "SKILL.md"
    if not skill_path.exists():
        raise SystemExit(f"Missing {skill_path}")
    try:
        metadata = parse_frontmatter(skill_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc

    errors: list[str] = []
    name = metadata.get("name", "")
    description = metadata.get("description", "")
    if not NAME_RE.match(name):
        errors.append("name must be lowercase hyphenated text")
    if root.name != name:
        errors.append(f"directory name '{root.name}' must match skill name '{name}'")
    if not description:
        errors.append("description is required")
    if len(description) > 1024:
        errors.append("description exceeds 1024 characters")
    for relative in REQUIRED_PATHS:
        if not (root / relative).exists():
            errors.append(f"missing required path: {relative}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)
    print(f"OK: {name}; description={len(description)} chars; required files present")


if __name__ == "__main__":
    main()
