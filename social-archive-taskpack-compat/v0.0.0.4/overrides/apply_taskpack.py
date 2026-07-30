from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from common import atomic_json, repo_identity, run, sha, taskpack_root, timestamp
from semantic_classify import (
    ARCHITECTURE_DECISION,
    BLOCKED_DUAL_CORE,
    CONTROLLED_FALLBACK,
    capability_report,
    decide_mode,
)

IDENTITY_FILES = {"AGENTS.md", "README.md", "VERSION", "pyproject.toml"}
REBUILD_PREFIXES = {
    "apps/browser-extension",
    "apps/obsidian-plugin",
    "apps/pwa",
    "deploy",
    "sidecars",
    "scripts",
    "machine",
    "src/social_archive/connectors",
}
REBUILD_FILES = {
    "src/social_archive/__init__.py",
    "src/social_archive/api.py",
    "src/social_archive/config.py",
    "src/social_archive/destinations.py",
    "src/social_archive/downloader.py",
    "src/social_archive/encryption.py",
    "src/social_archive/exports.py",
    "src/social_archive/quota.py",
    "src/social_archive/registry.py",
    "src/social_archive/storage.py",
    "src/social_archive/utils.py",
    "src/social_archive/worker.py",
}
PRESERVED_CORE_FILES = {
    "src/social_archive/db.py",
    "src/social_archive/models.py",
    "src/social_archive/repository.py",
    "src/social_archive/service.py",
    "src/social_archive/sql/runtime_schema.sql",
}
TEXT_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".json", ".yaml", ".yml", ".md", ".toml", ".html", ".css", ".sh", ".sql", ".txt"}
RUNTIME_REPLACEMENTS = (
    ("xhs_douyin_2notion", "social_archive"),
    ("@x2n/", "@social-archive/"),
    ("X2N_", "SOCIAL_ARCHIVE_"),
    ("X2N", "SOCIAL_ARCHIVE"),
    ("x2n", "social_archive"),
    ("XHS Douyin 2 Notion", "Social Archive"),
)
GENERATED_IGNORE_RULES = (
    "/.social-archive-migration/",
    "/.social-archive-candidate-v0.0.0.4/",
)


def is_beneath(path: str, roots: set[str]) -> bool:
    return any(path == root or path.startswith(root + "/") for root in roots)




def blocking_worktree_changes(repo: Path) -> list[str]:
    """Ignore only read-only Stage 0 reports created by this taskpack before recovery."""
    allowed = {
        ".social-archive-migration/PRECONDITION_REPORT.json",
        ".social-archive-migration/SEMANTIC_CLASSIFICATION.json",
    }
    lines = run(["git", "status", "--porcelain", "--untracked-files=all"], repo, False).stdout.splitlines()
    blocked: list[str] = []
    for line in lines:
        path_text = line[3:] if len(line) >= 4 else line
        # Renames use "old -> new" and are never allowed before the recovery point.
        if " -> " in path_text or path_text not in allowed or not line.startswith("?? "):
            blocked.append(line)
    return blocked

def latest_main(repo: Path) -> dict[str, str]:
    """Require a current worktree base without silently merging moving main."""
    run(["git", "fetch", "origin", "main"], repo)
    branch = run(["git", "branch", "--show-current"], repo).stdout.strip()
    head = run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    origin_main = run(["git", "rev-parse", "--verify", "origin/main"], repo, False).stdout.strip()
    if not origin_main:
        raise RuntimeError("origin/main 不可用；禁止在未知基线执行。")
    current = run(["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"], repo, False).returncode == 0
    if not current:
        raise RuntimeError("当前 worktree 未包含最新 origin/main；禁止由任务包静默合并或重写历史。")
    return {"branch": branch, "head": head, "origin_main": origin_main}


def ensure_generated_paths_ignored(repo: Path) -> list[str]:
    gitignore = repo / ".gitignore"
    previous = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    lines = previous.splitlines()
    missing = [rule for rule in GENERATED_IGNORE_RULES if rule not in lines]
    if not missing:
        return []
    prefix = previous if not previous or previous.endswith("\n") else previous + "\n"
    block = "# Social Archive generated migration material; never stage runtime or candidate data.\n" + "\n".join(missing) + "\n"
    gitignore.write_text(prefix + block, encoding="utf-8")
    return missing


def make_recovery(repo: Path, backup: Path, stamp: str) -> dict[str, object]:
    identity = repo_identity(repo)
    blocked = blocking_worktree_changes(repo)
    if blocked:
        raise RuntimeError(
            "目标仓存在非任务包 Stage 0 报告的未提交变更。为避免覆盖最新工作，本脚本不会自动 stash；"
            f"请先提交或备份后重试（blocked_count={len(blocked)}，路径已不回显）。"
        )
    tag = f"social-archive-pre-v0.0.0.4-{stamp.lower()}"
    run(["git", "tag", "-a", tag, "-m", "Recovery point before Social Archive v0.0.0.4"], repo)
    ignored_rules = ensure_generated_paths_ignored(repo)
    backup.mkdir(parents=True, exist_ok=False)
    (backup / "BASE_HEAD.txt").write_text(identity["head"] + "\n", encoding="utf-8")
    return {"tag": tag, "head": identity["head"], "generated_ignore_rules_added": ignored_rules}


def tracked_files(repo: Path, source: Path) -> list[Path]:
    relative = source.resolve().relative_to(repo.resolve()).as_posix()
    result = run(["git", "ls-files", "-z", "--", relative], repo, False)
    return [repo / item for item in result.stdout.split("\0") if item]


def copy_tree_snapshot(repo: Path, source: Path, destination: Path) -> None:
    """Back up tracked source only; ignored runtime material is never copied."""
    if not source.exists():
        return
    for path in tracked_files(repo, source):
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("迁移快照只允许普通 tracked 文件；符号链接或异常路径必须人工处理。")
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def git_move_or_filesystem(repo: Path, source: Path, destination: Path) -> str:
    """Move tracked code only; leave ignored runtime material at its private source."""
    if not source.is_dir() or source.is_symlink():
        raise RuntimeError("目录迁移只允许普通目录；禁止跟随符号链接。")
    if destination.exists():
        raise RuntimeError("目标目录已存在；禁止自动合并两个产品树。")
    tracked = tracked_files(repo, source)
    if not tracked:
        raise RuntimeError("旧产品树没有 tracked 文件；禁止猜测并移动未跟踪或运行时数据。")
    destination.parent.mkdir(parents=True, exist_ok=True)
    for path in tracked:
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("迁移只允许普通 tracked 文件；符号链接或异常路径必须人工处理。")
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        # The active repository is intentionally sparse.  The new product path
        # is outside its initial sparse cone, so ordinary `git mv` refuses the
        # otherwise-safe tracked rename before changing anything.  --sparse is
        # Git's explicit opt-in for this exact move; files remain tracked and
        # ignored runtime material is still never selected by tracked_files().
        run(["git", "mv", "--sparse", "--", path.relative_to(repo).as_posix(), target.relative_to(repo).as_posix()], repo)
    return "git mv tracked files only; ignored runtime retained in place"


def migrate_package_path(repo: Path, target: Path) -> list[dict[str, str]]:
    candidates = [target / "src/x2n", target / "src/xhs_douyin_2notion", target / "apps/companion/src/x2n_companion"]
    existing = [path for path in candidates if path.exists()]
    if len(existing) > 1:
        raise RuntimeError("检测到多个候选事务包；禁止自动猜测权威内核。")
    if existing:
        return [{"from": str(existing[0].relative_to(repo)), "to": "src/social_archive", "method": "deferred_to_SA-003_focused_core_adoption"}]
    return []


def patch_runtime_identifiers(target: Path) -> list[dict[str, str]]:
    # A recursive brand replacement mutates the preserved core and historical
    # contracts.  Product-facing identity comes from the explicit overlay;
    # remaining adapters are renamed only in their bounded SA-003 contract.
    return []


def should_replace(rel_text: str, mode: str) -> bool:
    if rel_text in IDENTITY_FILES:
        return True
    if mode == "ADAPT_CURRENT_UPSTREAM":
        return False
    if mode == CONTROLLED_FALLBACK:
        return True
    return rel_text in REBUILD_FILES or is_beneath(rel_text, REBUILD_PREFIXES)


def apply_overlay(src_root: Path, dst_root: Path, candidate_root: Path, backup_root: Path, mode: str) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    for src in sorted(path for path in src_root.rglob("*") if path.is_file() and not path.is_symlink()):
        rel = src.relative_to(src_root)
        rel_text = rel.as_posix()
        dst = dst_root / rel
        if mode == ARCHITECTURE_DECISION and rel_text in PRESERVED_CORE_FILES:
            candidate = candidate_root / rel
            candidate.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, candidate)
            actions.append({
                "path": rel_text,
                "action": "preserve_core_candidate_requires_focused_proof",
                "candidate": str(candidate.relative_to(dst_root.parent)),
                "current_sha256": sha(dst) if dst.is_file() and not dst.is_symlink() else None,
                "candidate_sha256": sha(src),
            })
            continue
        if dst.is_symlink():
            actions.append({"path": rel_text, "action": "blocked_symlink"})
            continue
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            actions.append({"path": rel_text, "action": "apply_missing", "sha256": sha(src)})
            continue
        if not dst.is_file():
            actions.append({"path": rel_text, "action": "blocked_non_file"})
            continue
        if sha(src) == sha(dst):
            actions.append({"path": rel_text, "action": "satisfied", "sha256": sha(src)})
            continue
        backup = backup_root / "changed-files" / rel
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dst, backup)
        if should_replace(rel_text, mode):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            actions.append({
                "path": rel_text,
                "action": "adapt_replace_product_surface_after_backup",
                "previous_sha256": sha(backup),
                "sha256": sha(src),
            })
        else:
            candidate = candidate_root / rel
            candidate.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, candidate)
            action = "preserve_core_candidate_requires_focused_proof" if rel_text in PRESERVED_CORE_FILES else "adapt_candidate_retain_stronger_upstream_or_preserved_core"
            actions.append({
                "path": rel_text,
                "action": action,
                "candidate": str(candidate.relative_to(dst_root.parent)),
                "current_sha256": sha(dst),
                "candidate_sha256": sha(src),
            })
    return actions



def apply_identity_overlay(src_root: Path, dst_root: Path, backup_root: Path) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    for rel_text in sorted(IDENTITY_FILES):
        src = src_root / rel_text
        if not src.is_file():
            continue
        dst = dst_root / rel_text
        if dst.is_symlink():
            raise RuntimeError(f"身份文件不能是符号链接：{rel_text}")
        if dst.is_file() and sha(src) == sha(dst):
            actions.append({"path": rel_text, "action": "identity_satisfied", "sha256": sha(src)})
            continue
        if dst.exists() and not dst.is_file():
            raise RuntimeError(f"身份路径不是普通文件：{rel_text}")
        if dst.is_file():
            backup = backup_root / "identity-files" / rel_text
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dst, backup)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        actions.append({"path": rel_text, "action": "identity_replace_after_backup", "sha256": sha(src)})
    return actions

def load_session(session_path: Path, repo: Path, phase: str) -> dict[str, object] | None:
    if not session_path.is_file():
        return None
    session = json.loads(session_path.read_text(encoding="utf-8"))
    current = repo_identity(repo)
    if current["head"] != session.get("base_head"):
        raise RuntimeError("已有迁移 Session 的 base HEAD 与当前 HEAD 不一致；请回滚旧 Session 或显式完成后再开始。")
    expected = session.get("status_after_identity") or []
    if phase == "all" and session.get("phase") == "identity" and current["dirty"] != expected:
        raise RuntimeError("identity 阶段后出现额外工作区变更；禁止自动继续。请比较 ACTIVE_SESSION.json 后处理。")
    return session


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely apply Social Archive v0.0.0.4 to a moving MetaDatabase main")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--phase", choices=["all", "identity"], default="all")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    taskpack = taskpack_root()
    migration = repo / ".social-archive-migration"
    session_path = migration / "ACTIVE_SESSION.json"
    session = load_session(session_path, repo, args.phase)

    if session:
        stamp = str(session["stamp"])
        backup = Path(str(session["backup_root"]))
        sync = dict(session["latest_main_sync"])
        recovery = dict(session["recovery"])
        before = dict(session["base_identity"])
    else:
        stamp = timestamp()
        backup = migration / "backups" / stamp
        sync = latest_main(repo)
        recovery = make_recovery(repo, backup, stamp)
        before = repo_identity(repo)
        atomic_json(migration / "BASE_IDENTITY.json", before)

    legacy = repo / "xhs-douyin-2notion"
    target = repo / "social-archive"
    if legacy.exists() and target.exists() and tracked_files(repo, legacy):
        raise RuntimeError("旧目录与新目录同时存在。先运行 semantic_classify.py 并按报告确定唯一权威树。")

    target_caps_before = capability_report(target)
    legacy_caps_before = capability_report(legacy)
    mode = decide_mode(target, legacy, target_caps_before, legacy_caps_before)
    if mode == BLOCKED_DUAL_CORE:
        raise RuntimeError("检测到多个可复用事务核心；禁止迁移或覆盖，必须先完成 SA-003 的单一权威裁决。")

    if not session:
        if target.exists():
            copy_tree_snapshot(repo, target, backup / "target-tree")
        if legacy.exists():
            copy_tree_snapshot(repo, legacy, backup / "legacy-tree-read-only")
        if legacy.exists() and not target.exists():
            method = git_move_or_filesystem(repo, legacy, target)
            move = {"from": "xhs-douyin-2notion", "to": "social-archive", "method": method, "preserved_transaction_core": True, "legacy_role": "read_only_backup_snapshot"}
        elif target.exists():
            move = {"from": None, "to": "social-archive", "retained_current_upstream": True, "legacy_role": None}
        else:
            target.mkdir(parents=True)
            move = {"from": None, "to": "social-archive", "created": True, "legacy_role": None}
        package_moves = migrate_package_path(repo, target)
        identity_actions = apply_identity_overlay(taskpack / "overlay/social-archive", target, backup)
        identity_actions.extend(patch_runtime_identifiers(target))
    else:
        move = dict(session["move"])
        package_moves = list(session.get("package_moves") or [])
        identity_actions = list(session.get("identity_actions") or [])

    candidate_root = repo / ".social-archive-candidate-v0.0.0.4" / "social-archive"
    actions: list[dict[str, object]] = []
    if args.phase == "all":
        actions = apply_overlay(taskpack / "overlay/social-archive", target, candidate_root, backup, mode)
        identity_actions.extend(patch_runtime_identifiers(target))
        root_overlay = taskpack / "overlay/root"
        if root_overlay.exists():
            actions.extend(apply_overlay(root_overlay, repo, repo / ".social-archive-candidate-v0.0.0.4/root", backup / "root", "ADAPT_CURRENT_UPSTREAM"))

    current = repo_identity(repo)
    session_doc = {
        "schema_version": "1.0",
        "stamp": stamp,
        "phase": args.phase,
        "base_head": before["head"],
        "base_identity": before,
        "latest_main_sync": sync,
        "recovery": recovery,
        "backup_root": str(backup),
        "move": move,
        "package_moves": package_moves,
        "identity_actions": identity_actions,
        "semantic_decision": mode,
        "status_after_identity": current["dirty"] if args.phase == "identity" else (session.get("status_after_identity", []) if session else []),
        "status_after_all": current["dirty"] if args.phase == "all" else None,
    }
    atomic_json(session_path, session_doc)

    report = {
        "schema_version": "3.0",
        "status": "APPLIED_WITH_CANDIDATES" if any("candidate" in str(item.get("action")) for item in actions) else "APPLIED",
        "stamp": stamp,
        "phase": args.phase,
        "latest_main_sync": sync,
        "base_identity": before,
        "recovery": recovery,
        "move": move,
        "package_moves": package_moves,
        "semantic_decision": mode,
        "architecture_decision": ARCHITECTURE_DECISION,
        "controlled_fallback": CONTROLLED_FALLBACK,
        "capabilities_before_move_or_overlay": {
            "target": target_caps_before,
            "legacy": legacy_caps_before,
        },
        "asset_adoption_policy": "preserve focused-proven single transaction core; rebuild product shell/connectors; evidence-gated affected-slice fallback",
        "legacy_tree_role": "read-only migration source; proven single transaction core may be preserved, never duplicated",
        "preserved_core_files": sorted(PRESERVED_CORE_FILES),
        "identity_actions": identity_actions,
        "actions": actions,
        "candidate_root": str(candidate_root),
        "preserved_core_proof_command": "python3 -m pytest -q tests/focused/test_core_capture.py tests/focused/test_runtime_store.py tests/focused/test_legacy_migration.py",
        "next_command": f"python3 {taskpack / 'apply/semantic_classify.py'} --repo {repo}",
        "rollback_command": f"python3 {taskpack / 'apply/rollback_taskpack.py'} --repo {repo} --stamp {stamp}",
    }
    atomic_json(migration / "APPLY_REPORT.json", report)
    atomic_json(backup / "MANIFEST.json", report)
    (migration / "ROLLBACK_COMMAND.txt").write_text(report["rollback_command"] + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "stamp", "phase", "semantic_decision", "candidate_root", "rollback_command")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
