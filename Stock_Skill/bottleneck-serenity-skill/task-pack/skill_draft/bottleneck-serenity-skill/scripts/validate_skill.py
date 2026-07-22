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
    "scripts/validate_evidence.py",
    "scripts/analyze_portfolio_clusters.py",
    "schemas/opportunity.schema.json",
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
