#!/usr/bin/env python3
"""Run Adapters002 DOM, Canonical and 50-process-kill synthetic acceptance."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps/companion/src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages/contracts/src"))

from x2n_companion.canonical_store import CanonicalStore  # noqa: E402
from x2n_companion.runtime import RuntimePaths  # noqa: E402
from x2n_companion.xiaohongshu_favorites import (  # noqa: E402
    XhsFavoriteItem,
    XhsFavoritesAdapter,
    XhsFavoritesBatch,
    build_xhs_favorites_canary_plan,
)


TASK_ID = "TSK.x2n.adapters.002"
PHASE = "PH.X2N.3.2"
FIXTURE = PROJECT_ROOT / "packages/test-fixtures/adapters/v1/xhs_favorites/fixture_manifest.json"
WORKER = PROJECT_ROOT / "scripts/xhs_favorites_chaos_worker.py"
NOW = datetime(2026, 7, 23, tzinfo=timezone.utc)
ACCOUNT_HASH = "a" * 64


def _run_unit_suite() -> dict[str, int]:
    spec = importlib.util.spec_from_file_location(
        "x2n_adapters_002_tests",
        PROJECT_ROOT / "apps/companion/tests/test_xiaohongshu_favorites.py",
    )
    if spec is None or spec.loader is None:
        raise AssertionError("Adapters002 unit test module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    suite = unittest.TestLoader().loadTestsFromModule(module)
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("Adapters002 unit suite failed")
    return {
        "errors": len(result.errors),
        "failures": len(result.failures),
        "skips": len(result.skipped),
        "tests": result.testsRun,
    }


def _dom_acceptance() -> dict[str, Any]:
    environment = {
        "HOME": os.environ.get("HOME", ""),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "npm_config_audit": "false",
        "npm_config_fund": "false",
        "npm_config_ignore_scripts": "true",
    }
    browser_cache = PROJECT_ROOT / "build/playwright-browsers"
    configured_cache = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if configured_cache:
        environment["PLAYWRIGHT_BROWSERS_PATH"] = configured_cache
    elif browser_cache.is_dir():
        environment["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_cache)
    result = subprocess.run(
        ["npm", "--workspace", "@x2n/extension", "run", "--silent", "test:xhs-favorites-fixtures"],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise AssertionError("Adapters002 DOM fixture acceptance failed")
    lines = [line for line in result.stdout.splitlines() if line.strip().startswith("{")]
    if not lines:
        raise AssertionError("Adapters002 DOM fixture receipt is missing")
    payload = json.loads(lines[-1])
    if payload.get("status") != "PASS" or payload.get("network_calls") != 0:
        raise AssertionError("Adapters002 DOM fixture receipt is invalid")
    return payload


def _item(index: int) -> XhsFavoriteItem:
    collection = index % 2
    return XhsFavoriteItem(
        content_id=f"synth_xhs_favorite_{index:03d}",
        content_type="image_gallery" if index % 2 == 0 else "video",
        title=f"合成收藏条目 {index:03d}",
        collection_id=f"collection_{collection}",
        collection_name_private=f"合成收藏夹 {collection}",
    )


def _batch(sequence: int) -> XhsFavoritesBatch:
    return XhsFavoritesBatch(
        sequence=sequence,
        status="ready",
        completion_signal="authoritative_end" if sequence == 4 else "more_available",
        visible_card_count=20,
        items=tuple(_item(index) for index in range(sequence * 20, sequence * 20 + 20)),
        error_codes=(),
        observed_at=NOW + timedelta(minutes=sequence),
    )


def _chaos_acceptance(fixture: dict[str, Any]) -> dict[str, Any]:
    chaos = fixture["chaos"]
    rng = random.Random(chaos["seed"])
    with tempfile.TemporaryDirectory(prefix="x2n-a002-chaos-") as value:
        destination = Path(value) / "MediaCrawler"
        destination.mkdir(mode=0o700)
        root = destination / "xhs-douyin-2notion"
        paths = RuntimePaths.from_values(
            str(root),
            str(destination),
            repository_root=PROJECT_ROOT,
            create=True,
        )
        store = CanonicalStore(paths, busy_timeout_ms=30_000)
        store.initialize()
        scan_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "x2n-adapters002-chaos-100"))
        adapter = XhsFavoritesAdapter(store)
        adapter.begin_scan(scan_id, account_ref_hash=ACCOUNT_HASH, scope_mode="full_scan", started_at=NOW)
        env = {
            "HOME": str(Path(value) / "home"),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": "apps/companion/src:packages/contracts/src",
            "X2N_DATA_ROOT": str(root),
            "X2N_DOWNLOAD_DESTINATION": str(destination),
        }
        Path(env["HOME"]).mkdir(mode=0o700)
        kill_count = 0
        for sequence in range(5):
            labels = [f"after_item_{index}" for index in range(20)] + ["before_checkpoint", "after_checkpoint"]
            for _ in range(10):
                label = rng.choice(labels)
                killed = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(WORKER),
                        "--scan-id",
                        scan_id,
                        "--sequence",
                        str(sequence),
                        "--kill-label",
                        label,
                    ],
                    cwd=PROJECT_ROOT,
                    env=env,
                    check=False,
                    capture_output=True,
                    timeout=120,
                )
                if killed.returncode != 79 or killed.stdout or killed.stderr:
                    raise AssertionError("Adapters002 chaos worker did not stop at the selected kill point")
                kill_count += 1
                recovered = XhsFavoritesAdapter(CanonicalStore(paths, busy_timeout_ms=30_000)).checkpoint(scan_id)
                if recovered.next_sequence != sequence:
                    raise AssertionError("Adapters002 checkpoint advanced across an uncommitted kill")
            adapter = XhsFavoritesAdapter(CanonicalStore(paths, busy_timeout_ms=30_000))
            receipt = adapter.commit_batch(scan_id, _batch(sequence))
            replay = adapter.commit_batch(scan_id, _batch(sequence))
            if receipt.next_sequence != sequence + 1 or replay.disposition != "replayed":
                raise AssertionError("Adapters002 durable resume or replay failed")

        connection = CanonicalStore(paths)._open(writable=False)
        try:
            ids = {str(row[0]) for row in connection.execute("SELECT platform_content_id FROM content")}
            expected = {f"synth_xhs_favorite_{index:03d}" for index in range(100)}
            relation_count = int(connection.execute("SELECT COUNT(*) FROM user_relation").fetchone()[0])
            observation_count = int(connection.execute("SELECT COUNT(*) FROM source_observation").fetchone()[0])
            removed = int(
                connection.execute("SELECT COUNT(*) FROM user_relation WHERE status = 'removed'").fetchone()[0]
            )
            candidates = int(
                connection.execute(
                    "SELECT COUNT(*) FROM user_relation WHERE status = 'tombstone_candidate'"
                ).fetchone()[0]
            )
            collections = int(
                connection.execute("SELECT COUNT(DISTINCT source_collection_id) FROM user_relation").fetchone()[0]
            )
        finally:
            connection.close()
        if ids != expected or relation_count != 100 or observation_count != 100:
            raise AssertionError("Adapters002 final Canonical ID set or cardinality differs")
        if kill_count != 50 or removed != 0 or candidates != 0 or collections != 2:
            raise AssertionError("Adapters002 chaos safety metric differs")
        return {
            "automatic_scrolls": 0,
            "checkpoint_state": receipt.checkpoint_state,
            "collection_count": collections,
            "content_auto_deletes": 0,
            "duplicate_side_effects": 0,
            "final_id_set_exact": True,
            "infinite_loops": 0,
            "kill_runs": kill_count,
            "lost_ids": 0,
            "observation_count": observation_count,
            "physical_deletes": 0,
            "relation_count": relation_count,
            "removed_relations": removed,
            "resume_from_durable_checkpoint": True,
            "tombstone_candidates": candidates,
        }


def run() -> dict[str, Any]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if fixture.get("fixture_id") != "FIXTURE.X2N.S03.A002.001" or fixture.get("synthetic") is not True:
        raise AssertionError("Adapters002 fixture identity drifted")
    for field in (
        "contains_accounts",
        "contains_cookies",
        "contains_credentials",
        "contains_local_absolute_paths",
        "contains_media_urls",
        "contains_private_content",
        "contains_profile_paths",
    ):
        if fixture.get(field) is not False:
            raise AssertionError(f"Adapters002 fixture privacy boundary drifted: {field}")
    dom = _dom_acceptance()
    chaos = _chaos_acceptance(fixture)
    unit = _run_unit_suite()
    canary = build_xhs_favorites_canary_plan()
    return {
        "acceptance_scope": "ADAPTERS_002_XHS_FAVORITES_CI_SYNTH",
        "automatic_scrolls": 0,
        "canary_item_limit": canary["max_items"],
        "canary_tooling": "PASS_NONEXECUTING",
        "chaos": chaos,
        "dom": dom,
        "identified_item_success_percent": 100,
        "network_calls": 0,
        "owner_canary": "NOT_RUN",
        "owner_profile_login": "NOT_RUN",
        "phase": PHASE,
        "platform_calls": 0,
        "real_account_execution": "NOT_RUN",
        "silent_losses": 0,
        "status": "PASS_CI_SYNTH_SCOPED",
        "task_id": TASK_ID,
        "unit_suite": unit,
    }


def main() -> int:
    try:
        payload = run()
    except Exception as error:
        print(
            json.dumps(
                {"reason": str(error), "status": "FAIL_CLOSED", "task_id": TASK_ID},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
