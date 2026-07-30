#!/usr/bin/env python3
"""Run Adapters003 DOM, Canonical and 50-process-kill synthetic acceptance."""

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
)
from x2n_companion.xiaohongshu_likes import (  # noqa: E402
    XhsLikeItem,
    XhsLikesAdapter,
    XhsLikesBatch,
    build_xhs_likes_canary_plan,
)


TASK_ID = "TSK.x2n.adapters.003"
PHASE = "PH.X2N.3.3"
FIXTURE = PROJECT_ROOT / "packages/test-fixtures/adapters/v1/xhs_likes/fixture_manifest.json"
WORKER = PROJECT_ROOT / "scripts/xhs_likes_chaos_worker.py"
NOW = datetime(2026, 7, 23, tzinfo=timezone.utc)
ACCOUNT_HASH = "a" * 64


def _run_unit_suite() -> dict[str, int]:
    spec = importlib.util.spec_from_file_location(
        "x2n_adapters_003_tests",
        PROJECT_ROOT / "apps/companion/tests/test_xiaohongshu_likes.py",
    )
    if spec is None or spec.loader is None:
        raise AssertionError("Adapters003 unit test module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    suite = unittest.TestLoader().loadTestsFromModule(module)
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("Adapters003 unit suite failed")
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
        ["npm", "--workspace", "@x2n/extension", "run", "--silent", "test:xhs-likes-fixtures"],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise AssertionError("Adapters003 DOM fixture acceptance failed")
    lines = [line for line in result.stdout.splitlines() if line.strip().startswith("{")]
    if not lines:
        raise AssertionError("Adapters003 DOM fixture receipt is missing")
    payload = json.loads(lines[-1])
    if payload.get("status") != "PASS" or payload.get("network_calls") != 0:
        raise AssertionError("Adapters003 DOM fixture receipt is invalid")
    return payload


def _item(index: int) -> XhsLikeItem:
    return XhsLikeItem(
        content_id=f"synth_xhs_like_{index:03d}",
        content_type="image_gallery" if index % 2 == 0 else "video",
        title=f"合成点赞条目 {index:03d}",
    )


def _favorite_overlap_item(index: int) -> XhsFavoriteItem:
    return XhsFavoriteItem(
        content_id=f"synth_xhs_like_{index:03d}",
        content_type="image_gallery" if index % 2 == 0 else "video",
        title=f"合成点赞条目 {index:03d}",
        collection_id="collection_overlap",
        collection_name_private="合成重叠收藏夹",
    )


def _batch(sequence: int) -> XhsLikesBatch:
    return XhsLikesBatch(
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
    with tempfile.TemporaryDirectory(prefix="x2n-a003-chaos-") as value:
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
        favorite_scan_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "x2n-adapters003-favorite-overlap-20"))
        favorite_adapter = XhsFavoritesAdapter(store)
        favorite_adapter.begin_scan(
            favorite_scan_id,
            account_ref_hash=ACCOUNT_HASH,
            scope_mode="full_scan",
            started_at=NOW - timedelta(minutes=1),
        )
        favorite_adapter.commit_batch(
            favorite_scan_id,
            XhsFavoritesBatch(
                sequence=0,
                status="ready",
                completion_signal="authoritative_end",
                visible_card_count=20,
                items=tuple(_favorite_overlap_item(index) for index in range(20)),
                error_codes=(),
                observed_at=NOW - timedelta(minutes=1),
            ),
        )
        scan_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "x2n-adapters003-chaos-100"))
        adapter = XhsLikesAdapter(store)
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
                    raise AssertionError("Adapters003 chaos worker did not stop at the selected kill point")
                kill_count += 1
                recovered = XhsLikesAdapter(CanonicalStore(paths, busy_timeout_ms=30_000)).checkpoint(scan_id)
                if recovered.next_sequence != sequence:
                    raise AssertionError("Adapters003 checkpoint advanced across an uncommitted kill")
            adapter = XhsLikesAdapter(CanonicalStore(paths, busy_timeout_ms=30_000))
            receipt = adapter.commit_batch(scan_id, _batch(sequence))
            replay = adapter.commit_batch(scan_id, _batch(sequence))
            if receipt.next_sequence != sequence + 1 or replay.disposition != "replayed":
                raise AssertionError("Adapters003 durable resume or replay failed")

        connection = CanonicalStore(paths)._open(writable=False)
        try:
            ids = {str(row[0]) for row in connection.execute("SELECT platform_content_id FROM content")}
            expected = {f"synth_xhs_like_{index:03d}" for index in range(100)}
            content_count = int(connection.execute("SELECT COUNT(*) FROM content").fetchone()[0])
            relation_count = int(connection.execute("SELECT COUNT(*) FROM user_relation").fetchone()[0])
            observation_count = int(connection.execute("SELECT COUNT(*) FROM source_observation").fetchone()[0])
            liked_relations = int(
                connection.execute("SELECT COUNT(*) FROM user_relation WHERE relation_type = 'liked'").fetchone()[0]
            )
            favorited_relations = int(
                connection.execute("SELECT COUNT(*) FROM user_relation WHERE relation_type = 'favorited'").fetchone()[0]
            )
            likes_observations = int(
                connection.execute(
                    "SELECT COUNT(*) FROM source_observation WHERE adapter_name = 'xhs_likes'"
                ).fetchone()[0]
            )
            removed = int(
                connection.execute("SELECT COUNT(*) FROM user_relation WHERE status = 'removed'").fetchone()[0]
            )
            candidates = int(
                connection.execute(
                    "SELECT COUNT(*) FROM user_relation WHERE status = 'tombstone_candidate'"
                ).fetchone()[0]
            )
            classifications = int(connection.execute("SELECT COUNT(*) FROM classification").fetchone()[0])
            taxonomy_rows = int(connection.execute("SELECT COUNT(*) FROM taxonomy_category").fetchone()[0])
        finally:
            connection.close()
        if (
            ids != expected
            or content_count != 100
            or relation_count != 120
            or liked_relations != 100
            or favorited_relations != 20
            or observation_count != 120
            or likes_observations != 100
        ):
            raise AssertionError("Adapters003 final Canonical ID set or cardinality differs")
        if kill_count != 50 or removed != 0 or candidates != 0 or classifications != 0 or taxonomy_rows != 0:
            raise AssertionError("Adapters003 chaos safety metric differs")
        return {
            "automatic_classification_writes": classifications,
            "automatic_scrolls": 0,
            "checkpoint_state": receipt.checkpoint_state,
            "content_auto_deletes": 0,
            "content_count": content_count,
            "duplicate_content_rows": 0,
            "duplicate_side_effects": 0,
            "favorited_relation_count": favorited_relations,
            "final_id_set_exact": True,
            "infinite_loops": 0,
            "kill_runs": kill_count,
            "liked_relation_count": liked_relations,
            "likes_observation_count": likes_observations,
            "lost_ids": 0,
            "observation_count": observation_count,
            "physical_deletes": 0,
            "relation_count": relation_count,
            "removed_relations": removed,
            "resume_from_durable_checkpoint": True,
            "taxonomy_mutations": taxonomy_rows,
            "tombstone_candidates": candidates,
        }


def run() -> dict[str, Any]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if fixture.get("fixture_id") != "FIXTURE.X2N.S03.A003.001" or fixture.get("synthetic") is not True:
        raise AssertionError("Adapters003 fixture identity drifted")
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
            raise AssertionError(f"Adapters003 fixture privacy boundary drifted: {field}")
    dom = _dom_acceptance()
    chaos = _chaos_acceptance(fixture)
    unit = _run_unit_suite()
    canary = build_xhs_likes_canary_plan()
    return {
        "acceptance_scope": "ADAPTERS_003_XHS_LIKES_CI_SYNTH",
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
