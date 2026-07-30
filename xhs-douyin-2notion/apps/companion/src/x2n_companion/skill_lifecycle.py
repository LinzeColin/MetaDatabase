"""Current, copyable source-lifecycle rehearsal for the x2n Skill.

The commands in this module validate a fresh public source tree only. They do
not install a released product, read a Chrome profile, resolve a private
runtime root, or contact a platform, Notion, model provider, or credential.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[4]
TASK_ID = "TSK.x2n.assurance.001"
EXPECTED_EXTENSION_PERMISSIONS = ("activeTab", "nativeMessaging", "scripting", "sidePanel")
REQUIRED_FILES = (
    "SKILL.md",
    "agents/openai.yaml",
    "package.json",
    "package-lock.json",
    "pyproject.toml",
    "uv.lock",
    "apps/extension/manifest.json",
    "apps/extension/scripts/self-test.mjs",
    "apps/extension/scripts/extension-e2e.mjs",
    "apps/companion/pyproject.toml",
    "apps/companion/src/x2n_companion/runtime_cli.py",
    "apps/companion/src/x2n_companion/skill_lifecycle.py",
    "packages/contracts/README.md",
    "packages/test-fixtures/extension/v1/page_cases.json",
)


class SkillLifecycleError(RuntimeError):
    def __init__(self, code: str, safe_message: str, decision_question: str) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.decision_question = decision_question


def _emit(payload: dict[str, Any], *, stream: Any = sys.stdout) -> None:
    stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def _require(condition: bool, code: str, safe_message: str, decision_question: str) -> None:
    if not condition:
        raise SkillLifecycleError(code, safe_message, decision_question)


def _validate_source() -> dict[str, Any]:
    missing = [relative for relative in REQUIRED_FILES if not (PROJECT_ROOT / relative).is_file()]
    _require(
        not missing,
        "X2N_SKILL_SOURCE_INCOMPLETE",
        "The public source lifecycle is incomplete.",
        "是否先恢复受治理的公开源文件后重试？",
    )
    for relative in ("runtime", "downloads", ".x2n-root.json"):
        _require(
            not (PROJECT_ROOT / relative).exists(),
            "X2N_SKILL_RUNTIME_IN_REPOSITORY",
            "Private Runtime must remain outside the repository.",
            "是否先隔离仓库内 Runtime 并完成隐私复核？",
        )
    try:
        manifest = json.loads((PROJECT_ROOT / "apps/extension/manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SkillLifecycleError(
            "X2N_SKILL_EXTENSION_MANIFEST_INVALID",
            "The extension manifest is invalid.",
            "是否恢复受治理的 MV3 manifest 后重试？",
        ) from error
    _require(
        manifest.get("manifest_version") == 3
        and tuple(manifest.get("permissions", ())) == EXPECTED_EXTENSION_PERMISSIONS
        and "host_permissions" not in manifest,
        "X2N_SKILL_EXTENSION_POLICY_DRIFT",
        "The extension permission boundary drifted.",
        "是否恢复受治理的最小权限 MV3 manifest 后重试？",
    )
    skill = (PROJECT_ROOT / "SKILL.md").read_text(encoding="utf-8")
    _require(
        "x2n_companion.skill_lifecycle" in skill and "x2n_companion.scaffold" not in skill,
        "X2N_SKILL_COMMAND_DRIFT",
        "The Skill command surface is stale.",
        "是否同步当前 Skill 命令和 fresh-copy acceptance 后重试？",
    )
    return {
        "extension_host_permissions": 0,
        "extension_permissions": len(EXPECTED_EXTENSION_PERMISSIONS),
        "network_calls": 0,
        "required_files": len(REQUIRED_FILES),
        "runtime_writes": 0,
    }


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
        "X2N_SKILL_TOOL_MISSING",
        "A required local development tool is unavailable.",
        "是否安装缺失的本地开发工具后重试？",
    )
    return capabilities


def _success(action: str, **details: Any) -> dict[str, Any]:
    return {
        "action": action,
        "authorization": "current_public_source_ci_synth_only",
        "platform_calls": 0,
        "product_lifecycle": "REAL_INSTALL_AND_MVP_DEPLOYMENT_NOT_RUN",
        "status": "PASS",
        "task_id": TASK_ID,
        **details,
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    validation = _validate_source()
    if args.action == "install":
        capabilities = _require_tools()
        return _success(
            "source_install_rehearsal",
            capability_count=sum(capabilities.values()),
            install_writes=0,
            **validation,
        )
    if args.action == "self-test":
        _require_tools()
        return _success("source_self_test", **validation)
    if args.action == "canary":
        _require(
            args.synthetic,
            "X2N_SKILL_REAL_CANARY_UNAUTHORIZED",
            "Only the synthetic Skill Canary is authorized.",
            "是否改用 --synthetic，或等待最终 MVP Task 获得真实 Canary 授权？",
        )
        return _success("synthetic_canary", cases=1, **validation)
    if args.action in {"upgrade", "rollback"}:
        _require(
            args.dry_run,
            "X2N_SKILL_LIFECYCLE_WRITE_UNAUTHORIZED",
            "Only a dry-run source lifecycle rehearsal is authorized.",
            "是否添加 --dry-run，或等待最终 MVP Task 的安装/回滚授权？",
        )
        return _success(f"{args.action}_rehearsal", changes=0, **validation)
    if args.action == "diagnose":
        return _success(
            "diagnose",
            capabilities=_tool_capabilities(),
            local_paths_in_output=0,
            private_values_in_output=0,
            **validation,
        )
    if args.action == "uninstall":
        _require(
            args.dry_run and args.retain_data,
            "X2N_SKILL_UNINSTALL_DESTRUCTIVE_UNAUTHORIZED",
            "Source uninstall is dry-run only and must retain data.",
            "是否使用 --dry-run --retain-data，或等待最终 MVP Task 的卸载授权？",
        )
        return _success("uninstall_rehearsal", data_retained=True, files_removed=0, **validation)
    raise SkillLifecycleError(
        "X2N_SKILL_ACTION_UNKNOWN",
        "Unknown Skill lifecycle action.",
        "是否选择 install、self-test、canary、upgrade、rollback、diagnose 或 uninstall？",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="x2n current public-source Skill lifecycle rehearsal")
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
        _emit(run(args))
    except SkillLifecycleError as error:
        _emit(
            {
                "code": error.code,
                "minimum_decision_question": error.decision_question,
                "safe_message": error.safe_message,
                "status": "FAIL_CLOSED",
                "task_id": TASK_ID,
            },
            stream=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
