from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    spec = importlib.util.spec_from_file_location("social_archive_final_verify_test", ROOT / "scripts/final_verify.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_default_final_verify_is_structural_and_does_not_repeat_application_suite(monkeypatch, tmp_path, capsys):
    module = _load_module()
    calls: list[list[str]] = []
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "run", lambda argv: calls.append(argv) or {"argv": argv, "exit_code": 0, "stdout": "", "stderr": ""})

    assert module.main([]) == 0
    report = json.loads((tmp_path / "evidence/final-verification.json").read_text(encoding="utf-8"))

    assert report["status"] == "PASS"
    assert report["suite_mode"] == "structural"
    assert report["application_suite_rerun"] is False
    assert all("pytest" not in command for command in calls)
    assert capsys.readouterr().out.strip() == "PASS"


def test_full_mode_requires_explicit_opt_in(monkeypatch, tmp_path):
    module = _load_module()
    calls: list[list[str]] = []
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "run", lambda argv: calls.append(argv) or {"argv": argv, "exit_code": 0, "stdout": "", "stderr": ""})

    assert module.main(["--full"]) == 0
    report = json.loads((tmp_path / "evidence/final-verification.json").read_text(encoding="utf-8"))

    assert report["suite_mode"] == "explicit_full"
    assert report["application_suite_rerun"] is True
    assert any("pytest" in command for command in calls)
