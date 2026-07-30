from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def self_hash(payload):
    body = dict(payload)
    body["receipt_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    return body


class FormalLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.env = os.environ.copy()
        cls.env["PYTHONPATH"] = str(cls.root / "src")

    def run_script(self, script, *args, cwd=None):
        return subprocess.run(
            [os.sys.executable, str(self.root / "scripts" / script), *map(str, args)],
            cwd=cwd or self.root,
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
        )

    def create_review_bundle(self, base: Path):
        subject_sha = "a" * 64
        subject = {"schema_version": "1.0.0", "state": "FROZEN", "subject_sha256": subject_sha, "files": [], "bindings": {}}
        subject_path = base / "SUBJECT_LOCK.json"
        subject_path.write_text(json.dumps(subject))
        review_input = self_hash({"schema_version": "1.0.0", "state": "PASS", "subject_sha256": subject_sha})
        input_path = base / "review_input.json"
        input_path.write_text(json.dumps(review_input, sort_keys=True))
        input_sha = hashlib.sha256(input_path.read_bytes()).hexdigest()
        receipts = base / "receipts"
        receipts.mkdir()
        counts = {
            "VERIFIER": 3,
            "TELEIOSIS_SCOPED": 3,
            "PERSONA_GROUP_SCOPED": 3,
            "PANEL_ROUND_1": 6,
            "PANEL_ROUND_2": 6,
            "SECOND_MODEL": 1,
            "FINAL_INDEPENDENT": 1,
            "FRESH_BUILDER": 1,
        }
        index = 0
        for review_type, count in counts.items():
            for _ in range(count):
                index += 1
                payload = self_hash({
                    "schema_version": "1.0.0",
                    "review_id": f"R-{index:02d}",
                    "review_type": review_type,
                    "subject_sha256": subject_sha,
                    "input_sha256": input_sha,
                    "reviewer_identity": f"reviewer-{index:02d}",
                    "context_isolation": "ISOLATED",
                    "independent_from_builder": True,
                    "provider_run_id": f"run-{index:02d}",
                    "verdict": "PASS",
                    "findings": [],
                })
                (receipts / f"{index:02d}.json").write_text(json.dumps(payload, sort_keys=True))
        return subject_path, input_path, receipts, subject_sha

    def test_review_chain_requires_exact_independent_set(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            subject, review_input, receipts, _ = self.create_review_bundle(base)
            output = base / "review_chain.json"
            result = self.run_script("build_review_chain.py", "--subject-lock", subject, "--review-input", review_input, "--receipts-dir", receipts, "--output", output)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(output.read_text())
            self.assertEqual(payload["state"], "PASS")
            self.assertEqual(payload["receipt_count"], 24)
            # Reusing a provider run must fail closed.
            first = json.loads((receipts / "01.json").read_text())
            second = json.loads((receipts / "02.json").read_text())
            second["provider_run_id"] = first["provider_run_id"]
            second.pop("receipt_sha256")
            second = self_hash(second)
            (receipts / "02.json").write_text(json.dumps(second, sort_keys=True))
            blocked = self.run_script("build_review_chain.py", "--subject-lock", subject, "--review-input", review_input, "--receipts-dir", receipts, "--output", output)
            self.assertEqual(blocked.returncode, 2)
            self.assertIn("DUPLICATE_PROVIDER_RUN_ID", json.loads(output.read_text())["findings"])

    def test_stop_and_freeze_requires_two_no_change_rounds(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            subject_sha = "b" * 64
            subject = base / "SUBJECT_LOCK.json"
            subject.write_text(json.dumps({"state": "FROZEN", "subject_sha256": subject_sha}))
            review = base / "review.json"
            review.write_text(json.dumps(self_hash({"schema_version": "1.0.0", "state": "PASS", "subject_sha256": subject_sha, "open_p0": 0, "open_p1": 0})))
            replay = base / "replay.json"
            replay.write_text(json.dumps(self_hash({"schema_version": "1.0.0", "state": "PASS", "subject_sha256": subject_sha, "frozen_replays_identical": True})))
            rounds = []
            for index in (1, 2):
                path = base / f"round-{index}.json"
                args = ["--round-id", f"round-{index}", "--sequence", str(index), "--subject-sha256", subject_sha, "--new-mechanisms", "0", "--new-p0", "0", "--new-p1", "0", "--developer-burden-deltas", "0"]
                if index == 2:
                    args += ["--previous-receipt", rounds[0]]
                args += ["--output", path]
                result = self.run_script("build_iteration_receipt.py", *args)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                rounds.append(path)
            output = base / "stop.json"
            args = ["--subject-lock", subject, "--review-chain", review, "--replay-comparison", replay, "--round-receipt", rounds[0], "--round-receipt", rounds[1], "--output", output]
            result = self.run_script("build_stop_and_freeze.py", *args)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(output.read_text())
            self.assertEqual(payload["decision"], "STOP_AND_FREEZE")
            self.assertEqual(payload["qualifying_round_count"], 2)
            broken = json.loads(rounds[1].read_text())
            broken["previous_receipt_sha256"] = "0" * 64
            broken.pop("receipt_sha256", None)
            rounds[1].write_text(json.dumps(self_hash(broken), sort_keys=True))
            rejected = self.run_script("build_stop_and_freeze.py", *args)
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("NO_CHANGE_ROUND_CHAIN_BROKEN", json.loads(output.read_text())["findings"])

    def test_formal_gate_fails_closed_when_receipts_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            result = self.run_script("verify_formal_gate.py", "--root", temp)
            self.assertEqual(result.returncode, 2)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["state"], "BLOCKED")
            self.assertFalse(payload["owner_gate_ready"])

    def _reset_to_formal_prepackage_state(self, candidate: Path) -> None:
        state_path = candidate / "CANONICAL_STATE.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["current_phase"] = "REMEDIATION"
        state["scope_state"] = "FROZEN_FOR_PREPACKAGE"
        state["owner_gate"] = {
            "eligible": False,
            "qualifying_no_change_rounds": 0,
            "required_rounds": 2,
        }
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def test_frozen_subject_requires_freeze_receipt_and_manifest_is_stable_after_formal_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            candidate = Path(temp) / "candidate"
            shutil.copytree(self.root, candidate, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "build", "dist", "*.pyc", "*.egg-info"))
            self._reset_to_formal_prepackage_state(candidate)
            upstream = self_hash({
                "schema_version": "1.0.0", "state": "PASS",
                "agent_commit": "a" * 40, "meta_commit": "b" * 40,
                "skill_instance_count": 100, "unique_slug_count": 84, "stock_skill_count": 5,
                "validator_states": {"all": "PASS"}
            })
            upstream_path = candidate / "evidence/upstream/upstream_seal.json"
            upstream_path.parent.mkdir(parents=True, exist_ok=True)
            upstream_path.write_text(json.dumps(upstream, sort_keys=True))
            subject_path = candidate / "SUBJECT_LOCK.json"
            blocked = self.run_script("build_subject_lock.py", "--root", candidate, "--state", "FROZEN", "--output", subject_path, cwd=candidate)
            self.assertNotEqual(blocked.returncode, 0)
            frozen = self.run_script("freeze_candidate_contracts.py", "--root", candidate, "--output", candidate / "evidence/owner_gate/candidate_freeze.json", cwd=candidate)
            self.assertEqual(frozen.returncode, 0, frozen.stdout + frozen.stderr)
            built = self.run_script("build_subject_lock.py", "--root", candidate, "--state", "FROZEN", "--output", subject_path, cwd=candidate)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            manifest = candidate / "MANIFEST.json"
            first = self.run_script("build_manifest.py", "--root", candidate, "--output", manifest, cwd=candidate)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            before = hashlib.sha256(manifest.read_bytes()).hexdigest()
            formal = candidate / "evidence/formal_review/receipts/01.json"
            formal.parent.mkdir(parents=True, exist_ok=True)
            formal.write_text(json.dumps(self_hash({"schema_version": "1.0.0", "state": "PASS"})))
            owner = candidate / "evidence/owner_gate/round-1.json"
            owner.write_text(json.dumps(self_hash({"schema_version": "1.0.0", "state": "PASS"})))
            second = self.run_script("build_manifest.py", "--root", candidate, "--output", manifest, cwd=candidate)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(before, hashlib.sha256(manifest.read_bytes()).hexdigest())
            review_input = candidate / "evidence/formal_review/review_input.json"
            review = self.run_script("build_review_input.py", "--root", candidate, "--output", review_input, cwd=candidate)
            self.assertEqual(review.returncode, 0, review.stdout + review.stderr)
            payload = json.loads(review_input.read_text())
            self.assertIn("freeze_receipt", payload["bindings"])
            self.assertIn("manifest", payload["bindings"])


    def _copy_and_freeze_candidate(self, base: Path) -> Path:
        candidate = base / "candidate"
        shutil.copytree(self.root, candidate, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "build", "dist", "*.pyc", "*.egg-info"))
        self._reset_to_formal_prepackage_state(candidate)
        upstream = self_hash({
            "schema_version": "1.0.0", "state": "PASS",
            "agent_commit": "a" * 40, "meta_commit": "b" * 40,
            "skill_instance_count": 100, "unique_slug_count": 84, "stock_skill_count": 5,
            "validator_states": {"all": "PASS"}
        })
        upstream_path = candidate / "evidence/upstream/upstream_seal.json"
        upstream_path.parent.mkdir(parents=True, exist_ok=True)
        upstream_path.write_text(json.dumps(upstream, sort_keys=True))
        frozen = self.run_script("freeze_candidate_contracts.py", "--root", candidate, "--output", candidate / "evidence/owner_gate/candidate_freeze.json", cwd=candidate)
        self.assertEqual(frozen.returncode, 0, frozen.stdout + frozen.stderr)
        subject = self.run_script("build_subject_lock.py", "--root", candidate, "--state", "FROZEN", "--output", candidate / "SUBJECT_LOCK.json", cwd=candidate)
        self.assertEqual(subject.returncode, 0, subject.stdout + subject.stderr)
        manifest = self.run_script("build_manifest.py", "--root", candidate, "--output", candidate / "MANIFEST.json", cwd=candidate)
        self.assertEqual(manifest.returncode, 0, manifest.stdout + manifest.stderr)
        review = self.run_script("build_review_input.py", "--root", candidate, "--output", candidate / "evidence/formal_review/review_input.json", cwd=candidate)
        self.assertEqual(review.returncode, 0, review.stdout + review.stderr)
        return candidate

    def test_subject_verification_detects_post_freeze_code_and_binding_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            candidate = self._copy_and_freeze_candidate(Path(temp))
            (candidate / "README.md").write_text((candidate / "README.md").read_text() + "\nmutation\n")
            result = self.run_script("verify_formal_gate.py", "--root", candidate, cwd=candidate)
            self.assertEqual(result.returncode, 2)
            payload = json.loads(result.stdout)
            self.assertIn("SUBJECT_FILE_DRIFT:README.md", payload["findings"])
            quant = json.loads((candidate / "evidence/quant/quant_seal.json").read_text())
            quant["limitations"].append("mutated")
            quant.pop("receipt_sha256", None)
            quant = self_hash(quant)
            (candidate / "evidence/quant/quant_seal.json").write_text(json.dumps(quant, sort_keys=True))
            result = self.run_script("verify_formal_gate.py", "--root", candidate, cwd=candidate)
            payload = json.loads(result.stdout)
            self.assertIn("SUBJECT_BINDING_DRIFT:quant", payload["findings"])

    def test_state_transition_requires_frozen_subject_and_review_input(self):
        with tempfile.TemporaryDirectory() as temp:
            candidate = self._copy_and_freeze_candidate(Path(temp))
            output = candidate / "evidence/owner_gate/state_transition_builder_readiness.json"
            result = self.run_script("transition_canonical_state.py", "--root", candidate, "--target", "BUILDER_READINESS", "--output", output, cwd=candidate)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            state = json.loads((candidate / "CANONICAL_STATE.json").read_text())
            self.assertEqual(state["current_phase"], "BUILDER_READINESS")
            duplicate = self.run_script("transition_canonical_state.py", "--root", candidate, "--target", "BUILDER_READINESS", "--output", output, cwd=candidate)
            self.assertNotEqual(duplicate.returncode, 0)

    def test_skill_pass_c_fails_closed_before_owner_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            candidate = self._copy_and_freeze_candidate(Path(temp))
            result = self.run_script("build_skill_pass_c.py", "--root", candidate, "--output", candidate / "evidence/skill_router/pass_c.json", cwd=candidate)
            self.assertEqual(result.returncode, 2)
            payload = json.loads((candidate / "evidence/skill_router/pass_c.json").read_text())
            self.assertEqual(payload["state"], "BLOCKED_NOT_READY")
            self.assertFalse(payload["formal_pass_claimed"])

    def test_formal_orchestration_shells_are_syntax_valid(self):
        for name in ("prepare_formal_candidate.sh", "close_formal_candidate.sh"):
            result = subprocess.run(["bash", "-n", str(self.root / "scripts" / name)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_final_zip_refuses_unapproved_or_unfrozen_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            approval = Path(temp) / "approval.json"
            approval.write_text(json.dumps(self_hash({"schema_version": "1.0.0", "approved": False, "version": "0.0.0.1.40", "subject_sha256": "c" * 64, "scope_summary_sha256": "d" * 64})))
            result = self.run_script("build_final_zip.py", "--root", self.root, "--approval", approval, "--output", Path(temp) / "out.zip")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((Path(temp) / "out.zip").exists())


if __name__ == "__main__":
    unittest.main()
