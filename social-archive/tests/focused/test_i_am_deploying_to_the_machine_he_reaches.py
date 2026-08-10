r"""部署之前必须证明「我要部署的这台就是他打得到的那台」（2026-08-10）。

## 从哪来

一天里三次部署、三次「回读生产全绿」，**三次都没到他手上**：

    从 Owner 的 Mac 打公开域名 → 0.0.0.25，disk.total 95.82G
    ssh 到部署目标上打回环     → 0.0.0.27，disk.total 38.00G

同一个域名两台机器。全套验收（第 7 / 8 / 8.5 步）**都站在被测机器上**，
对这件事结构上就是瞎的。

## 这条判据钉什么

`check_i_am_deploying_to_the_machine_he_reaches.py` 的判断本身：
用 `disk.total_gb` 当机器指纹（版本号可以一样地旧，盘不会恰好一样大），
两边不等就必须拦下，而且**任何一侧读不到都算拦下**——
「判不了」不许当成「那就是同一台」。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/check_i_am_deploying_to_the_machine_he_reaches.py"


def _module():
    spec = importlib.util.spec_from_file_location("machine_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _health(total_gb: float | None, version: str) -> dict:
    disk = {"total_gb": total_gb} if total_gb is not None else {}
    return {"version": version, "disk": disk}


def _run(monkeypatch, capsys, outside, inside) -> tuple[int, dict]:
    module = _module()
    monkeypatch.setattr(module, "_public_health",
                        lambda base: outside() if callable(outside) else outside)
    monkeypatch.setattr(module, "_target_health",
                        lambda host, port: inside() if callable(inside) else inside)
    monkeypatch.setattr(sys, "argv", ["check"])
    code = module.main()
    return code, json.loads(capsys.readouterr().out)


def test_the_real_incident_is_caught(monkeypatch, capsys) -> None:
    """今天这场的真实数字：95.82G vs 38.00G。"""
    code, report = _run(monkeypatch, capsys,
                        _health(95.82, "0.0.0.25"), _health(38.00, "0.0.0.27"))
    assert code == 1, report
    assert report["error_code"] == "TWO_DIFFERENT_MACHINES", report
    assert "95.82" in report["message_zh"] and "38.0" in report["message_zh"], report


def test_same_machine_passes_even_with_different_versions(monkeypatch, capsys) -> None:
    """**部署前两边版本本来就不一样**——不能拿版本当判据，只看机器指纹。"""
    code, report = _run(monkeypatch, capsys,
                        _health(38.00, "0.0.0.25"), _health(38.00, "0.0.0.27"))
    assert code == 0, report
    assert report["status"] == "PASS", report


def test_missing_fingerprint_is_not_a_pass(monkeypatch, capsys) -> None:
    """**取不到指纹不等于同一台。** 空默认值吞掉「不知道」是这个仓的老毛病。"""
    code, report = _run(monkeypatch, capsys,
                        _health(None, "0.0.0.25"), _health(38.00, "0.0.0.27"))
    assert code == 2, report
    assert report["error_code"] == "NO_FINGERPRINT", report


@pytest.mark.parametrize("side", ["public", "target"])
def test_either_side_unreachable_is_a_fail(monkeypatch, capsys, side: str) -> None:
    def boom():
        raise RuntimeError("连不上")
    code, report = _run(
        monkeypatch, capsys,
        boom if side == "public" else _health(38.0, "0.0.0.25"),
        boom if side == "target" else _health(38.0, "0.0.0.27"))
    assert code == 2, report
    assert report["error_code"] in {"PUBLIC_UNREACHABLE", "TARGET_UNREACHABLE"}, report


def test_the_deploy_actually_calls_it() -> None:
    """**建好了没接上**——这个仓栽过六次以上。"""
    deploy = (ROOT / "scripts/deploy_to_production.sh").read_text(encoding="utf-8")
    assert "check_i_am_deploying_to_the_machine_he_reaches.py" in deploy, (
        "部署没有调用这条判据——那它就只是一个躺在 scripts/ 里的文件")
    # 必须排在**构建之前**：建完了才发现部署错机器，那一趟全白跑
    called_at = deploy.index("check_i_am_deploying_to_the_machine_he_reaches.py")
    build_at = deploy.index('step "5) 构建并上线"')
    assert called_at < build_at, "这条判据排在构建之后了——白建一次镜像才发现部署错了机器"
