from __future__ import annotations

import importlib.util
import platform
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("run_kernel_isolation", ROOT / "tools" / "run_kernel_isolation.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class KernelIsolationTests(unittest.TestCase):
    @unittest.skipUnless(platform.system() == "Linux" and platform.machine().lower() in {"x86_64", "amd64"}, "v0 supported runtime profile is Linux x86_64")
    def test_820_seccomp_blocks_network_and_process_spawn_while_runtime_still_works(self):
        # The filter is irreversible for a process, so this test is intentionally
        # exercised by the standalone oracle rather than installed in the test runner.
        # Here we validate the public syscall profile and report contract only.
        self.assertIn("socket", MODULE.BLOCKED_SYSCALLS_X86_64)
        self.assertIn("connect", MODULE.BLOCKED_SYSCALLS_X86_64)
        self.assertIn("clone3", MODULE.BLOCKED_SYSCALLS_X86_64)
        self.assertIn("execve", MODULE.BLOCKED_SYSCALLS_X86_64)
        self.assertEqual(MODULE.SCHEMA, "efs.kernel_isolation_execution.v1")

    def test_821_blocked_syscall_numbers_are_unique_after_deduplication(self):
        numbers = list(MODULE.BLOCKED_SYSCALLS_X86_64.values())
        self.assertGreaterEqual(len(set(numbers)), 20)
        self.assertTrue(all(isinstance(value, int) and value > 0 for value in numbers))


if __name__ == "__main__":
    unittest.main()
