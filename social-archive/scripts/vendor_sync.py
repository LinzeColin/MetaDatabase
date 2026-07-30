from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "machine" / "third_party_lock.json"
SAFE_ID = re.compile(r"^[a-z0-9_][a-z0-9_-]{0,79}$")
VENDOR_DIRECTORY_NAMES = {
    "xhs_downloader": "XHS-Downloader",
    "ks_downloader": "KS-Downloader",
    "douk": "TikTokDownloader",
}


def _public_git_environment() -> dict[str, str]:
    """Return an isolated, non-interactive Git environment for public sources."""
    environment = os.environ.copy()
    for key in tuple(environment):
        if key == "GIT_CONFIG_COUNT" or key.startswith("GIT_CONFIG_KEY_") or key.startswith("GIT_CONFIG_VALUE_"):
            environment.pop(key)
    environment["GIT_CONFIG_GLOBAL"] = os.devnull
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment.pop("GIT_ASKPASS", None)
    environment.pop("SSH_ASKPASS", None)
    return environment


def run(argv: list[str], cwd: Path | None = None, *, environment: dict[str, str] | None = None) -> str:
    process = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False, env=environment)
    if process.returncode:
        raise RuntimeError(f"command failed {argv}: {process.stderr[-1000:]}")
    return process.stdout.strip()


def _entries(document: Any) -> list[dict[str, Any]]:
    entries = document.get("entries") if isinstance(document, dict) else document
    if not isinstance(entries, list) or not all(isinstance(item, dict) for item in entries):
        raise RuntimeError("third_party_lock.json 必须包含 entries 数组")
    return entries


def _is_public_github_repository(value: object) -> bool:
    parsed = urlsplit(str(value or ""))
    return parsed.scheme == "https" and parsed.hostname == "github.com" and not parsed.username and not parsed.password


def _validate_entry(item: dict[str, Any]) -> None:
    source_id = str(item.get("id") or "")
    repository = str(item.get("repository") or "")
    commit = str(item.get("commit") or "")
    boundary = str(item.get("boundary") or "").upper()
    if not SAFE_ID.fullmatch(source_id):
        raise RuntimeError(f"不安全来源 id：{source_id!r}")
    if not _is_public_github_repository(repository):
        raise RuntimeError(f"{source_id}: 只允许无凭证的公开 GitHub HTTPS 来源")
    if not re.fullmatch(r"[0-9a-fA-F]{7,64}", commit):
        raise RuntimeError(f"{source_id}: 缺少固定 commit，拒绝浮动来源")
    if "SIDECAR" not in boundary:
        raise RuntimeError(f"{source_id}: 第三方来源必须保持 Sidecar 边界")
    if not str(item.get("license") or "").strip():
        raise RuntimeError(f"{source_id}: 缺少许可证信息")


def _select(entries: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    by_id = {str(item.get("id") or ""): item for item in entries}
    if args.source:
        unknown = [source_id for source_id in args.source if source_id not in by_id]
        if unknown:
            raise RuntimeError(f"未知 vendor source：{', '.join(unknown)}")
        selected = [by_id[source_id] for source_id in dict.fromkeys(args.source)]
    elif args.enabled_defaults:
        selected = [item for item in entries if item.get("default_enabled") and _is_public_github_repository(item.get("repository"))]
    else:
        selected = [item for item in entries if _is_public_github_repository(item.get("repository"))]
    if not selected:
        raise RuntimeError("没有可解析的公开 Sidecar 来源")
    for item in selected:
        _validate_entry(item)
    return selected


def _destination(source_id: str) -> Path:
    name = VENDOR_DIRECTORY_NAMES.get(source_id, source_id)
    root = (ROOT / "runtime" / "vendors").resolve()
    destination = (root / name).resolve()
    if destination == root or root not in destination.parents:
        raise RuntimeError(f"vendor 路径越界：{source_id}")
    return destination


def _resolve_and_lock(item: dict[str, Any], checkout: bool) -> dict[str, Any]:
    source_id = str(item["id"])
    repository = str(item["repository"])
    requested_ref = str(item["commit"]).lower()
    destination = _destination(source_id)
    git_environment = _public_git_environment()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not (destination / ".git").exists():
        raise RuntimeError(f"{source_id}: 既有 vendor 目录不是 Git 工作树，拒绝覆盖：{destination}")
    if not destination.exists():
        run(["git", "clone", "--filter=blob:none", "--no-checkout", repository, str(destination)], environment=git_environment)
    run(["git", "fetch", "--tags", "--force", "origin"], destination, environment=git_environment)
    resolved_commit = run(
        ["git", "rev-parse", "--verify", f"{requested_ref}^{{commit}}"],
        destination,
        environment=git_environment,
    ).lower()
    if not resolved_commit.startswith(requested_ref):
        raise RuntimeError(f"{source_id}: 已解析 commit 不匹配锁定前缀")
    if checkout:
        run(["git", "checkout", "--detach", resolved_commit], destination, environment=git_environment)
    return {
        "id": source_id,
        "repository": repository,
        "requested_ref": requested_ref,
        "resolved_commit": resolved_commit,
        "license": item["license"],
        "boundary": item["boundary"],
        "working_tree": str(destination.relative_to(ROOT)),
        "checkout": "detached" if checkout else "not_checked_out",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", action="append", metavar="SOURCE")
    parser.add_argument("--resolve-and-lock", action="store_true")
    parser.add_argument("--resolve-only", action="store_true")
    parser.add_argument("--enabled-defaults", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if args.resolve_and_lock and args.resolve_only:
        parser.error("--resolve-and-lock 与 --resolve-only 不能同时使用")
    if args.source and (args.enabled_defaults or args.all):
        parser.error("--source 不能与 --enabled-defaults 或 --all 同时使用")

    document = json.loads(LOCK.read_text(encoding="utf-8"))
    selected = _select(_entries(document), args)
    resolved = [_resolve_and_lock(item, checkout=not args.resolve_only) for item in selected]
    output = ROOT / "runtime" / "vendor-resolved.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"schema_version": "1.0", "projects": resolved}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"resolved": len(resolved), "sources": [item["id"] for item in resolved], "output": str(output.relative_to(ROOT))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Vendor 解析失败：{exc}", file=sys.stderr)
        raise SystemExit(2)
