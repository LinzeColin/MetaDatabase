#!/usr/bin/env python3
"""Re-accept all Stage 3 tasks without overstating G3 or real execution."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REVIEW_ID = "STG.X2N.3.REVIEW"
RUN_ID = "RUN-X2N-S03-REVIEW"
TASK_RUNNERS = (
    ("TSK.x2n.adapters.001", "run_adapters_001_acceptance.py"),
    ("TSK.x2n.adapters.002", "run_adapters_002_acceptance.py"),
    ("TSK.x2n.adapters.003", "run_adapters_003_acceptance.py"),
    ("TSK.x2n.adapters.004", "run_adapters_004_acceptance.py"),
    ("TSK.x2n.adapters.006", "run_adapters_006_acceptance.py"),
    ("TSK.x2n.adapters.007", "run_adapters_007_acceptance.py"),
    ("TSK.x2n.adapters.008", "run_adapters_008_acceptance.py"),
    ("TSK.x2n.adapters.009", "run_adapters_009_acceptance.py"),
    ("TSK.x2n.adapters.005", "run_adapters_005_acceptance.py"),
)
CANARY_SCOPES = (
    "xiaohongshu_favorites",
    "xiaohongshu_likes",
    "douyin_favorites",
    "douyin_likes",
    "bilibili_selected_collection",
    "kuaishou_selected_collection",
    "weibo_selected_collection",
    "taobao_selected_collection",
)


class ReviewAcceptanceError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReviewAcceptanceError(message)


def _safe_environment(home: Path) -> dict[str, str]:
    environment = {
        "HOME": os.environ.get("HOME", ""),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": "apps/companion/src:packages/contracts/src",
        "TMPDIR": str(home),
    }
    browser_cache = PROJECT_ROOT / "build/playwright-browsers"
    if browser_cache.is_dir():
        environment["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_cache)
    return environment


def _parse_payload(stdout: str, task_id: str) -> dict[str, Any]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    _require(bool(lines), f"{task_id} acceptance emitted no report")
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError:
        raise ReviewAcceptanceError(f"{task_id} acceptance report is not JSON") from None
    _require(isinstance(payload, dict), f"{task_id} acceptance report is not an object")
    _require(payload.get("task_id") == task_id, f"{task_id} acceptance identity drifted")
    _require(
        str(payload.get("status", "")).startswith("PASS_CI_SYNTH"),
        f"{task_id} acceptance did not pass its CI-synthetic scope",
    )
    _require(payload.get("real_account_execution") == "NOT_RUN", f"{task_id} overstated real execution")
    platform_calls = payload.get("platform_calls", 0)
    _require(platform_calls in {0, "NOT_RUN"}, f"{task_id} made or overstated platform calls")
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    forbidden = (
        "/" + "Users/",
        "/" + "home/",
        "github" + "_pat_",
        "ghp" + "_",
        "xhs" + "cdn",
        "douyin" + "vod",
        "byte" + "img",
        "bili" + "video",
        "ks" + "cdn",
        "ali" + "cdn",
    )
    _require(not any(value.lower() in rendered.lower() for value in forbidden), f"{task_id} report is not public-safe")
    return payload


def _run_task(task_id: str, script_name: str, *, home: Path) -> tuple[dict[str, Any], str]:
    result = subprocess.run(
        [sys.executable, "-B", str(PROJECT_ROOT / "scripts" / script_name)],
        cwd=PROJECT_ROOT,
        env=_safe_environment(home),
        check=False,
        capture_output=True,
        text=True,
        timeout=360,
    )
    _require(result.returncode == 0, f"{task_id} acceptance failed")
    payload = _parse_payload(result.stdout, task_id)
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    return payload, digest


def _technical_blockers() -> list[dict[str, str]]:
    service_worker = (PROJECT_ROOT / "apps/extension/src/service-worker.js").read_text(encoding="utf-8")
    sidepanel = (PROJECT_ROOT / "apps/extension/sidepanel.html").read_text(encoding="utf-8")
    native_host = (PROJECT_ROOT / "apps/companion/src/x2n_companion/native_host.py").read_text(encoding="utf-8")
    blockers: list[dict[str, str]] = []
    if "X2N_START_SYNC" not in service_worker:
        blockers.append(
            {
                "id": "BLK-X2N-S03-NATIVE-DISPATCH",
                "kind": "technical",
                "status": "OPEN",
            }
        )
    if "native_sync_skeleton" in native_host or 'id="sync-button" disabled' in sidepanel:
        blockers.append(
            {
                "id": "BLK-X2N-S03-EXPLICIT-FALLBACK",
                "kind": "technical",
                "status": "OPEN",
            }
        )
    _require(len(blockers) == 2, "Stage 3 technical blocker inventory drifted")
    return blockers


def run() -> dict[str, Any]:
    reports: dict[str, dict[str, Any]] = {}
    digests: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="x2n-s03-review-acceptance-") as value:
        home = Path(value) / "home"
        home.mkdir(mode=0o700)
        for task_id, script_name in TASK_RUNNERS:
            reports[task_id], digests[task_id] = _run_task(task_id, script_name, home=home)

    a005 = reports["TSK.x2n.adapters.005"]
    cross_layer = a005.get("cross_layer", {})
    _require(
        cross_layer.get("content_count") == 80
        and cross_layer.get("artifact_count") == 80
        and cross_layer.get("markdown_files") == 80
        and cross_layer.get("notion_mock_pages") == 80
        and cross_layer.get("sink_receipts") == 160
        and cross_layer.get("artifact_duplicate_count") == 0
        and cross_layer.get("markdown_duplicate_count") == 0
        and cross_layer.get("notion_duplicate_page_count") == 0
        and cross_layer.get("notion_replay_requests") == 0
        and cross_layer.get("cdn_or_private_path_findings") == 0,
        "Stage 3 cross-layer idempotency did not close",
    )
    a004 = reports["TSK.x2n.adapters.004"]
    _require(
        a004.get("chaos", {}).get("kill_runs") == 50,
        "Douyin process-kill recovery evidence is missing",
    )
    blockers = _technical_blockers()
    canaries = [{"execution": "NOT_RUN", "scope_id": scope} for scope in CANARY_SCOPES]
    return {
        "automated_reacceptance": "PASS",
        "canaries": canaries,
        "external_execution": {
            "media_processing": "NOT_RUN",
            "model_calls": 0,
            "notion_real_calls": 0,
            "owner_profile_login": "NOT_RUN",
            "platform_calls": 0,
            "real_accounts": 0,
        },
        "g3_eligible": False,
        "g3_status": "BLOCKED_TECHNICAL_AND_OWNER_CLARIFICATION",
        "review_id": REVIEW_ID,
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "status": "PASS_LOCAL_REACCEPTANCE_G3_BLOCKED",
        "task_reports": [
            {
                "acceptance_report_sha256": digests[task_id],
                "status": reports[task_id]["status"],
                "task_id": task_id,
                "unit_tests": reports[task_id].get("unit_suite", {}).get("tests", 0),
            }
            for task_id, _script_name in TASK_RUNNERS
        ],
        "technical_blockers": blockers,
        "verified_cross_layer": {
            "artifacts": cross_layer["artifact_count"],
            "canonical": cross_layer["content_count"],
            "cdn_or_private_path_findings": cross_layer["cdn_or_private_path_findings"],
            "markdown": cross_layer["markdown_files"],
            "notion_mock_pages": cross_layer["notion_mock_pages"],
            "outbox_receipts": cross_layer["sink_receipts"],
            "replay_duplicates": 0,
        },
    }


def main() -> int:
    try:
        report = run()
    except (OSError, ReviewAcceptanceError, subprocess.TimeoutExpired) as error:
        print(
            json.dumps(
                {
                    "reason": str(error),
                    "review_id": REVIEW_ID,
                    "status": "FAIL_CLOSED",
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
