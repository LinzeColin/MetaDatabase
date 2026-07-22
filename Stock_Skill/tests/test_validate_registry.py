#!/usr/bin/env python3
"""Isolated success and fail-closed tests for the stock Skill registry."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPO_ROOT / "Stock_Skill/scripts/validate_registry.py"
REGISTRY_PATH = REPO_ROOT / "Stock_Skill/REGISTRY.json"
LEGACY_ENTRY_PROJECTION_SHA256 = (
    "41232c50c051ebc4b5d2e9503bba6c938b8b6e83f81f69bd322ccfdaeeaf98a0"
)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    value.update(path.read_bytes())
    return value.hexdigest()


def load_validator_module():
    spec = importlib.util.spec_from_file_location("stock_registry_validator", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load validator: {VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = load_validator_module()


class RegistryValidatorIsolationTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        active_registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        active_entry = next(
            item
            for item in active_registry["skills"]
            if item["id"] == "stock-commercial-opportunities"
        )
        locked_paths = [
            REGISTRY_PATH,
            VALIDATOR_PATH,
            REPO_ROOT / active_entry["release"]["path"],
            *(
                REPO_ROOT / archive["path"]
                for archive in active_entry["superseded_archives"]
            ),
        ]
        self.active_fingerprints = {path: digest(path) for path in locked_paths}
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="stock-registry-fixture-"
        )
        self.fixture_repo = Path(self.temporary_directory.name)
        self.fixture_registry_path = self.fixture_repo / "Stock_Skill/REGISTRY.json"
        self.fixture_validator_path = (
            self.fixture_repo / "Stock_Skill/scripts/validate_registry.py"
        )
        self.registry: dict[str, object] | None = None

    def tearDown(self) -> None:
        try:
            for path, expected in self.active_fingerprints.items():
                self.assertEqual(digest(path), expected, f"active file mutated: {path}")
        finally:
            self.temporary_directory.cleanup()

    def _write_text(self, relative: str, content: str) -> Path:
        path = self.fixture_repo.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    @staticmethod
    def _write_manifest(root: Path, manifest_name: str) -> None:
        manifest = root / manifest_name
        files = sorted(
            (path for path in root.rglob("*") if path.is_file() and path != manifest),
            key=lambda path: path.relative_to(root).as_posix().encode("utf-8"),
        )
        lines = [
            f"{digest(path)}  ./{path.relative_to(root).as_posix()}" for path in files
        ]
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_registry(self, registry: object) -> None:
        self.fixture_registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.fixture_registry_path.write_text(
            json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _build_fixture(
        self,
        *,
        version_scheme: str = "numeric-quad",
        version: str = "0.0.0.1",
        latest_major: object = 0,
        archive_versions: tuple[str, ...] = (),
    ) -> None:
        skill_id = "fixture-skill"
        display_name = "Fixture Skill"
        project_relative = "Stock_Skill/fixture-skill-project"
        skill_relative = f"{project_relative}/task-pack/skill_draft/{skill_id}"
        project = self.fixture_repo.joinpath(*project_relative.split("/"))
        task_pack = project / "task-pack"
        skill = self.fixture_repo.joinpath(*skill_relative.split("/"))

        self.fixture_validator_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(VALIDATOR_PATH, self.fixture_validator_path)

        claim = f"{skill_id}={version}\n"
        claim_paths = [
            "AGENTS.md",
            "README.md",
            "Stock_Skill/AGENTS.md",
            "Stock_Skill/README.md",
            f"{project_relative}/AGENTS.md",
            f"{project_relative}/README.md",
        ]
        for claim_path in claim_paths:
            self._write_text(claim_path, claim)
        self._write_text(
            f"{project_relative}/README.md",
            claim + f"Version：`{version}`\n",
        )

        self._write_text(f"{project_relative}/VERSION", version + "\n")
        self._write_text(f"{project_relative}/task-pack/VERSION", version + "\n")
        self._write_text(
            f"{skill_relative}/SKILL.md",
            f"---\nname: {skill_id}\ndescription: Isolated registry fixture.\n---\n",
        )
        self._write_text(
            f"{skill_relative}/agents/openai.yaml",
            f"display_name: {display_name}\ndefault_prompt: Use ${skill_id}\n",
        )

        release_relative = (
            f"{project_relative}/releases/{skill_id}_task-pack_v{version}.zip"
        )
        release = self._write_text(release_relative, f"release {version}\n")
        release_sha = digest(release)
        self._write_text(
            f"{project_relative}/releases/SHA256SUMS",
            f"{release_sha}  {release.name}\n",
        )

        archives: list[dict[str, str]] = []
        for index, archive_version in enumerate(archive_versions):
            archive_relative = (
                f"{project_relative}/archives/archive_{index}_v{archive_version}.zip"
            )
            archive = self._write_text(
                archive_relative, f"archive {index} {archive_version}\n"
            )
            archives.append(
                {
                    "version": archive_version,
                    "status": "ARCHIVE_ONLY",
                    "path": archive_relative,
                    "sha256": digest(archive),
                }
            )

        self._write_manifest(task_pack, "MANIFEST.sha256")
        self._write_manifest(project, "BACKUP_MANIFEST.sha256")

        self.registry = {
            "schema_version": "1.1",
            "registry_id": "stock-skill",
            "updated_at": "2026-07-22",
            "latest_resolution_rule": "Fixture values are current only when valid.",
            "legacy_paths_must_not_exist": [],
            "skills": [
                {
                    "id": skill_id,
                    "display_name": display_name,
                    "latest_version": version,
                    "version_scheme": version_scheme,
                    "latest_major": latest_major,
                    "current": True,
                    "distribution_mode": "SOURCE_ONLY",
                    "local_install_policy": "PROHIBITED",
                    "canonical_project_path": project_relative,
                    "canonical_skill_path": skill_relative,
                    "version_sources": [
                        f"{project_relative}/VERSION",
                        f"{project_relative}/task-pack/VERSION",
                    ],
                    "version_claim_paths": claim_paths,
                    "release": {"path": release_relative, "sha256": release_sha},
                    "superseded_archives": archives,
                }
            ],
        }
        self._write_registry(self.registry)

    def _run_fixture_validator(self) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, str(self.fixture_validator_path)],
            cwd=self.fixture_repo,
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )

    def _assert_registry_fails(self, registry: object, message: str) -> None:
        self._write_registry(registry)
        result = self._run_fixture_validator()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(message, result.stderr)

    def test_active_registry_preserves_legacy_entry_and_passes(self) -> None:
        registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        self.assertEqual(registry["schema_version"], "1.1")
        entry = copy.deepcopy(
            next(
                item
                for item in registry["skills"]
                if item["id"] == "stock-commercial-opportunities"
            )
        )
        self.assertEqual(entry.pop("version_scheme"), "semver")
        canonical = json.dumps(
            entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            LEGACY_ENTRY_PROJECTION_SHA256,
        )
        result = subprocess.run(
            [sys.executable, str(VALIDATOR_PATH)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: stock Skill registry valid", result.stdout)
        self.assertIn(
            "CURRENT: stock-commercial-opportunities=3.0.0 (v3)",
            result.stdout,
        )

    def test_semver_with_archive_passes(self) -> None:
        self._build_fixture(
            version_scheme="semver",
            version="3.0.0",
            latest_major=3,
            archive_versions=("2.0.0", "1.0.0"),
        )
        result = self._run_fixture_validator()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CURRENT: fixture-skill=3.0.0 (v3)", result.stdout)

    def test_numeric_quad_with_empty_archives_passes(self) -> None:
        self._build_fixture()
        result = self._run_fixture_validator()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "CURRENT: fixture-skill=0.0.0.1 (v0.0.0.1)", result.stdout
        )

    def test_scheme_is_required_known_and_string(self) -> None:
        self._build_fixture()
        assert self.registry is not None
        for name, value in (
            ("missing", None),
            ("unknown", "calendar"),
            ("wrong-type", ["numeric-quad"]),
        ):
            with self.subTest(name=name):
                registry = copy.deepcopy(self.registry)
                entry = registry["skills"][0]
                if name == "missing":
                    entry.pop("version_scheme")
                else:
                    entry["version_scheme"] = value
                self._assert_registry_fails(registry, "invalid version_scheme")

    def test_versions_must_be_present_and_canonical_for_scheme(self) -> None:
        self._build_fixture()
        assert self.registry is not None
        cases = (
            ("missing", None),
            ("wrong-arity", "0.0.1"),
            ("leading-zero", "0.0.0.01"),
            ("prefix", "v0.0.0.1"),
            ("suffix", "0.0.0.1-alpha"),
        )
        for name, value in cases:
            with self.subTest(name=name):
                registry = copy.deepcopy(self.registry)
                entry = registry["skills"][0]
                if name == "missing":
                    entry.pop("latest_version")
                else:
                    entry["latest_version"] = value
                self._assert_registry_fails(registry, "invalid latest_version")

    def test_latest_major_requires_exact_non_boolean_integer(self) -> None:
        self._build_fixture()
        assert self.registry is not None
        for value in (1, True, "0", None):
            with self.subTest(value=value):
                registry = copy.deepcopy(self.registry)
                registry["skills"][0]["latest_major"] = value
                self._assert_registry_fails(
                    registry, "latest_major does not match latest_version"
                )

    def test_archives_are_required_array_but_may_be_empty(self) -> None:
        self._build_fixture()
        assert self.registry is not None
        passing = self._run_fixture_validator()
        self.assertEqual(passing.returncode, 0, passing.stdout + passing.stderr)
        for name, value in (
            ("missing", None),
            ("null", None),
            ("object", {}),
            ("string", "[]"),
        ):
            with self.subTest(name=name):
                registry = copy.deepcopy(self.registry)
                entry = registry["skills"][0]
                if name == "missing":
                    entry.pop("superseded_archives")
                else:
                    entry["superseded_archives"] = value
                self._assert_registry_fails(
                    registry, "superseded_archives must be an array"
                )

    def test_archive_lineage_is_same_scheme_unique_and_older(self) -> None:
        self._build_fixture(archive_versions=("0.0.0.0",))
        assert self.registry is not None
        baseline = self.registry

        same = copy.deepcopy(baseline)
        same["skills"][0]["superseded_archives"][0]["version"] = "0.0.0.1"
        self._assert_registry_fails(same, "version must be older than latest")

        wrong_arity = copy.deepcopy(baseline)
        wrong_arity["skills"][0]["superseded_archives"][0]["version"] = "0.0.0"
        self._assert_registry_fails(
            wrong_arity, "invalid version for version_scheme numeric-quad"
        )

        duplicate = copy.deepcopy(baseline)
        duplicate["skills"][0]["superseded_archives"].append(
            copy.deepcopy(duplicate["skills"][0]["superseded_archives"][0])
        )
        self._assert_registry_fails(duplicate, "duplicate version")

        explicit_scheme = copy.deepcopy(baseline)
        explicit_scheme["skills"][0]["superseded_archives"][0][
            "version_scheme"
        ] = "numeric-quad"
        self._assert_registry_fails(
            explicit_scheme, "version_scheme must be inherited"
        )

    def test_archive_items_must_be_objects(self) -> None:
        self._build_fixture(archive_versions=("0.0.0.0",))
        assert self.registry is not None
        for value in (None, "0.0.0.0", ["0.0.0.0"]):
            with self.subTest(value=value):
                registry = copy.deepcopy(self.registry)
                registry["skills"][0]["superseded_archives"][0] = value
                self._assert_registry_fails(registry, "must be an object")

    def test_root_schema_and_root_type_fail_closed(self) -> None:
        self._build_fixture()
        assert self.registry is not None
        for name, value in (
            ("missing", None),
            ("legacy", "1.0"),
            ("unknown", "9.9"),
            ("wrong-type", 1.1),
        ):
            with self.subTest(name=name):
                registry = copy.deepcopy(self.registry)
                if name == "missing":
                    registry.pop("schema_version")
                else:
                    registry["schema_version"] = value
                self._assert_registry_fails(registry, "schema_version must be 1.1")
        self._assert_registry_fails([], "registry root must be an object")

    def test_compare_versions_rejects_cross_scheme(self) -> None:
        with self.assertRaises(ValueError):
            VALIDATOR.compare_versions(
                "1.2.3", "semver", "1.2.3.0", "numeric-quad"
            )


if __name__ == "__main__":
    unittest.main()
