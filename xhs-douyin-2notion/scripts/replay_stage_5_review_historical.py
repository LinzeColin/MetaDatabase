#!/usr/bin/env python3
"""Replay the immutable G5 review on its frozen source tree only.

This prevents Stage 6 changes from being judged by Stage 5's deliberately
current-tree-sensitive verifier. The disposable repository borrows only local
Git objects, creates no worktree, contacts no remote, and never inspects a
private runtime or authentication material.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
FINAL_COMMIT = "34fac27299e1b5599b78456ee825814f456f2df7"
HISTORICAL_VERIFIER = Path("xhs-douyin-2notion/scripts/verify_stage_5_review.py")


class HistoricalReplayError(RuntimeError):
    pass


def _run(command: Sequence[str], *, env: dict[str, str] | None = None, cwd: Path = REPOSITORY_ROOT) -> str:
    result = subprocess.run(
        list(command),
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        if os.environ.get("X2N_HISTORICAL_REPLAY_DEBUG") == "1":
            sys.stderr.write(result.stdout + result.stderr)
        raise HistoricalReplayError("historical Stage 5 review replay failed")
    return result.stdout


def _common_git_dir() -> Path:
    raw = _run(("git", "rev-parse", "--git-common-dir")).strip()
    candidate = Path(raw)
    return candidate if candidate.is_absolute() else (REPOSITORY_ROOT / candidate).resolve()


def _isolated_checkout(root: Path) -> Path:
    checkout = root / "checkout"
    branch = "refs/heads/codex/x2n-historical-stage5-review"
    _run(("git", "init", "--quiet", str(checkout)))
    git_dir = checkout / ".git"
    alternate = git_dir / "objects/info/alternates"
    alternate.parent.mkdir(parents=True, exist_ok=True)
    alternate.write_text(f"{_common_git_dir() / 'objects'}\n", encoding="utf-8")
    _run(("git", "config", "remote.origin.url", "git@github.com:LinzeColin/MetaDatabase.git"), cwd=checkout)
    _run(("git", "update-ref", branch, FINAL_COMMIT), cwd=checkout)
    _run(("git", "symbolic-ref", "HEAD", branch), cwd=checkout)
    _run(("git", "read-tree", FINAL_COMMIT), cwd=checkout)
    _run(("git", "checkout-index", "--all", "--force"), cwd=checkout)
    return checkout


def replay() -> dict[str, Any]:
    _run(("git", "cat-file", "-e", f"{FINAL_COMMIT}^{{commit}}"))
    with tempfile.TemporaryDirectory(prefix="x2n-g5-historical-") as temporary:
        root = Path(temporary)
        checkout = _isolated_checkout(root)
        environment = {
            "HOME": str(root / "home"),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": str(checkout / "xhs-douyin-2notion/apps/companion/src")
            + os.pathsep
            + str(checkout / "xhs-douyin-2notion/packages/contracts/src"),
        }
        Path(environment["HOME"]).mkdir(mode=0o700)
        for key in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE"):
            environment.pop(key, None)
        checked_root = _run(("git", "rev-parse", "--show-toplevel"), env=environment, cwd=checkout).strip()
        if Path(checked_root).resolve() != checkout.resolve():
            raise HistoricalReplayError("historical Stage 5 checkout isolation is invalid")
        verifier = checkout / HISTORICAL_VERIFIER
        if not verifier.is_file():
            raise HistoricalReplayError("historical Stage 5 verifier source is missing")
        output = _run(
            (sys.executable, "-B", str(verifier), "--run-acceptance", "--require-evidence"),
            env=environment,
            cwd=checkout / "xhs-douyin-2notion",
        )
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as error:
        raise HistoricalReplayError("historical Stage 5 verifier output is invalid") from error
    if (
        not isinstance(payload, dict)
        or payload.get("status") != "PASS"
        or payload.get("review_id") != "STG.X2N.5.REVIEW"
    ):
        raise HistoricalReplayError("historical Stage 5 verifier did not pass")
    return {
        "current_stage_6_tree_evaluated": False,
        "historical_commit": FINAL_COMMIT,
        "historical_review": "STG.X2N.5.REVIEW",
        "isolation": "disposable_git_repository_with_alternate_object_store",
        "status": "PASS",
    }


def main() -> int:
    try:
        print(json.dumps(replay(), ensure_ascii=True, sort_keys=True))
    except (OSError, HistoricalReplayError, subprocess.SubprocessError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
