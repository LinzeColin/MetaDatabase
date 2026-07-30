from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import sys
import tempfile
from pathlib import Path

from . import __version__
from .analysis import analyze
from .io import file_sha256, load_config, load_sessions
from .render import output_inventory, render_outputs
from .validation import verify_output


def _json_print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def cmd_doctor(_: argparse.Namespace) -> int:
    ok = sys.version_info >= (3, 10)
    setuptools_available = importlib.util.find_spec("setuptools") is not None
    _json_print({
        "status": "PASS" if ok else "FAIL",
        "skill": "global-equity-lead-lag-atlas",
        "version": __version__,
        "python": platform.python_version(),
        "python_supported": ok,
        "execution_mode": "zero_install_pythonpath_or_installed",
        "zero_install_supported": ok,
        "required_third_party_runtime_dependencies": [],
        "optional_editable_install": {
            "available_in_current_environment": setuptools_available,
            "build_backend": "setuptools>=61",
            "required_for_core_runtime": False,
        },
        "network_required": False,
        "standalone_service": False,
    })
    return 0 if ok else 2


def cmd_validate(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    config = load_config(config_path)
    markets, warnings = load_sessions(config.input_csv)
    _json_print({
        "status": "PASS" if not warnings else "PASS_WITH_WARNINGS",
        "analysis_id": config.analysis_id,
        "markets": len(markets),
        "sessions": sum(len(value) for value in markets.values()),
        "warnings": warnings,
    })
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    markets, warnings = load_sessions(config.input_csv)
    result = analyze(markets, config)
    output = render_outputs(
        result,
        config,
        input_sha256=file_sha256(config.input_csv),
        config_sha256=file_sha256(config_path),
        input_warnings=warnings,
    )
    verification = verify_output(output)
    if verification["status"] != "PASS":
        _json_print(verification)
        return 3
    _json_print({
        "status": "PASS",
        "output_dir": str(output),
        "counts": result["counts"],
        "inventory": output_inventory(output),
    })
    return 0


def cmd_verify_output(args: argparse.Namespace) -> int:
    result = verify_output(Path(args.output_dir))
    _json_print(result)
    return 0 if result["status"] == "PASS" else 4


def _example_root() -> Path:
    return Path(__file__).resolve().parents[2] / "examples"


def cmd_selftest(_: argparse.Namespace) -> int:
    example = _example_root()
    config_path = example / "config.selftest.json"
    if not config_path.is_file():
        _json_print({"status": "FAIL", "error": f"缺少自检配置: {config_path}"})
        return 5
    with tempfile.TemporaryDirectory(prefix="gela-selftest-") as temp:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        source_input = example / data["input_csv"]
        temp_root = Path(temp)
        temp_input = temp_root / "input.csv"
        shutil.copy2(source_input, temp_input)
        data["input_csv"] = "input.csv"
        data["output_dir"] = "out"
        temp_config = temp_root / "config.json"
        temp_config.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        config = load_config(temp_config)
        markets, warnings = load_sessions(config.input_csv)
        result = analyze(markets, config)
        render_outputs(result, config, file_sha256(config.input_csv), file_sha256(temp_config), warnings)
        verified = verify_output(config.output_dir)
        a_b_correlation = [
            item for item in result["confirmed_co_movements"]
            if item["market_a"] == "SYN_A" and item["market_b"] == "SYN_B" and item["horizon"] == 1
        ]
        a_to_b = [
            edge for edge in result["confirmed_edges"]
            if edge["source_market"] == "SYN_A" and edge["target_market"] == "SYN_B" and edge["horizon"] == 1
        ]
        b_to_a = [
            edge for edge in result["confirmed_edges"]
            if edge["source_market"] == "SYN_B" and edge["target_market"] == "SYN_A" and edge["horizon"] == 1
        ]
        errors: list[str] = []
        if verified["status"] != "PASS":
            errors.extend(verified["errors"])
        if not a_b_correlation:
            errors.append("未识别预置 SYN_A ↔ SYN_B 同期相关")
        if not a_to_b:
            errors.append("未识别预置 SYN_A → SYN_B 关系")
        if b_to_a:
            errors.append("错误识别 SYN_B → SYN_A 关系")
        status = "PASS" if not errors else "FAIL"
        _json_print({
            "status": status,
            "expected_correlation_found": bool(a_b_correlation),
            "expected_edge_found": bool(a_to_b),
            "reverse_false_positive": bool(b_to_a),
            "counts": result["counts"],
            "errors": errors,
        })
        return 0 if status == "PASS" else 6


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="gela", description="全球股市时序联动图谱")
    commands = root.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="检查运行环境")
    doctor.set_defaults(func=cmd_doctor)
    validate = commands.add_parser("validate", help="验证配置与输入")
    validate.add_argument("--config", required=True)
    validate.set_defaults(func=cmd_validate)
    analyze_command = commands.add_parser("analyze", help="运行分析并生成制品")
    analyze_command.add_argument("--config", required=True)
    analyze_command.set_defaults(func=cmd_analyze)
    verify = commands.add_parser("verify-output", help="复验输出完整性")
    verify.add_argument("output_dir")
    verify.set_defaults(func=cmd_verify_output)
    selftest = commands.add_parser("selftest", help="运行确定性合成自检")
    selftest.set_defaults(func=cmd_selftest)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        _json_print({"status": "FAIL", "error": str(exc)})
        return 2
