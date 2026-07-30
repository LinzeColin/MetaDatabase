#!/usr/bin/env python3
"""Validate local invariants for the stock-commercial-opportunities package.

Run the current official skill-creator quick validator in addition to this
package-specific, standard-library-only check.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
ALLOWED_FRONTMATTER = {"name", "description"}
FORBIDDEN_NAMES = {"__pycache__", ".DS_Store"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".bak"}
EXPECTED_NAME = "stock-commercial-opportunities"

EXPECTED_REFERENCES = {
    "workflow.md",
    "commercial-mechanism.md",
    "evidence-protocol.md",
    "scoring-and-maturity.md",
    "diligence-gates.md",
    "output-contracts.md",
    "safety-and-boundaries.md",
    "stock-research-routing.md",
    "evaluation.md",
}
EXPECTED_SCRIPTS = {
    "score_stock_opportunities.py",
    "validate_deliverable.py",
    "validate_skill.py",
}
EXPECTED_ASSETS = {
    "intake-template.md",
    "stock-opportunity-card-template.md",
    "diligence-card-template.md",
    "research-note-template.md",
    "evidence-ledger.csv",
    "stock-opportunity-score-input.example.json",
    "deliverable.example.json",
}
EXPECTED_EVALS = {"trigger_cases.jsonl", "quality_cases.jsonl", "benchmark-template.csv"}


@dataclass
class Finding:
    severity: str
    path: str
    message: str


def parse_frontmatter(text: str) -> Tuple[Dict[str, str], int]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md must begin with YAML frontmatter delimited by ---")
    end = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            end = index
            break
    if end is None:
        raise ValueError("SKILL.md frontmatter is not closed")
    data: Dict[str, str] = {}
    for number, raw in enumerate(lines[1:end], start=2):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"frontmatter line {number} is not key: value")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise ValueError(f"frontmatter line {number} has an empty key or value")
        if key in data:
            raise ValueError(f"duplicate frontmatter key: {key}")
        if value.startswith(("[", "{", "|", ">")):
            raise ValueError(f"frontmatter key {key} must use a scalar value")
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]
        data[key] = value
    return data, end + 1


def _expect_files(
    findings: List[Finding], directory: Path, expected: set[str], label: str
) -> None:
    for filename in sorted(expected):
        path = directory / filename
        if not path.exists() or not path.is_file():
            findings.append(Finding("error", str(path), f"Expected {label} is missing"))


def validate_skill(skill_dir: Path) -> List[Finding]:
    findings: List[Finding] = []
    if not skill_dir.exists() or not skill_dir.is_dir():
        return [Finding("error", str(skill_dir), "Skill directory does not exist")]

    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        return [Finding("error", str(skill_file), "Required SKILL.md is missing")]
    try:
        text = skill_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [Finding("error", str(skill_file), "SKILL.md must be UTF-8")]

    try:
        frontmatter, body_start = parse_frontmatter(text)
    except ValueError as exc:
        return [Finding("error", str(skill_file), str(exc))]

    unknown = sorted(set(frontmatter) - ALLOWED_FRONTMATTER)
    missing = sorted(ALLOWED_FRONTMATTER - set(frontmatter))
    if unknown:
        findings.append(
            Finding("error", str(skill_file), f"Unsupported frontmatter fields: {', '.join(unknown)}")
        )
    if missing:
        findings.append(
            Finding("error", str(skill_file), f"Missing frontmatter fields: {', '.join(missing)}")
        )

    name = frontmatter.get("name", "")
    description = frontmatter.get("description", "")
    if not NAME_RE.fullmatch(name):
        findings.append(Finding("error", str(skill_file), "name must use lowercase letters, digits, and single hyphens"))
    if len(name) > 64:
        findings.append(Finding("error", str(skill_file), "name must be 64 characters or fewer"))
    if name != EXPECTED_NAME:
        findings.append(Finding("error", str(skill_file), f"name must be {EXPECTED_NAME!r}"))
    if skill_dir.name != name:
        findings.append(Finding("error", str(skill_dir), f"Directory name must match frontmatter name {name!r}"))
    if not description.strip():
        findings.append(Finding("error", str(skill_file), "description must not be empty"))
    if len(description) > 1024:
        findings.append(Finding("warning", str(skill_file), "description exceeds 1024 characters"))
    lowered = description.lower()
    if "use" not in lowered and "用于" not in description:
        findings.append(Finding("warning", str(skill_file), "description should state when to use the skill"))
    if "do not use" not in lowered and "不要" not in description:
        findings.append(Finding("warning", str(skill_file), "description should state non-trigger boundaries"))

    body = "\n".join(text.splitlines()[body_start:]).strip()
    if not body:
        findings.append(Finding("error", str(skill_file), "SKILL.md body is empty"))
    if len(text.splitlines()) > 500:
        findings.append(Finding("warning", str(skill_file), "SKILL.md exceeds 500 lines; use progressive disclosure"))

    for target in LINK_RE.findall(body):
        clean = target.split("#", 1)[0].strip()
        if not clean or clean.startswith(("http://", "https://", "mailto:", "#")):
            continue
        if clean.startswith("/") or ".." in Path(clean).parts:
            findings.append(Finding("error", str(skill_file), f"Link must stay inside the skill: {target}"))
            continue
        resolved = (skill_dir / clean).resolve()
        try:
            resolved.relative_to(skill_dir.resolve())
        except ValueError:
            findings.append(Finding("error", str(skill_file), f"Link escapes skill directory: {target}"))
            continue
        if not resolved.exists():
            findings.append(Finding("error", str(skill_file), f"Linked resource does not exist: {target}"))
        if len(Path(clean).parts) > 2:
            findings.append(Finding("warning", str(skill_file), f"Prefer one-level direct references: {target}"))

    yaml_file = skill_dir / "agents" / "openai.yaml"
    if not yaml_file.exists():
        findings.append(Finding("error", str(yaml_file), "agents/openai.yaml is required by this package"))
    else:
        yaml_text = yaml_file.read_text(encoding="utf-8")
        for token in (
            "interface:",
            "display_name:",
            "short_description:",
            "default_prompt:",
            "policy:",
            "allow_implicit_invocation:",
            f"${EXPECTED_NAME}",
        ):
            if token not in yaml_text:
                findings.append(Finding("error", str(yaml_file), f"Expected token missing: {token}"))
        if re.search(r"(?im)^\s*(dependencies|icons?|connectors?|tools?):", yaml_text):
            findings.append(Finding("warning", str(yaml_file), "Unexpected optional tool/icon metadata; verify intentionally"))

    _expect_files(findings, skill_dir / "references", EXPECTED_REFERENCES, "reference")
    _expect_files(findings, skill_dir / "scripts", EXPECTED_SCRIPTS, "script")
    _expect_files(findings, skill_dir / "assets", EXPECTED_ASSETS, "asset")
    _expect_files(findings, skill_dir / "evals", EXPECTED_EVALS, "eval")
    if not (skill_dir / "tests" / "test_scripts.py").is_file():
        findings.append(Finding("error", str(skill_dir / "tests" / "test_scripts.py"), "Expected test suite is missing"))

    for path in skill_dir.rglob("*"):
        if path.name in FORBIDDEN_NAMES or path.suffix in FORBIDDEN_SUFFIXES:
            findings.append(Finding("error", str(path), "Cache/temporary artifact must not be packaged"))
        if path.is_symlink():
            findings.append(Finding("warning", str(path), "Symlinks reduce package portability"))

    return findings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_dir", type=Path, help="Path to the skill directory")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    findings = validate_skill(args.skill_dir.resolve())
    errors = [finding for finding in findings if finding.severity == "error"]
    warnings = [finding for finding in findings if finding.severity == "warning"]
    for finding in findings:
        print(f"{finding.severity.upper()} {finding.path}: {finding.message}")
    failed = bool(errors) or (args.strict and bool(warnings))
    print(f"{'FAIL' if failed else 'PASS'}: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
