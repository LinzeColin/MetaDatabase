"""Network-free lifecycle rehearsal for TSK.x2n.foundation.001.

This module intentionally implements no server, browser IPC, database, source
adapter, model provider, media handling, or external sink.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[4]
TASK_ID = "TSK.x2n.foundation.001"


class ScaffoldError(RuntimeError):
    def __init__(self, code: str, safe_message: str, decision_question: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.decision_question = decision_question


def _emit(payload: dict[str, Any], *, stream: Any = sys.stdout) -> None:
    stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _require(condition: bool, code: str, safe_message: str, decision_question: str) -> None:
    if not condition:
        raise ScaffoldError(code, safe_message, decision_question)


def _validate_scaffold() -> dict[str, Any]:
    required = (
        "SKILL.md",
        "agents/openai.yaml",
        "package.json",
        "pyproject.toml",
        "apps/extension/manifest.json",
        "apps/companion/pyproject.toml",
        "packages/contracts/README.md",
        "packages/test-fixtures/scaffold_case.json",
    )
    missing = [relative for relative in required if not (PROJECT_ROOT / relative).is_file()]
    _require(
        not missing,
        "X2N_SCAFFOLD_FILE_MISSING",
        "Scaffold source is incomplete.",
        "是否恢复缺失的受治理 scaffold 文件后重试？",
    )
    for relative in ("runtime", "downloads", ".x2n-root.json"):
        _require(
            not (PROJECT_ROOT / relative).exists(),
            "X2N_RUNTIME_INSIDE_REPOSITORY",
            "Private Runtime must remain outside the repository.",
            "是否先把仓库内 Runtime 隔离并完成隐私复核？",
        )

    manifest = json.loads((PROJECT_ROOT / "apps/extension/manifest.json").read_text(encoding="utf-8"))
    _require(
        manifest.get("manifest_version") == 3
        and manifest.get("permissions") == []
        and "host_permissions" not in manifest,
        "X2N_EXTENSION_PERMISSION_DRIFT",
        "The foundation extension must remain permission-free.",
        "是否恢复无权限 manifest 并把浏览器能力留给后续 Task？",
    )
    fixture = json.loads(
        (PROJECT_ROOT / "packages/test-fixtures/scaffold_case.json").read_text(encoding="utf-8")
    )
    _require(
        fixture.get("synthetic_only") is True
        and fixture.get("real_account") is False
        and fixture.get("contains_credentials") is False
        and fixture.get("contains_media_urls") is False,
        "X2N_FIXTURE_NOT_SYNTHETIC",
        "The scaffold fixture is not public-safe.",
        "是否用已登记的纯合成 fixture 替换该输入？",
    )
    return {"required_files": len(required), "runtime_writes": 0, "network_calls": 0}


def _tool_capabilities() -> dict[str, bool]:
    return {
        "node": shutil.which("node") is not None,
        "npm": shutil.which("npm") is not None,
        "python_3_12": sys.version_info >= (3, 12),
        "uv": shutil.which("uv") is not None,
    }


def _require_tools() -> dict[str, bool]:
    capabilities = _tool_capabilities()
    _require(
        all(capabilities.values()),
        "X2N_SCAFFOLD_TOOL_MISSING",
        "A required local scaffold tool is unavailable.",
        "是否安装缺失的本地构建工具后重试？",
    )
    return capabilities


def _success(action: str, **details: Any) -> dict[str, Any]:
    return {
        "action": action,
        "authorization": "synthetic_scaffold_only",
        "product_lifecycle": "DOWNSTREAM_NOT_RUN",
        "status": "PASS",
        "task_id": TASK_ID,
        **details,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    validation = _validate_scaffold()
    if args.action == "install":
        capabilities = _require_tools()
        return _success(
            "install_rehearsal",
            capability_count=sum(capabilities.values()),
            install_writes=0,
            **validation,
        )
    if args.action == "self-test":
        _require_tools()
        return _success("self_test", **validation)
    if args.action == "canary":
        _require(
            args.synthetic,
            "X2N_REAL_CANARY_UNAUTHORIZED",
            "Only the synthetic scaffold Canary is authorized.",
            "是否改用 --synthetic，或等待真实 Canary Task 获得授权？",
        )
        return _success("synthetic_canary", cases=1, **validation)
    if args.action in {"upgrade", "rollback"}:
        _require(
            args.dry_run,
            "X2N_LIFECYCLE_WRITE_UNAUTHORIZED",
            "Only a dry-run lifecycle rehearsal is authorized.",
            "是否添加 --dry-run，或等待迁移与回滚 Task？",
        )
        return _success(f"{args.action}_rehearsal", changes=0, **validation)
    if args.action == "diagnose":
        capabilities = _tool_capabilities()
        return _success(
            "diagnose",
            capabilities=capabilities,
            local_paths_in_output=0,
            private_values_in_output=0,
            **validation,
        )
    if args.action == "uninstall":
        _require(
            args.dry_run and args.retain_data,
            "X2N_UNINSTALL_DESTRUCTIVE_UNAUTHORIZED",
            "Scaffold uninstall is dry-run only and must retain data.",
            "是否使用 --dry-run --retain-data，或等待卸载与数据保留 Task？",
        )
        return _success("uninstall_rehearsal", files_removed=0, data_retained=True, **validation)
    raise ScaffoldError(
        "X2N_SCAFFOLD_ACTION_UNKNOWN",
        "Unknown scaffold action.",
        "是否选择 install、self-test、canary、upgrade、rollback、diagnose 或 uninstall？",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="x2n governed scaffold lifecycle rehearsal")
    parser.add_argument(
        "action",
        choices=("install", "self-test", "canary", "upgrade", "rollback", "diagnose", "uninstall"),
    )
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--retain-data", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = run(args)
    except ScaffoldError as exc:
        _emit(
            {
                "code": exc.code,
                "minimum_decision_question": exc.decision_question,
                "safe_message": exc.safe_message,
                "status": "FAIL_CLOSED",
                "task_id": TASK_ID,
            },
            stream=sys.stderr,
        )
        return 2
    _emit(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
