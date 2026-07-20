#!/usr/bin/env python3
"""Generate/check the deterministic foundation.002 dependency SBOM."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "machine/sbom/stage_1_foundation_002.cdx.json"

PYTHON_EXPECTED: dict[str, tuple[str, str, str]] = {
    "annotated-types": ("0.7.0", "MIT", "runtime_transitive"),
    "pydantic": ("2.13.4", "MIT", "runtime_direct"),
    "pydantic-core": ("2.46.4", "MIT", "runtime_transitive"),
    "typing-extensions": ("4.16.0", "PSF-2.0", "runtime_transitive"),
    "typing-inspection": ("0.4.2", "MIT", "runtime_transitive"),
}


class SbomError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SbomError(message)


def _pypi_ref(name: str, version: str) -> str:
    return f"pkg:pypi/{name}@{version}"


def _npm_ref(name: str, version: str) -> str:
    if name.startswith("@"):
        namespace, package = name[1:].split("/", 1)
        return f"pkg:npm/%40{namespace}/{package}@{version}"
    return f"pkg:npm/{name}@{version}"


def _component(*, name: str, version: str, license_id: str, purl: str, role: str, scope: str) -> dict[str, Any]:
    return {
        "bom-ref": purl,
        "licenses": [{"license": {"id": license_id}}],
        "name": name,
        "properties": [{"name": "x2n:dependency-role", "value": role}],
        "purl": purl,
        "scope": scope,
        "type": "library",
        "version": version,
    }


def _uv_registry_versions(text: str) -> dict[str, str]:
    packages: dict[str, str] = {}
    for block in text.split("[[package]]")[1:]:
        name = re.search(r'(?m)^name = "([^"]+)"$', block)
        version = re.search(r'(?m)^version = "([^"]+)"$', block)
        source = re.search(r"(?m)^source = (.+)$", block)
        if name and version and source and "registry" in source.group(1):
            packages[name.group(1)] = version.group(1)
    return packages


def build_sbom() -> dict[str, Any]:
    locked_python = _uv_registry_versions((PROJECT_ROOT / "uv.lock").read_text(encoding="utf-8"))
    _require(locked_python == {name: row[0] for name, row in PYTHON_EXPECTED.items()}, "uv registry dependency set/version drifted")

    npm = json.loads((PROJECT_ROOT / "package-lock.json").read_text(encoding="utf-8"))
    registry_npm: dict[str, dict[str, Any]] = {}
    for path, metadata in npm.get("packages", {}).items():
        if not path.startswith("node_modules/") or metadata.get("link") is True:
            continue
        name = path.removeprefix("node_modules/")
        if name == "typescript" or name.startswith("@typescript/typescript-"):
            registry_npm[name] = metadata
    # Preserve the historical Foundation002 Contract SBOM. Later Task
    # dependencies are inventoried by an additive, Task-specific SBOM.
    _require("typescript" in registry_npm, "TypeScript build dependency missing")
    _require(all(item.get("version") == "7.0.2" for item in registry_npm.values()), "TypeScript package version drifted")
    _require(all(item.get("license") == "Apache-2.0" for item in registry_npm.values()), "TypeScript package license drifted")
    _require(all("hasInstallScript" not in item for item in registry_npm.values()), "npm install script entered historical dependency set")
    platform_packages = sorted(name for name in registry_npm if name != "typescript")
    _require(len(platform_packages) == 20, "TypeScript platform package set drifted")
    _require(all(registry_npm[name].get("optional") is True for name in platform_packages), "TypeScript platform package is not optional")

    components: list[dict[str, Any]] = []
    for name, (version, license_id, role) in PYTHON_EXPECTED.items():
        components.append(
            _component(
                name=name,
                version=version,
                license_id=license_id,
                purl=_pypi_ref(name, version),
                role=role,
                scope="required",
            )
        )
    for name in sorted(registry_npm):
        role = "build_direct" if name == "typescript" else "build_optional_platform"
        components.append(
            _component(
                name=name,
                version="7.0.2",
                license_id="Apache-2.0",
                purl=_npm_ref(name, "7.0.2"),
                role=role,
                scope="optional",
            )
        )
    components.sort(key=lambda item: item["bom-ref"])

    pydantic_ref = _pypi_ref("pydantic", "2.13.4")
    typing_extensions_ref = _pypi_ref("typing-extensions", "4.16.0")
    typescript_ref = _npm_ref("typescript", "7.0.2")
    dependencies = [
        {
            "ref": "urn:x2n:component:contracts:0.0.0.1",
            "dependsOn": [pydantic_ref, typescript_ref],
        },
        {
            "ref": pydantic_ref,
            "dependsOn": [
                _pypi_ref("annotated-types", "0.7.0"),
                _pypi_ref("pydantic-core", "2.46.4"),
                typing_extensions_ref,
                _pypi_ref("typing-inspection", "0.4.2"),
            ],
        },
        {"ref": _pypi_ref("pydantic-core", "2.46.4"), "dependsOn": [typing_extensions_ref]},
        {"ref": _pypi_ref("typing-inspection", "0.4.2"), "dependsOn": [typing_extensions_ref]},
        {"ref": typescript_ref, "dependsOn": [_npm_ref(name, "7.0.2") for name in platform_packages]},
    ]
    leaf_refs = {item["bom-ref"] for item in components} - {item["ref"] for item in dependencies}
    dependencies.extend({"ref": ref, "dependsOn": []} for ref in sorted(leaf_refs))
    dependencies.sort(key=lambda item: item["ref"])

    return {
        "bomFormat": "CycloneDX",
        "components": components,
        "dependencies": dependencies,
        "metadata": {
            "component": {
                "bom-ref": "urn:x2n:component:contracts:0.0.0.1",
                "name": "x2n-contracts",
                "type": "library",
                "version": "0.0.0.1",
            },
            "properties": [
                {"name": "x2n:build-registry-packages", "value": str(len(registry_npm))},
                {"name": "x2n:install-scripts", "value": "0"},
                {"name": "x2n:runtime-registry-packages", "value": str(len(locked_python))},
                {"name": "x2n:source", "value": "frozen-package-lock-and-uv-lock"},
            ],
        },
        "serialNumber": "urn:uuid:00000000-0000-4000-8000-000000000102",
        "specVersion": "1.5",
        "version": 1,
    }


def _render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate/check foundation.002 SBOM")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        rendered = _render(build_sbom())
        if args.write:
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT.write_text(rendered, encoding="utf-8")
            print(json.dumps({"status": "WRITTEN", "components": 26}, sort_keys=True))
            return 0
        _require(OUTPUT.is_file(), "SBOM is missing")
        _require(OUTPUT.read_text(encoding="utf-8") == rendered, "SBOM drifted from frozen locks")
        print(json.dumps({"status": "PASS", "components": 26}, sort_keys=True))
        return 0
    except SbomError as error:
        print(json.dumps({"status": "FAIL_CLOSED", "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
