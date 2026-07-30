from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import atomic_json, repo_identity, run


def _tracked_files(repo: Path, path: Path) -> list[str]:
    try:
        relative = path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return []
    result = run(["git", "ls-files", "-z", "--", relative], repo, False)
    return [item for item in result.stdout.split("\0") if item]


def _redacted_identity(identity: dict[str, object]) -> dict[str, object]:
    result = dict(identity)
    dirty = result.pop("dirty", [])
    result["dirty_count"] = len(dirty) if isinstance(dirty, list) else 0
    return result


def _latest_main_state(repo: Path) -> dict[str, object]:
    remote = run(["git", "rev-parse", "--verify", "origin/main"], repo, False)
    if remote.returncode:
        return {"available": False, "head_includes_origin_main": False, "origin_main": None}
    origin_main = remote.stdout.strip()
    ancestor = run(["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"], repo, False).returncode == 0
    return {"available": True, "head_includes_origin_main": ancestor, "origin_main": origin_main}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    findings: list[dict[str, object]] = []
    try:
        if args.fetch:
            run(["git", "fetch", "origin", "main"], repo)
        identity_raw = repo_identity(repo)
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=False))
        return 2

    identity = _redacted_identity(identity_raw)
    remote = str(identity.get("remote") or "")
    if "LinzeColin/MetaDatabase" not in remote and repo.name != "MetaDatabase":
        findings.append({"severity": "P0", "code": "TARGET_IDENTITY_MISMATCH", "message": "目标必须是 LinzeColin/MetaDatabase"})

    latest_main = _latest_main_state(repo)
    if not latest_main["available"]:
        findings.append({"severity": "P0", "code": "ORIGIN_MAIN_UNAVAILABLE", "message": "无法证明分支基于 origin/main；禁止在未知基线执行"})
    elif not latest_main["head_includes_origin_main"]:
        findings.append({"severity": "P0", "code": "STALE_OR_DIVERGED_BASE", "message": "当前 worktree 未包含最新 origin/main；请在一个受控 Run 中先解决基线，不得由任务包静默合并"})

    allowed_reports = {
        ".social-archive-migration/PRECONDITION_REPORT.json",
        ".social-archive-migration/SEMANTIC_CLASSIFICATION.json",
    }
    detailed = run(["git", "status", "--porcelain", "--untracked-files=all"], repo, False).stdout.splitlines()
    blocking = []
    for line in detailed:
        path_text = line[3:] if len(line) >= 4 else line
        if " -> " in path_text or path_text not in allowed_reports or not line.startswith("?? "):
            blocking.append(line)
    if blocking:
        findings.append({
            "severity": "P0",
            "code": "DIRTY_WORKTREE",
            "message": "为保护移动仓库，应用前必须提交或另行备份当前未提交变更；仅允许任务包生成的只读 Stage 0 报告",
            "blocking_count": len(blocking),
            "paths_redacted": True,
        })

    legacy = repo / "xhs-douyin-2notion"
    target = repo / "social-archive"
    for label, path in (("legacy", legacy), ("target", target)):
        if path.is_symlink():
            findings.append({"severity": "P0", "code": f"{label.upper()}_SYMLINK", "message": "项目树不得是符号链接"})

    legacy_tracked = _tracked_files(repo, legacy) if legacy.exists() else []
    target_tracked = _tracked_files(repo, target) if target.exists() else []
    if legacy_tracked and target_tracked:
        findings.append({"severity": "P0", "code": "BOTH_TRACKED_PRODUCT_TREES", "message": "旧目录和新目录同时含有 tracked 产品文件；禁止自动覆盖或形成双产品入口"})

    report = {
        "status": "BLOCKED" if any(item["severity"] == "P0" for item in findings) else "READY",
        "identity": identity,
        "latest_main": latest_main,
        "legacy_exists": legacy.exists(),
        "target_exists": target.exists(),
        "legacy_tracked_file_count": len(legacy_tracked),
        "target_tracked_file_count": len(target_tracked),
        "findings": findings,
    }
    out = repo / ".social-archive-migration/PRECONDITION_REPORT.json"
    atomic_json(out, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
