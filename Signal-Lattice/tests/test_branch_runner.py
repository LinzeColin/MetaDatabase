"""分支隔离运行器：独立子进程/临时目录/受限资源、同一份不可变快照、收据；一个分支崩溃/超时/超内存不影响其他分支；
分支读不到别的分支的输出；快照被改就一个分支都不启动。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import signal_lattice
from signal_lattice import evidence_snapshot as ES
from signal_lattice.branch_runner import BranchSpec, run_branches

SRC = str(Path(signal_lattice.__file__).resolve().parents[1])
TESTS = str(Path(__file__).resolve().parent)
FAKE = "_fake_branches:%s"
SKILLS = {"ok-a": ("0.0.0.7", "a" * 64), "ok-b": ("0.0.0.8", "b" * 64)}


def make_snapshot(directory: Path) -> Path:
    body = {"schema": ES.SCHEMA, "as_of_date": "2026-09-29",
            "universe": {"source_sha256": "u" * 64, "count": 1, "rules": None,
                         "entries": [{"symbol": "AAA", "cik": 1, "name": "A", "market_cap_usd": 1e9}]},
            "data_files": {}, "text_similarity": {}, "market_environment": {"symbols": {}},
            "params": {"ref": "main", "skills": {k: {"skill_id": k, "params_version": v[0], "params_sha256": v[1], "registry_version": "0.0.0.1",
                                                     "active_path": None, "source": "LOCAL"} for k, v in SKILLS.items()}, "findings": []},
            "collection": {}}
    return ES.write_snapshot(body, directory)


def spec(branch_id, fn, **kw):
    return BranchSpec(branch_id, FAKE % fn, kw.pop("verify_data", ()), **{"memory_mb": 1024, "cpu_seconds": 60, "timeout_seconds": 60, **kw})


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sl-runner-test-"))
        self.snapshot = make_snapshot(self.tmp / "snap")
        self.out = self.tmp / "out"
        self.work = self.tmp / "work"
        self.env = {"PYTHONPATH": SRC + os.pathsep + TESTS, "SL_TEST_OUT_DIR": str(self.out)}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_specs(self, specs, **kw):
        env = {**self.env, **kw.pop("extra_env", {})}
        return run_branches(self.snapshot, specs, self.out, work_root=self.work, extra_env=env, log=lambda m: None, **kw)

    def by_id(self, receipts):
        return {r.branch_id: r for r in receipts}

    def read_verdicts(self, receipt):
        return json.loads(Path(receipt.verdicts_file).read_text("utf-8"))

    def test_every_branch_gets_the_same_snapshot_and_a_complete_receipt(self):
        receipts = self.by_id(self.run_specs([spec("ok-a", "ok_branch"), spec("ok-b", "abstain_branch")]))
        digest = json.loads(self.snapshot.read_text("utf-8"))["content_sha256"]
        self.assertEqual({r.snapshot_hash for r in receipts.values()}, {digest})
        a, b = receipts["ok-a"], receipts["ok-b"]
        self.assertEqual((a.status, b.status), ("PASS", "ABSTAIN"))
        self.assertEqual(b.reason, "NOT_BETTER_THAN_BASE_RATE")
        self.assertEqual((a.params_version, a.params_sha256), SKILLS["ok-a"])
        self.assertEqual(a.verdict_counts, {"PASS": 1, "ABSTAIN": 1})
        for r in (a, b):
            self.assertTrue(r.started_at < r.finished_at)
            self.assertEqual(r.exit_code, 0)
            content = Path(r.verdicts_file).read_bytes()
            self.assertEqual(r.verdicts_sha256, hashlib.sha256(content).hexdigest())
            doc = json.loads(content)
            self.assertEqual(doc["snapshot_sha256"], digest)
            self.assertEqual(doc["params"]["params_version"], SKILLS[r.branch_id][0])
            self.assertTrue((self.out / r.branch_id / ("receipt-%s.json" % digest[:12])).is_file())
        self.assertEqual(a.limits["memory_mb"], 1024)

    def test_a_crash_a_hard_exit_and_a_bad_status_do_not_touch_the_other_branches(self):
        specs = [spec("first", "ok_branch"), spec("boom", "crash_branch"), spec("hard-exit", "exit_branch"),
                 spec("bad-status", "bad_status_branch"), spec("last", "ok_branch")]
        receipts = self.by_id(self.run_specs(specs))
        self.assertEqual((receipts["first"].status, receipts["last"].status), ("PASS", "PASS"))
        self.assertEqual(receipts["boom"].status, "FAILED")
        self.assertTrue(receipts["boom"].reason.startswith("CRASH:exit=6"))
        self.assertIn("boom inside branch", receipts["boom"].stderr_tail)
        self.assertEqual((receipts["hard-exit"].status, receipts["hard-exit"].reason), ("FAILED", "CRASH:exit=3"))
        self.assertEqual(receipts["bad-status"].status, "FAILED")
        for failed in ("boom", "hard-exit", "bad-status"):
            self.assertIsNone(receipts[failed].verdicts_file)      # FAILED 的分支没有可用结论落盘
            self.assertIsNone(receipts[failed].verdicts_sha256)

    def test_timeout_kills_the_branch_and_its_process_and_others_still_finish(self):
        pidfile = self.tmp / "pid.txt"
        started = time.time()
        receipts = self.by_id(self.run_specs([spec("slow", "sleep_branch", timeout_seconds=3), spec("after", "ok_branch")],
                                             extra_env={"SL_TEST_PIDFILE": str(pidfile)}))
        self.assertLess(time.time() - started, 30)
        self.assertEqual(receipts["slow"].status, "FAILED")
        self.assertTrue(receipts["slow"].reason.startswith("TIMEOUT:3s"))
        self.assertEqual(receipts["after"].status, "PASS")
        pid = int(pidfile.read_text("utf-8"))
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        with self.assertRaises(ProcessLookupError):                  # 超时后进程确实没了
            os.kill(pid, 0)

    def test_memory_hog_is_killed_and_recorded_failed(self):
        receipts = self.by_id(self.run_specs([spec("hog", "hog_branch", memory_mb=250), spec("after", "ok_branch")]))
        self.assertEqual(receipts["hog"].status, "FAILED")
        self.assertRegex(receipts["hog"].reason, r"^(MEMORY_LIMIT_EXCEEDED|CRASH)")
        self.assertEqual(receipts["after"].status, "PASS")

    def test_cpu_limit_kills_a_busy_loop(self):
        receipts = self.by_id(self.run_specs([spec("busy", "cpu_branch", cpu_seconds=1, timeout_seconds=40)]))
        self.assertEqual(receipts["busy"].status, "FAILED")
        self.assertRegex(receipts["busy"].reason, r"^(CPU_LIMIT_EXCEEDED|CRASH)")

    def test_rlimits_are_applied_inside_the_child(self):
        receipts = self.by_id(self.run_specs([spec("lim", "limits_branch", cpu_seconds=123)]))
        meta = self.read_verdicts(receipts["lim"])["meta"]
        self.assertEqual(meta["cpu"][0], 123)
        self.assertEqual(meta["core"], [0, 0])

    def test_a_branch_cannot_see_another_branchs_output_or_the_parents_environment(self):
        os.environ["SL_SECRET_TOKEN_FOR_TEST"] = "must-not-leak"
        try:
            receipts = self.by_id(self.run_specs([spec("writer", "ok_branch"), spec("spy", "spy_branch")]))
        finally:
            del os.environ["SL_SECRET_TOKEN_FOR_TEST"]
        meta = self.read_verdicts(receipts["spy"])["meta"]
        self.assertEqual(meta["secrets_found"], [])                  # writer 写在自己 cwd 里的文件，spy 在整个工作根下都找不到
        self.assertEqual(meta["sibling_dirs"], [])                   # 别的分支的私有目录此刻不存在
        self.assertEqual(meta["outputs_visible"], [])                # 别的分支的结论此刻也没落盘（所有分支跑完才写 out_dir）
        self.assertNotIn("SL_SECRET_TOKEN_FOR_TEST", meta["env_keys"])
        self.assertEqual(meta["own_files"], ["worker.stderr", "worker.stdout"])      # 私有目录一开始只有运行器给的两个日志文件
        self.assertNotIn("secret-of-ok.txt", meta["own_files"])
        self.assertEqual(meta["cwd_mode"], "0o700")
        self.assertTrue(meta["home_is_private"])
        self.assertEqual(list(self.work.iterdir()), [])              # 所有私有目录都已删除

    def test_parallel_mode_runs_the_same_specs_and_keeps_private_dirs_private(self):
        receipts = self.run_specs([spec("p1", "ok_branch"), spec("p2", "ok_branch"), spec("p3", "crash_branch")], max_parallel=3)
        self.assertEqual([r.status for r in receipts], ["PASS", "PASS", "FAILED"])
        self.assertEqual(list(self.work.iterdir()), [])

    def test_tampered_snapshot_starts_no_branch(self):
        document = json.loads(self.snapshot.read_text("utf-8"))
        document["universe"]["entries"][0]["market_cap_usd"] = 4.9e9
        self.snapshot.write_text(json.dumps(document), "utf-8")
        with self.assertRaises(ES.SnapshotError):
            self.run_specs([spec("ok-a", "ok_branch")])
        self.assertFalse(self.out.exists())

    def test_worker_refuses_a_snapshot_whose_hash_is_not_the_one_it_was_told(self):
        result = subprocess.run(
            [sys.executable, "-m", "signal_lattice.branch_worker", "--branch", "x", "--entry", FAKE % "ok_branch", "--snapshot", str(self.snapshot),
             "--expect-sha", "0" * 64, "--cpu-seconds", "30", "--memory-mb", "512"],
            cwd=str(self.tmp), env={**os.environ, "PYTHONPATH": SRC + os.pathsep + TESTS}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 5)
        self.assertFalse((self.tmp / "verdicts.json").exists())

    def test_pinned_data_files_are_verified_before_the_branch_runs(self):
        data = self.tmp / "data.bin"
        data.write_bytes(b"hello")
        body = json.loads(self.snapshot.read_text("utf-8"))
        for k in ("content_sha256", "generated_at", "run_info"):
            body.pop(k)
        body["data_files"] = {"facts_db": ES.pin_file(data)}
        snapshot = ES.write_snapshot(body, self.tmp / "snap2")
        data.write_bytes(b"HELLO")                                  # 快照之后数据被改
        receipts = run_branches(snapshot, [spec("ok-a", "ok_branch", verify_data=("facts_db",))], self.out, work_root=self.work,
                                extra_env=self.env, log=lambda m: None)
        self.assertEqual((receipts[0].status, receipts[0].reason), ("FAILED", "CRASH:exit=5"))


if __name__ == "__main__":
    unittest.main()
