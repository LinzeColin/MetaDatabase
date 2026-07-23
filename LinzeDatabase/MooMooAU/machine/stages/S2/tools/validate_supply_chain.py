#!/usr/bin/env python3
"""Read-only structural validation for Stage 2 immutable supply-chain inputs."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[4]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
TOOLS = PROJECT_ROOT / "machine/tools"
WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/moomooau-stage2-security.yml"
_PINNED_ACTION = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?@[0-9a-f]{40}$")
_REQUIREMENT = re.compile(
    r"^([A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?==([A-Za-z0-9_.+-]+)(?:\s*;.*)?\s*\\$"
)
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")

if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from validate_workflow_matrix import (  # noqa: E402
    validate_governance_dependency_workflow,
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def requirement_versions(lock_text: str) -> dict[str, str]:
    """Return normalized exact pins, rejecting duplicate or unhashed requirement blocks."""

    versions: dict[str, str] = {}
    lines = lock_text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line or line.startswith("#") or line.startswith(" "):
            index += 1
            continue
        match = _REQUIREMENT.fullmatch(line)
        if match is None:
            raise ValueError("lock contains a non-exact requirement")
        name = match.group(1).replace("_", "-").casefold()
        if name in versions:
            raise ValueError("lock contains a duplicate requirement")
        block = [line]
        index += 1
        while index < len(lines) and lines[index].startswith(" "):
            block.append(lines[index])
            index += 1
        if not any(re.fullmatch(r"\s+--hash=sha256:[0-9a-f]{64}\s*\\?", item) for item in block):
            raise ValueError("lock requirement has no SHA-256 hash")
        versions[name] = match.group(2)
    if not versions:
        raise ValueError("lock contains no requirements")
    return versions


def validate_supply_chain(
    root: Path = PROJECT_ROOT,
    workflow_path: Path = WORKFLOW_PATH,
) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    required = [
        root / "requirements/stage2.in",
        root / "requirements/stage2.lock",
        root / "container/Dockerfile.stage2-ci",
        root / "machine/stages/S2/supply-chain/pins.json",
        root / "machine/stages/S2/supply-chain/sbom.cdx.json",
        root / "machine/stages/S2/tools/sanitize_sbom.py",
        workflow_path,
    ]
    if any(not path.is_file() for path in required):
        return ["Stage 2 supply-chain artifact is missing"]

    lock_text = (root / "requirements/stage2.lock").read_text(encoding="utf-8")
    try:
        versions = requirement_versions(lock_text)
    except ValueError as exc:
        errors.append(str(exc))
        versions = {}
    if len(versions) != 78:
        errors.append("hash lock must contain the observed 78-package transitive closure")

    direct_lines = [
        line.strip()
        for line in (root / "requirements/stage2.in").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if len(direct_lines) != 14 or any(
        re.fullmatch(r"[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==[A-Za-z0-9_.+-]+", line) is None
        for line in direct_lines
    ):
        errors.append("Stage 2 direct inputs must contain 14 exact pins")

    pins = _load(root / "machine/stages/S2/supply-chain/pins.json")
    action_pins = pins.get("actions", {})
    if not isinstance(action_pins, dict) or set(action_pins) != {
        "actions/checkout",
        "actions/setup-python",
        "actions/dependency-review-action",
        "github/codeql-action",
    }:
        errors.append("Action pin catalog is incomplete")
        action_pins = {}
    for value in action_pins.values():
        if (
            not isinstance(value, dict)
            or re.fullmatch(r"[0-9a-f]{40}", str(value.get("commit_sha", ""))) is None
        ):
            errors.append("Action pin catalog contains a mutable reference")

    workflow = workflow_path.read_text(encoding="utf-8")
    uses = re.findall(r"^\s*-?\s*uses:\s*([^\s]+)\s*$", workflow, flags=re.MULTILINE)
    if len(uses) != 8 or any(_PINNED_ACTION.fullmatch(item) is None for item in uses):
        errors.append("all eight Stage 2 Action uses must be immutable commit SHAs")
    for action, metadata in action_pins.items():
        expected_sha = metadata.get("commit_sha") if isinstance(metadata, dict) else None
        if not any(
            item.rsplit("@", 1)[1] == expected_sha
            and (
                item.rsplit("@", 1)[0] == action or item.rsplit("@", 1)[0].startswith(action + "/")
            )
            for item in uses
        ):
            errors.append("workflow Action use drifts from the pin catalog")
    forbidden_workflow = (
        "self-hosted",
        "actions/cache",
        "upload-artifact",
        "download-artifact",
        "schedule:",
        "git push",
    )
    if any(token in workflow.casefold() for token in forbidden_workflow):
        errors.append("Stage 2 workflow contains a forbidden persistence or authority surface")
    errors.extend(
        validate_governance_dependency_workflow(
            workflow_path,
            repository_root=REPOSITORY_ROOT,
        )
    )
    required_workflow = (
        "--require-hashes",
        "pip_audit",
        "cyclonedx-py",
        "detect-secrets",
        "dependency-review-action",
        "codeql-action/init",
        "codeql-action/analyze",
        "validate_stage2.py",
        "docker build --no-cache",
    )
    if any(token not in workflow for token in required_workflow):
        errors.append("Stage 2 workflow is missing a required security gate")

    age = pins.get("age", {})
    age_digest = age.get("linux_amd64_archive_sha256") if isinstance(age, dict) else None
    if re.fullmatch(r"[0-9a-f]{64}", str(age_digest)) is None or str(age_digest) not in workflow:
        errors.append("official age archive digest is not consistently pinned")

    container = pins.get("container", {})
    container_digest = container.get("oci_index_digest") if isinstance(container, dict) else None
    dockerfile = (root / "container/Dockerfile.stage2-ci").read_text(encoding="utf-8")
    from_lines = [line for line in dockerfile.splitlines() if line.startswith("FROM ")]
    if (
        len(from_lines) != 1
        or not isinstance(container_digest, str)
        or _DIGEST.fullmatch(container_digest) is None
        or "@" + container_digest not in from_lines[0]
        or "--require-hashes" not in dockerfile
        or "not a production runtime image" not in dockerfile
    ):
        errors.append("Stage 2 validation container is not immutably and honestly defined")

    sbom = _load(root / "machine/stages/S2/supply-chain/sbom.cdx.json")
    if '"purl"' in json.dumps(sbom, separators=(",", ":")):
        errors.append("public SBOM still contains publication-unsafe PURL fields")
    components = sbom.get("components", []) if isinstance(sbom, dict) else []
    component_versions = {
        str(item.get("name", "")).replace("_", "-").casefold(): str(item.get("version", ""))
        for item in components
        if isinstance(item, dict)
    }
    metadata = sbom.get("metadata", {}) if isinstance(sbom, dict) else {}
    root_component = metadata.get("component", {}) if isinstance(metadata, dict) else {}
    root_ref = root_component.get("bom-ref") if isinstance(root_component, dict) else None
    dependencies = sbom.get("dependencies", []) if isinstance(sbom, dict) else []
    dependency_by_ref = {
        item.get("ref"): item.get("dependsOn", [])
        for item in dependencies
        if isinstance(item, dict) and isinstance(item.get("ref"), str)
    }
    component_refs = {item.get("bom-ref") for item in components if isinstance(item, dict)}
    all_refs = component_refs | ({root_ref} if isinstance(root_ref, str) else set())
    graph_valid = (
        set(dependency_by_ref) == all_refs
        and isinstance(root_ref, str)
        and len(dependency_by_ref.get(root_ref, [])) == 14
        and all(
            isinstance(children, list) and set(children).issubset(all_refs)
            for children in dependency_by_ref.values()
        )
        and sum(bool(children) for children in dependency_by_ref.values()) >= 15
    )
    if (
        sbom.get("bomFormat") != "CycloneDX"
        or sbom.get("specVersion") != "1.6"
        or not isinstance(root_component, dict)
        or root_component.get("name") != "moomooau-archive"
        or component_versions != versions
        or not graph_valid
    ):
        errors.append("CycloneDX SBOM inventory or dependency graph does not match the hash lock")
    return errors


if __name__ == "__main__":
    result = validate_supply_chain()
    print(json.dumps({"status": "PASS" if not result else "FAIL", "errors": result}, indent=2))
    raise SystemExit(bool(result))
