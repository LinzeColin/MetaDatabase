#!/usr/bin/env python3
"""Generate or verify the deterministic Foundation005 CI/release SBOM."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "machine/sbom/stage_1_foundation_005.cdx.json"
PYTHON_EXPECTED = {
    "annotated-types": ("0.7.0", "MIT", "runtime_transitive", "required"),
    "coverage": ("7.15.2", "Apache-2.0", "ci_coverage_direct", "optional"),
    "pydantic": ("2.13.4", "MIT", "runtime_direct", "required"),
    "pydantic-core": ("2.46.4", "MIT", "runtime_transitive", "required"),
    "pyyaml": ("6.0.3", "MIT", "ci_historical_test_direct", "optional"),
    "ruff": ("0.15.22", "MIT", "ci_format_lint_direct", "optional"),
    "typing-extensions": ("4.16.0", "PSF-2.0", "runtime_transitive", "required"),
    "typing-inspection": ("0.4.2", "MIT", "runtime_transitive", "required"),
}
PLAYWRIGHT_EXPECTED = {
    "@playwright/test": ("1.61.1", "Apache-2.0", "e2e_direct"),
    "playwright": ("1.61.1", "Apache-2.0", "e2e_transitive"),
    "playwright-core": ("1.61.1", "Apache-2.0", "e2e_transitive"),
    "fsevents": ("2.3.2", "MIT", "e2e_optional_platform"),
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
    _require(
        locked_python == {name: row[0] for name, row in PYTHON_EXPECTED.items()},
        "uv registry dependency set/version drifted",
    )

    lock = json.loads((PROJECT_ROOT / "package-lock.json").read_text(encoding="utf-8"))
    npm = {
        path.removeprefix("node_modules/"): metadata
        for path, metadata in lock.get("packages", {}).items()
        if path.startswith("node_modules/") and metadata.get("link") is not True
    }
    typescript_names = {name for name in npm if name == "typescript" or name.startswith("@typescript/typescript-")}
    _require(len(typescript_names) == 21, "TypeScript dependency set drifted")
    _require(set(npm) == typescript_names | set(PLAYWRIGHT_EXPECTED), "unexpected npm dependency entered Foundation005")
    for name in typescript_names:
        _require(
            npm[name].get("version") == "7.0.2" and npm[name].get("license") == "Apache-2.0",
            "TypeScript package metadata drifted",
        )
    for name, (version, license_id, _) in PLAYWRIGHT_EXPECTED.items():
        _require(
            npm[name].get("version") == version and npm[name].get("license") == license_id,
            f"dependency metadata drifted: {name}",
        )
    scripted = {name for name, item in npm.items() if item.get("hasInstallScript") is True}
    _require(scripted == {"fsevents"}, "install-script dependency set drifted")
    _require(
        npm["fsevents"].get("optional") is True and npm["fsevents"].get("os") == ["darwin"],
        "fsevents is not optional macOS-only",
    )
    _require(
        "ignore-scripts=true" in (PROJECT_ROOT / ".npmrc").read_text(encoding="utf-8").splitlines(),
        "npm install scripts are not disabled",
    )

    components = [
        _component(
            name=name,
            version=version,
            license_id=license_id,
            purl=_pypi_ref(name, version),
            role=role,
            scope=scope,
        )
        for name, (version, license_id, role, scope) in PYTHON_EXPECTED.items()
    ]
    for name in sorted(npm):
        if name in PLAYWRIGHT_EXPECTED:
            version, license_id, role = PLAYWRIGHT_EXPECTED[name]
        else:
            version, license_id = "7.0.2", "Apache-2.0"
            role = "build_direct" if name == "typescript" else "build_optional_platform"
        components.append(
            _component(
                name=name,
                version=version,
                license_id=license_id,
                purl=_npm_ref(name, version),
                role=role,
                scope="optional",
            )
        )
    components.sort(key=lambda item: item["bom-ref"])

    root_ref = "urn:x2n:component:foundation005:0.0.0.1"
    dependencies: list[dict[str, Any]] = [
        {
            "ref": root_ref,
            "dependsOn": [
                _npm_ref("@playwright/test", "1.61.1"),
                _pypi_ref("coverage", "7.15.2"),
                _pypi_ref("pydantic", "2.13.4"),
                _pypi_ref("pyyaml", "6.0.3"),
                _pypi_ref("ruff", "0.15.22"),
                _npm_ref("typescript", "7.0.2"),
            ],
        },
        {"ref": _npm_ref("@playwright/test", "1.61.1"), "dependsOn": [_npm_ref("playwright", "1.61.1")]},
        {
            "ref": _npm_ref("playwright", "1.61.1"),
            "dependsOn": [_npm_ref("fsevents", "2.3.2"), _npm_ref("playwright-core", "1.61.1")],
        },
        {
            "ref": _pypi_ref("pydantic", "2.13.4"),
            "dependsOn": [
                _pypi_ref("annotated-types", "0.7.0"),
                _pypi_ref("pydantic-core", "2.46.4"),
                _pypi_ref("typing-extensions", "4.16.0"),
                _pypi_ref("typing-inspection", "0.4.2"),
            ],
        },
        {
            "ref": _pypi_ref("pydantic-core", "2.46.4"),
            "dependsOn": [_pypi_ref("typing-extensions", "4.16.0")],
        },
        {
            "ref": _pypi_ref("typing-inspection", "0.4.2"),
            "dependsOn": [_pypi_ref("typing-extensions", "4.16.0")],
        },
        {
            "ref": _npm_ref("typescript", "7.0.2"),
            "dependsOn": [_npm_ref(name, "7.0.2") for name in sorted(typescript_names - {"typescript"})],
        },
    ]
    referenced = {row["ref"] for row in dependencies}
    dependencies.extend(
        {"ref": item["bom-ref"], "dependsOn": []} for item in components if item["bom-ref"] not in referenced
    )
    dependencies.sort(key=lambda item: item["ref"])

    return {
        "bomFormat": "CycloneDX",
        "components": components,
        "dependencies": dependencies,
        "metadata": {
            "component": {
                "bom-ref": root_ref,
                "name": "x2n-foundation005-ci-baseline",
                "type": "application",
                "version": "0.0.0.1",
            },
            "properties": [
                {"name": "x2n:ci-python-components", "value": "3"},
                {"name": "x2n:install-script-packages", "value": "fsevents"},
                {"name": "x2n:install-scripts-executed", "value": "0"},
                {"name": "x2n:npm-install-policy", "value": "ignore-scripts"},
                {"name": "x2n:registry-components", "value": str(len(components))},
                {"name": "x2n:runtime-python-components", "value": "5"},
                {"name": "x2n:source", "value": "frozen-package-lock-and-uv-lock"},
            ],
        },
        "serialNumber": "urn:uuid:00000000-0000-4000-8000-000000000105",
        "specVersion": "1.5",
        "version": 1,
    }


def _render(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate/check Foundation005 SBOM")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        payload = build_sbom()
        rendered = _render(payload)
        if args.write:
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT.write_text(rendered, encoding="utf-8")
            status = "WRITTEN"
        else:
            _require(OUTPUT.is_file() and OUTPUT.read_text(encoding="utf-8") == rendered, "Foundation005 SBOM drifted")
            status = "PASS"
        print(
            json.dumps(
                {
                    "components": len(payload["components"]),
                    "install_scripts_executed": 0,
                    "status": status,
                    "unknown_licenses": 0,
                },
                sort_keys=True,
            )
        )
        return 0
    except (OSError, json.JSONDecodeError, SbomError) as error:
        print(json.dumps({"reason": str(error), "status": "FAIL_CLOSED"}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
