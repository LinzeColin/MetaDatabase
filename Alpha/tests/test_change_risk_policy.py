"""改风控配置的原子流程(门 #22):要么全做完,要么什么都不留下。"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/change_risk_policy.py"
POLICY = ROOT / "configs/trading_governor_policy.yaml"


def _run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], cwd=ROOT,
                          capture_output=True, text=True, timeout=120)


def test_refuses_change_without_owner_signature():
    """改风控必须同时重签授权;签字只能 owner 给,脚本绝不代拟。"""
    before = POLICY.read_text()
    r = _run("--ratio", "0.95")
    assert r.returncode == 2 and "只能由 owner 给出" in (r.stdout + r.stderr)
    assert POLICY.read_text() == before, "被拒时不得留下任何改动"


def test_refuses_placeholder_signature():
    """占位符签字(含 <)一律拒,防止把模板当成 owner 原话。"""
    before = POLICY.read_text()
    r = _run("--ratio", "0.95", "--sign", "<owner 原话>")
    assert r.returncode == 2
    assert POLICY.read_text() == before


def test_refuses_out_of_range_ratio():
    """比例越界拒改(>1 等于允许超额下单)。"""
    before = POLICY.read_text()
    r = _run("--ratio", "1.5", "--sign", "真实签字")
    assert r.returncode == 2 and "(0,1]" in (r.stdout + r.stderr)
    assert POLICY.read_text() == before


def test_check_mode_reports_and_changes_nothing():
    """体检模式只报告不改动;授权缺失时如实报不一致(不假装健康)。"""
    before = POLICY.read_text()
    r = _run("--check")
    assert "单笔比例(权威)" in r.stdout and "单笔上限" in r.stdout
    assert POLICY.read_text() == before
