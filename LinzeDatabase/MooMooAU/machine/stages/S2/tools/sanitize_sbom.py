#!/usr/bin/env python3
"""Remove PURL strings that resemble addresses under the frozen publication scanner."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

_REQUIREMENT = re.compile(
    r"^([A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?==[A-Za-z0-9_.+-]+(?:\s*;.*)?\s*\\$"
)


def without_purls(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: without_purls(item) for key, item in value.items() if key != "purl"}
    if isinstance(value, list):
        return [without_purls(item) for item in value]
    return value


def _normalize_name(value: str) -> str:
    match = re.match(r"[A-Za-z0-9_.-]+", value)
    if match is None:
        raise ValueError("dependency annotation contains an invalid package name")
    return match.group(0).replace("_", "-").casefold()


def _lock_lineage(lock_text: str) -> tuple[dict[str, set[str]], set[str]]:
    parents_by_child: dict[str, set[str]] = {}
    direct: set[str] = set()
    lines = lock_text.splitlines()
    index = 0
    while index < len(lines):
        match = _REQUIREMENT.fullmatch(lines[index])
        if match is None:
            index += 1
            continue
        child = _normalize_name(match.group(1))
        block: list[str] = []
        index += 1
        while index < len(lines) and (not lines[index] or lines[index].startswith(" ")):
            block.append(lines[index])
            index += 1
        parents: set[str] = set()
        for line_index, line in enumerate(block):
            stripped = line.strip()
            if stripped.startswith("# via -r "):
                direct.add(child)
            elif stripped.startswith("# via "):
                parents.add(_normalize_name(stripped.removeprefix("# via ")))
            elif stripped == "# via":
                for continuation in block[line_index + 1 :]:
                    candidate = continuation.strip()
                    if not candidate.startswith("#   "):
                        break
                    parent = candidate.removeprefix("#   ")
                    if parent.startswith("-r "):
                        direct.add(child)
                    else:
                        parents.add(_normalize_name(parent))
        parents_by_child[child] = parents
    return parents_by_child, direct


def with_dependency_graph(value: Any, lock_text: str) -> Any:
    if not isinstance(value, dict):
        raise ValueError("SBOM root must be an object")
    metadata = value.get("metadata")
    components = value.get("components")
    if not isinstance(metadata, dict) or not isinstance(components, list):
        raise ValueError("SBOM metadata or components are missing")
    root = metadata.get("component")
    if not isinstance(root, dict) or not isinstance(root.get("bom-ref"), str):
        raise ValueError("SBOM root component reference is missing")
    component_refs: dict[str, str] = {}
    for component in components:
        if (
            not isinstance(component, dict)
            or not isinstance(component.get("name"), str)
            or not isinstance(component.get("bom-ref"), str)
        ):
            raise ValueError("SBOM component identity is invalid")
        component_refs[_normalize_name(component["name"])] = component["bom-ref"]
    parents_by_child, direct = _lock_lineage(lock_text)
    if set(parents_by_child) != set(component_refs):
        raise ValueError("SBOM components do not match lock lineage")

    edges: dict[str, set[str]] = {reference: set() for reference in component_refs.values()}
    root_ref = root["bom-ref"]
    edges[root_ref] = {component_refs[name] for name in direct}
    for child, parents in parents_by_child.items():
        child_ref = component_refs[child]
        for parent in parents:
            try:
                edges[component_refs[parent]].add(child_ref)
            except KeyError as exc:
                raise ValueError("lock lineage references an unknown package") from exc
    value["dependencies"] = [
        {"ref": reference, **({"dependsOn": sorted(children)} if children else {})}
        for reference, children in sorted(edges.items())
    ]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = json.loads(args.input.read_text(encoding="utf-8"))
    sanitized = without_purls(value)
    completed = with_dependency_graph(sanitized, args.lock.read_text(encoding="utf-8"))
    args.output.write_text(
        json.dumps(completed, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
