#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


KIT = Path(__file__).resolve().parents[1]
PROFILE_PATH = KIT / "scripts/resource_profile.py"
WRAPPER = KIT / "scripts/select-resource-profile.sh"
SPEC = importlib.util.spec_from_file_location("resource_profile", PROFILE_PATH)
assert SPEC and SPEC.loader
RESOURCE_PROFILE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RESOURCE_PROFILE)


def measurement(
    *,
    total: int,
    available: int,
    free_disk: int,
    disk_used: float = 40,
    inode_used: float = 10,
    swap_total: int = 1024,
    swap_free: int = 1024,
    load: float = 0.2,
    cpu: int = 2,
    queue: int = 0,
) -> dict:
    return {
        "schema_version": 1,
        "source": "fixture",
        "captured_at": "fixture",
        "memory": {
            "total_mb": total,
            "available_mb": available,
            "swap_total_mb": swap_total,
            "swap_free_mb": swap_free,
        },
        "load": {"one_minute": load, "cpu_count": cpu},
        "storage": {
            "root": {
                "free_mb": free_disk,
                "used_percent": disk_used,
                "inode_used_percent": inode_used,
            }
        },
        "queue": {"depth": queue},
    }


class ResourceProfileTests(unittest.TestCase):
    def test_selects_all_three_profiles_from_measurements(self) -> None:
        fixtures = {
            "constrained": measurement(total=1900, available=1800, free_disk=10000),
            "tiny": measurement(total=4096, available=3000, free_disk=25000),
            "standard": measurement(total=8192, available=6000, free_disk=60000),
        }
        for expected, fixture in fixtures.items():
            with self.subTest(expected=expected):
                result = RESOURCE_PROFILE.select_profile(fixture)
                self.assertEqual(result["profile"], expected)
                self.assertTrue(result["activation_safe"])
                self.assertEqual(result["guard"]["state"], "recover")
                self.assertLessEqual(
                    sum(result["disk"]["caps_mb"].values()),
                    result["disk"]["allocatable_mb"],
                )

    def test_pressure_downgrades_and_protects(self) -> None:
        high_swap = measurement(
            total=8192,
            available=6000,
            free_disk=60000,
            swap_total=4096,
            swap_free=1024,
        )
        self.assertEqual(
            RESOURCE_PROFILE.select_profile(high_swap)["profile"], "tiny"
        )

        cases = {
            "memory": measurement(total=4096, available=400, free_disk=25000),
            "disk": measurement(
                total=4096,
                available=3000,
                free_disk=25000,
                disk_used=92,
            ),
            "inode": measurement(
                total=4096,
                available=3000,
                free_disk=25000,
                inode_used=92,
            ),
            "queue": measurement(
                total=4096,
                available=3000,
                free_disk=25000,
                queue=50,
            ),
        }
        for reason, fixture in cases.items():
            with self.subTest(reason=reason):
                result = RESOURCE_PROFILE.select_profile(fixture)
                self.assertEqual(result["guard"]["state"], "protect")
                self.assertIn(reason, result["guard"]["protect_reasons"])

    def test_recovery_requires_all_predicates(self) -> None:
        warning = measurement(
            total=4096,
            available=3000,
            free_disk=25000,
            queue=40,
        )
        recovered = measurement(
            total=4096,
            available=3000,
            free_disk=25000,
            queue=0,
        )
        self.assertEqual(
            RESOURCE_PROFILE.select_profile(warning)["guard"]["state"], "warn"
        )
        self.assertEqual(
            RESOURCE_PROFILE.select_profile(recovered)["guard"]["state"], "recover"
        )

        boundaries = (
            measurement(
                total=4096,
                available=3000,
                free_disk=25000,
                disk_used=80,
            ),
            measurement(
                total=4096,
                available=3000,
                free_disk=25000,
                inode_used=80,
            ),
            measurement(
                total=4096,
                available=3000,
                free_disk=25000,
                queue=40,
            ),
        )
        for fixture in boundaries:
            self.assertEqual(
                RESOURCE_PROFILE.select_profile(fixture)["guard"]["state"],
                "warn",
            )

    def test_unsafe_write_is_refused(self) -> None:
        unsafe = measurement(total=1024, available=300, free_disk=3000)
        with tempfile.TemporaryDirectory(prefix="cyberboss-profile-test-") as temp:
            root = Path(temp)
            fixture = root / "unsafe.json"
            output = root / "profile.env"
            fixture.write_text(json.dumps(unsafe), encoding="utf-8")
            result = subprocess.run(
                [
                    str(WRAPPER),
                    "--measurements",
                    str(fixture),
                    "--write",
                    str(output),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 3)
            self.assertFalse(output.exists())
            self.assertIn("PROFILE_WRITE=HAZARD_BLOCKED", result.stderr)

    def test_safe_outputs_are_atomic_sourceable_and_mode_bounded(self) -> None:
        safe = measurement(total=4096, available=3000, free_disk=25000)
        with tempfile.TemporaryDirectory(prefix="cyberboss-profile-write-") as temp:
            root = Path(temp)
            fixture = root / "safe.json"
            output = root / "profile.env"
            dropin = root / "20-resource-profile.conf"
            fixture.write_text(json.dumps(safe), encoding="utf-8")
            result = subprocess.run(
                [
                    str(WRAPPER),
                    "--measurements",
                    str(fixture),
                    "--write",
                    str(output),
                    "--systemd-dropin",
                    str(dropin),
                ],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            sourced = subprocess.run(
                [
                    "bash",
                    "-c",
                    'set -a; source "$1"; printf "%s|%s\\n" '
                    '"$CB_RESOURCE_PROFILE" "$CB_RESOURCE_PROTECT_PREDICATE"',
                    "bash",
                    str(output),
                ],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertIn("tiny|available_memory_mb<512", sourced.stdout)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o640)
            self.assertEqual(stat.S_IMODE(dropin.stat().st_mode), 0o644)
            self.assertIn("MemoryMax=1600M", dropin.read_text(encoding="utf-8"))

    def test_clean_shell_check_is_read_only(self) -> None:
        fixture_data = measurement(
            total=4096, available=3000, free_disk=25000
        )
        with tempfile.TemporaryDirectory(prefix="cyberboss-profile-check-") as temp:
            fixture = Path(temp) / "tiny.json"
            fixture.write_text(json.dumps(fixture_data), encoding="utf-8")
            result = subprocess.run(
                [str(WRAPPER), "--measurements", str(fixture), "--check"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertIn("PROFILE_CHECK=PASS", result.stdout)
            self.assertIn("activation_safe=true", result.stdout)


if __name__ == "__main__":
    unittest.main()
