#!/usr/bin/env python3
"""Durable negative oracles for the Stock Skill CI helpers."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_RUNNER = REPO_ROOT / "Stock_Skill/scripts/run_unittests.py"
SAFETY_VALIDATOR = REPO_ROOT / "Stock_Skill/scripts/validate_public_safety.py"
SYNTHETIC_FINE_GRAINED_PAT = "github_" + "pat_" + ("A" * 82)
SYNTHETIC_STATELESS_APP_TOKEN = (
    "ghs_"
    + "12345_"
    + "eyJhbGciOiJSUzI1NiJ9."
    + ("A" * 80)
    + "."
    + ("B" * 79)
    + "-"
)


class StockSkillCiHelperTests(unittest.TestCase):
    def _run(self, script: Path, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(script), "--repo-root", str(root)],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

    @staticmethod
    def _public_fixture(root: Path) -> Path:
        (root / "Stock_Skill").mkdir(parents=True)
        (root / "AGENTS.md").write_text("public rules\n", encoding="utf-8")
        (root / "README.md").write_text("public readme\n", encoding="utf-8")
        stock_readme = root / "Stock_Skill/README.md"
        stock_readme.write_text("public stock skills\n", encoding="utf-8")
        return stock_readme

    def test_unittest_runner_rejects_zero_case_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-zero-case-") as raw:
            root = Path(raw)
            tests = root / "Stock_Skill/tests"
            tests.mkdir(parents=True)
            (tests / "test_empty.py").write_bytes(b"")
            result = self._run(TEST_RUNNER, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("zero test cases", result.stderr)

    def test_unittest_runner_reports_actual_positive_case_count(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-positive-case-") as raw:
            root = Path(raw)
            tests = root / "Stock_Skill/tests"
            tests.mkdir(parents=True)
            (tests / "test_one.py").write_text(
                "import unittest\n"
                "class OneTest(unittest.TestCase):\n"
                "    def test_one(self): self.assertTrue(True)\n",
                encoding="utf-8",
            )
            result = self._run(TEST_RUNNER, root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS: 1 test case(s)", result.stdout)

    def test_unittest_runner_rejects_failing_case(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-failing-case-") as raw:
            root = Path(raw)
            tests = root / "Stock_Skill/tests"
            tests.mkdir(parents=True)
            (tests / "test_failure.py").write_text(
                "import unittest\n"
                "class FailureTest(unittest.TestCase):\n"
                "    def test_failure(self): self.fail('synthetic failure')\n",
                encoding="utf-8",
            )
            result = self._run(TEST_RUNNER, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FAILED", result.stderr)

    def test_public_safety_rejects_fine_grained_pat_in_plain_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-pat-plain-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            stock_readme.write_text(
                f"synthetic credential: {SYNTHETIC_FINE_GRAINED_PAT}\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("forbidden GitHub fine-grained PAT", result.stderr)

    def test_public_safety_rejects_fine_grained_pat_in_zip_payload(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-pat-zip-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("payload.txt", SYNTHETIC_FINE_GRAINED_PAT)
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "synthetic.zip!payload.txt: forbidden GitHub fine-grained PAT",
                result.stderr,
            )

    def test_public_safety_rejects_windows_style_zip_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-zip-path-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            for name in (
                "..\\escape.txt",
                "C:\\escape.txt",
                "C:/escape.txt",
                "\\\\server\\share\\escape.txt",
                "folder\\file.txt",
            ):
                with self.subTest(name=name):
                    with ZipFile(
                        archive_path, "w", compression=ZIP_DEFLATED
                    ) as archive:
                        archive.writestr(name, "benign")
                    result = self._run(SAFETY_VALIDATOR, root)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("unsafe ZIP path", result.stderr)

    def test_public_safety_rejects_nonempty_zip_directory_payload(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-zip-dir-payload-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            directory = ZipInfo("concealed/")
            directory.compress_type = ZIP_DEFLATED
            with ZipFile(archive_path, "w") as archive:
                archive.writestr(directory, SYNTHETIC_FINE_GRAINED_PAT)
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("non-empty directory ZIP entry", result.stderr)

    def test_public_safety_allows_empty_zip_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-zip-empty-dir-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("empty/", b"")
                archive.writestr("empty/payload.txt", "benign")
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("1 ZIP entries", result.stdout)

    def test_public_safety_rejects_stateless_app_token_in_plain_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-ghs-plain-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            stock_readme.write_text(
                f"synthetic credential: {SYNTHETIC_STATELESS_APP_TOKEN}\n",
                encoding="utf-8",
            )
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("forbidden GitHub stateless App token", result.stderr)

    def test_public_safety_rejects_stateless_app_token_in_zip_payload(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-ghs-zip-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("payload.txt", SYNTHETIC_STATELESS_APP_TOKEN)
            result = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("forbidden GitHub stateless App token", result.stderr)

    def test_public_safety_rejects_bare_and_child_user_home_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-bare-home-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            mac_root = "/" + "Users/"
            mac_case_root = "/" + "users/"
            linux_root = "/" + "home/"
            windows_root = "C:" + "\\" + "Users\\"
            windows_case_root = "c:" + "\\" + "users\\"
            windows_forward_case_root = "c:" + "/" + "users/"
            ascii_user = "exampleuser"
            unicode_user = "测试用户"
            cases = (
                ("macOS user path", mac_root + ascii_user),
                ("macOS user path", mac_root + ascii_user + "/project"),
                ("macOS user path", mac_case_root + ascii_user),
                ("macOS user path", mac_root + unicode_user),
                ("Linux user path", linux_root + ascii_user),
                ("Linux user path", linux_root + ascii_user + "/project"),
                ("Linux user path", linux_root + unicode_user),
                ("Windows user path", windows_root + ascii_user),
                ("Windows user path", windows_root + ascii_user + "\\project"),
                ("Windows user path", windows_case_root + ascii_user),
                ("Windows user path", windows_forward_case_root + ascii_user),
                ("Windows user path", windows_root + unicode_user),
            )
            for pattern_name, value in cases:
                with self.subTest(pattern_name=pattern_name):
                    stock_readme.write_text(value + "\n", encoding="utf-8")
                    result = self._run(SAFETY_VALIDATOR, root)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(f"forbidden {pattern_name}", result.stderr)

    def test_public_safety_rejects_case_and_unicode_user_homes_in_zip(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-home-zip-") as raw:
            root = Path(raw)
            self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            values = (
                "/" + "users/" + "exampleuser",
                "c:" + "\\" + "users\\" + "exampleuser",
                "c:" + "/" + "users/" + "exampleuser",
                "/" + "Users/" + "测试用户",
                "/" + "home/" + "测试用户",
                "C:" + "\\" + "Users\\" + "测试用户",
            )
            for value in values:
                with self.subTest(value=value):
                    with ZipFile(
                        archive_path, "w", compression=ZIP_DEFLATED
                    ) as archive:
                        archive.writestr("payload.txt", value)
                    result = self._run(SAFETY_VALIDATOR, root)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("forbidden", result.stderr)

    def test_public_safety_allows_ellipsis_path_placeholder(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-path-placeholder-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            placeholders = (
                "/" + "Users/" + "...",
                "/" + "users/" + "…",
                "/" + "home/" + "...",
                "C:" + "\\" + "Users\\" + "...",
            )
            for placeholder in placeholders:
                with self.subTest(placeholder=placeholder):
                    stock_readme.write_text(
                        f"portable documentation placeholder: `{placeholder}`\n",
                        encoding="utf-8",
                    )
                    result = self._run(SAFETY_VALIDATOR, root)
                    self.assertEqual(
                        result.returncode, 0, result.stdout + result.stderr
                    )

    def test_historical_path_allowlist_is_exact_and_backticked(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-historical-path-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            exact_path = "/home/" + "oai/" + "skills"
            safe_boundaries = ("\n", ".\n", "；继续说明\n", ")\n")
            for boundary in safe_boundaries:
                with self.subTest(boundary=boundary):
                    stock_readme.write_text(
                        f"historical: `{exact_path}`{boundary}", encoding="utf-8"
                    )
                    passing = self._run(SAFETY_VALIDATOR, root)
                    self.assertEqual(
                        passing.returncode, 0, passing.stdout + passing.stderr
                    )
            stock_readme.write_text(
                f"unbackticked historical path: {exact_path}\n", encoding="utf-8"
            )
            unbackticked = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(unbackticked.returncode, 0)
            self.assertIn("forbidden Linux user path", unbackticked.stderr)
            stock_readme.write_text(
                f"historical file URI: `file://{exact_path}`\n", encoding="utf-8"
            )
            file_uri = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(file_uri.returncode, 0)
            self.assertIn("forbidden Linux user path", file_uri.stderr)
            stock_readme.write_text(
                f"historical child: `{exact_path}/private`\n", encoding="utf-8"
            )
            failing = self._run(SAFETY_VALIDATOR, root)
            self.assertNotEqual(failing.returncode, 0)
            self.assertIn("forbidden Linux user path", failing.stderr)

    def test_historical_path_allowlist_rejects_post_backtick_continuation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="stock-ci-historical-boundary-") as raw:
            root = Path(raw)
            stock_readme = self._public_fixture(root)
            archive_path = root / "Stock_Skill/synthetic.zip"
            exact_path = "/home/" + "oai/" + "skills"
            continuations = (
                "/private",
                "\\private",
                "suffix",
                "_suffix",
                "-suffix",
                "9",
                "测试",
                "@suffix",
            )
            for continuation in continuations:
                payload = f"`{exact_path}`{continuation}"
                with self.subTest(surface="plain", continuation=continuation):
                    if archive_path.exists():
                        archive_path.unlink()
                    stock_readme.write_text(payload + "\n", encoding="utf-8")
                    plain = self._run(SAFETY_VALIDATOR, root)
                    self.assertNotEqual(plain.returncode, 0)
                    self.assertIn(
                        "Stock_Skill/README.md: forbidden Linux user path",
                        plain.stderr,
                    )
                with self.subTest(surface="zip", continuation=continuation):
                    stock_readme.write_text("public stock skills\n", encoding="utf-8")
                    with ZipFile(
                        archive_path, "w", compression=ZIP_DEFLATED
                    ) as archive:
                        archive.writestr("payload.txt", payload)
                    zipped = self._run(SAFETY_VALIDATOR, root)
                    self.assertNotEqual(zipped.returncode, 0)
                    self.assertIn(
                        "synthetic.zip!payload.txt: forbidden Linux user path",
                        zipped.stderr,
                    )


if __name__ == "__main__":
    unittest.main()
