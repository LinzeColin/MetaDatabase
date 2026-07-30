from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import run


def _select_stamp(backups: Path, stamp: str | None, latest: bool) -> str | None:
    stamps = sorted(path.name for path in backups.iterdir() if path.is_dir()) if backups.exists() else []
    return stamp or (stamps[-1] if latest and stamps else None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--stamp")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--confirm", help="Required exact confirmation for destructive rollback.")
    parser.add_argument("--execute", action="store_true", help="Without this flag the command is a non-mutating rollback plan.")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    backups = repo / ".social-archive-migration/backups"
    stamp = _select_stamp(backups, args.stamp, args.latest)
    if not stamp:
        print(json.dumps({"status": "BLOCKED", "message": "找不到回滚点"}, ensure_ascii=False))
        return 2
    backup = backups / stamp
    manifest = backup / "MANIFEST.json"
    if not manifest.is_file() or manifest.is_symlink():
        print(json.dumps({"status": "BLOCKED", "message": "回滚 manifest 不存在或不安全"}, ensure_ascii=False))
        return 2
    report = json.loads(manifest.read_text(encoding="utf-8"))
    base = str(report["recovery"]["head"])
    expected = f"ROLLBACK_SOCIAL_ARCHIVE_{stamp}"
    dirty = run(["git", "status", "--porcelain"], repo, False).stdout.splitlines()
    plan = {
        "status": "ROLLBACK_PLAN",
        "stamp": stamp,
        "head": base,
        "recovery_tag": report["recovery"]["tag"],
        "dirty_count": len(dirty),
        "requires": {"execute": True, "confirm": expected},
        "will_not_delete_ignored_runtime_data": True,
    }
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if args.confirm != expected:
        print(json.dumps({"status": "BLOCKED", "message": "缺少精确破坏性回滚确认", "expected": expected}, ensure_ascii=False))
        return 2
    if dirty:
        patch = backup / "rollback-preexisting.patch"
        patch.write_text(run(["git", "diff", "--binary"], repo, False).stdout, encoding="utf-8")
    run(["git", "reset", "--hard", base], repo)
    run(["git", "clean", "-fd", "--", "social-archive", "xhs-douyin-2notion", ".social-archive-candidate-v0.0.0.4"], repo, False)
    print(json.dumps({"status": "ROLLED_BACK", "stamp": stamp, "head": base, "recovery_tag": report["recovery"]["tag"], "dirty_patch_saved": bool(dirty)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
