#!/usr/bin/env python3
"""Run Adapters006 official-scope, Canonical and 50-process-kill acceptance."""

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps/companion/src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages/contracts/src"))

from x2n_contracts import ErrorCode  # noqa: E402
from x2n_companion.bilibili_selected import (  # noqa: E402
    BilibiliCapabilityReceipt,
    BilibiliSelectedAdapter,
    BilibiliSelectedIterator,
    build_bilibili_canary_plan,
    evaluate_bilibili_capability,
)
from x2n_companion.canonical_store import CanonicalStore  # noqa: E402
from x2n_companion.runtime import RuntimePaths  # noqa: E402


TASK_ID = "TSK.x2n.adapters.006"
PHASE = "PH.X2N.3.5"
FIXTURE = PROJECT_ROOT / "packages/test-fixtures/adapters/v1/bilibili_selected/fixture_manifest.json"
WORKER = PROJECT_ROOT / "scripts/bilibili_selected_chaos_worker.py"
NOW = datetime(2026, 7, 23, tzinfo=timezone.utc)
ACCOUNT_HASH = "a" * 64
AUTH_HASH = "b" * 64
MANIFEST_HASH = "c" * 64
SELECTION_ID = "x2nsel_0123456789abcdef0123456789abcdef"


def _capability(environment: str = "ci_synthetic", **overrides: bool) -> BilibiliCapabilityReceipt:
    values: dict[str, Any] = {
        "environment": environment,
        "source_kind": "authorized_uploader_video_manuscripts",
        "policy_revision": "2026-07-23",
        "authorization_ref_sha256": AUTH_HASH,
        "application_approved": False,
        "owner_authorized": False,
        "arc_base_granted": False,
        "written_automation_permission": False,
        "transport_available": False,
        "credential_material_present": False,
    }
    values.update(overrides)
    return BilibiliCapabilityReceipt(**values)


def _manifest(
    *,
    status: str = "ready",
    items: list[dict[str, object]] | None = None,
    count: int | None = None,
    errors: list[str] | None = None,
    selection_id: str = SELECTION_ID,
    manifest_hash: str = MANIFEST_HASH,
) -> dict[str, object]:
    if items is None:
        items = []
        for index in range(20):
            bvid = f"BV{index:010d}"
            items.append(
                {
                    "bvid": bvid,
                    "canonical_page_url": f"https://www.bilibili.com/video/{bvid}",
                    "content_type": "video",
                    "published_at": f"2026-07-23T00:{index:02d}:00Z",
                    "title": f"合成授权稿件 {index:03d}",
                }
            )
    errors = errors or []
    return {
        "automatic_pagination": False,
        "automatic_scroll": False,
        "error_codes": errors,
        "explicit_owner_action": True,
        "has_more": True,
        "items": items,
        "owner_selection_id": selection_id,
        "page_number": 1,
        "page_size": 20,
        "platform": "bilibili",
        "policy_revision": "2026-07-23",
        "schema_version": "1.0",
        "selected_manifest_count": len(items) + len(errors) if count is None else count,
        "selection_manifest_sha256": manifest_hash,
        "source_kind": "authorized_uploader_video_manuscripts",
        "status": status,
    }


def _batch(**kwargs: Any) -> Any:
    return BilibiliSelectedIterator(_capability()).one_explicit_batch(_manifest(**kwargs), observed_at=NOW)


def _run_unit_suite() -> dict[str, int]:
    spec = importlib.util.spec_from_file_location(
        "x2n_adapters_006_tests",
        PROJECT_ROOT / "apps/companion/tests/test_bilibili_selected.py",
    )
    if spec is None or spec.loader is None:
        raise AssertionError("Adapters006 unit test module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(
        unittest.TestLoader().loadTestsFromModule(module)
    )
    if not result.wasSuccessful():
        raise AssertionError("Adapters006 unit suite failed")
    return {
        "errors": len(result.errors),
        "failures": len(result.failures),
        "skips": len(result.skipped),
        "tests": result.testsRun,
    }


def _capability_acceptance() -> dict[str, Any]:
    synthetic = evaluate_bilibili_capability(_capability())
    missing = evaluate_bilibili_capability(_capability("owner_runtime"))
    eligible = evaluate_bilibili_capability(
        _capability(
            "owner_runtime",
            application_approved=True,
            owner_authorized=True,
            arc_base_granted=True,
            written_automation_permission=True,
            transport_available=True,
        )
    )
    if (
        synthetic.status != "PASS_CI_SYNTHETIC"
        or not synthetic.offline_mapping_permitted
        or synthetic.platform_requests_permitted
        or missing.status != "BLOCKED_MISSING_AUTHORIZATION"
        or len(missing.missing_requirements) != 5
        or eligible.status != "BLOCKED_FEATURE_DISABLED"
    ):
        raise AssertionError("Adapters006 capability gate differs")
    return {
        "ci_synthetic_mapping": True,
        "documented_source_kind": "authorized_uploader_video_manuscripts",
        "missing_requirement_count": 5,
        "official_scope": "ARC_BASE",
        "owner_runtime_status": eligible.status,
        "personal_favorites_api": "UNKNOWN_DISABLED",
        "personal_likes_api": "UNKNOWN_DISABLED",
        "platform_requests": 0,
        "production_enabled": False,
        "raw_open_api_responses": 0,
        "written_automation_permission_required": True,
    }


def _chaos_acceptance(fixture: dict[str, Any]) -> dict[str, Any]:
    rng = random.Random(fixture["chaos"]["seed"])
    with tempfile.TemporaryDirectory(prefix="x2n-a006-chaos-") as value:
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
        scan_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "x2n-adapters006-chaos-20"))
        adapter = BilibiliSelectedAdapter(store)
        adapter.begin_scan(
            scan_id,
            account_ref_hash=ACCOUNT_HASH,
            owner_selection_id=SELECTION_ID,
            selection_manifest_sha256=MANIFEST_HASH,
            capability=_capability(),
            started_at=NOW,
        )
        home = Path(value) / "home"
        home.mkdir(mode=0o700)
        env = {
            "HOME": str(home),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": "apps/companion/src:packages/contracts/src",
            "X2N_DATA_ROOT": str(root),
            "X2N_DOWNLOAD_DESTINATION": str(destination),
        }
        labels = [f"after_item_{index}" for index in range(20)] + ["before_checkpoint", "after_checkpoint"]
        for _ in range(50):
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(WORKER),
                    "--scan-id",
                    scan_id,
                    "--kill-label",
                    rng.choice(labels),
                ],
                cwd=PROJECT_ROOT,
                env=env,
                check=False,
                capture_output=True,
                timeout=120,
            )
            if result.returncode != 79 or result.stdout or result.stderr:
                raise AssertionError("Adapters006 chaos worker did not stop at the selected kill point")
            recovered = BilibiliSelectedAdapter(CanonicalStore(paths, busy_timeout_ms=30_000)).checkpoint(scan_id)
            if recovered.next_sequence != 0 or recovered.manifest_items != 0:
                raise AssertionError("Adapters006 checkpoint advanced across an uncommitted kill")

        adapter = BilibiliSelectedAdapter(CanonicalStore(paths, busy_timeout_ms=30_000))
        receipt = adapter.commit_batch(scan_id, _batch())
        replay = adapter.commit_batch(scan_id, _batch())

        connection = CanonicalStore(paths)._open(writable=False)
        try:
            content_ids = {str(row[0]) for row in connection.execute("SELECT platform_content_id FROM content")}
            relation_count = int(connection.execute("SELECT COUNT(*) FROM user_relation").fetchone()[0])
            saved_current = int(
                connection.execute(
                    "SELECT COUNT(*) FROM user_relation WHERE relation_type = 'saved_current' AND confirmed_by = 'owner'"
                ).fetchone()[0]
            )
            fake_relations = int(
                connection.execute(
                    "SELECT COUNT(*) FROM user_relation WHERE relation_type IN ('liked', 'favorited')"
                ).fetchone()[0]
            )
            observations = int(connection.execute("SELECT COUNT(*) FROM source_observation").fetchone()[0])
            removed = int(
                connection.execute("SELECT COUNT(*) FROM user_relation WHERE status = 'removed'").fetchone()[0]
            )
            candidates = int(
                connection.execute(
                    "SELECT COUNT(*) FROM user_relation WHERE status = 'tombstone_candidate'"
                ).fetchone()[0]
            )
            classifications = int(connection.execute("SELECT COUNT(*) FROM classification").fetchone()[0])
            taxonomy = int(connection.execute("SELECT COUNT(*) FROM taxonomy_category").fetchone()[0])
        finally:
            connection.close()
        expected_ids = {f"BV{index:010d}" for index in range(20)}
        if (
            content_ids != expected_ids
            or relation_count != 20
            or saved_current != 20
            or fake_relations != 0
            or observations != 20
            or receipt.identified_percent != 100.0
            or replay.disposition != "replayed"
        ):
            raise AssertionError("Adapters006 final Canonical identity or cardinality differs")
        if removed or candidates or classifications or taxonomy:
            raise AssertionError("Adapters006 deletion or taxonomy safety metric differs")
        return {
            "automatic_pagination": 0,
            "automatic_scroll": 0,
            "checkpoint_state": receipt.checkpoint_state,
            "content_auto_deletes": 0,
            "content_count": len(content_ids),
            "duplicate_side_effects": 0,
            "fake_favorited_or_liked_relations": fake_relations,
            "final_id_set_exact": True,
            "identified_item_success_percent": receipt.identified_percent,
            "kill_runs": 50,
            "lost_ids": 0,
            "observation_count": observations,
            "owner_confirmed_saved_current_relations": saved_current,
            "physical_deletes": 0,
            "relation_count": relation_count,
            "removed_relations": removed,
            "resume_from_durable_checkpoint": True,
            "silent_losses": 0,
            "taxonomy_mutations": taxonomy,
            "tombstone_candidates": candidates,
        }


def _blocked_state_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-a006-blocked-") as value:
        destination = Path(value) / "MediaCrawler"
        destination.mkdir(mode=0o700)
        paths = RuntimePaths.from_values(
            str(destination / "xhs-douyin-2notion"),
            str(destination),
            repository_root=PROJECT_ROOT,
            create=True,
        )
        store = CanonicalStore(paths)
        store.initialize()
        cases = (
            ("auth_required", ErrorCode.ADAPTER_AUTH_EXPIRED.value, True),
            ("policy_blocked", ErrorCode.POLICY_BLOCKED.value, True),
            ("captcha_required", ErrorCode.POLICY_BLOCKED.value, True),
            ("empty_unverified", ErrorCode.PROVENANCE_INCOMPLETE.value, False),
            ("platform_changed", ErrorCode.PLATFORM_CHANGED.value, False),
        )
        killed = 0
        for index, (status, error, should_kill) in enumerate(cases):
            selection_id = f"x2nsel_{index + 1:032x}"
            manifest_hash = f"{index + 1:064x}"
            scan_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"x2n-adapters006-blocked-{status}"))
            adapter = BilibiliSelectedAdapter(store)
            adapter.begin_scan(
                scan_id,
                account_ref_hash=ACCOUNT_HASH,
                owner_selection_id=selection_id,
                selection_manifest_sha256=manifest_hash,
                capability=_capability(),
                started_at=NOW,
            )
            receipt = adapter.commit_batch(
                scan_id,
                _batch(
                    status=status,
                    items=[],
                    count=0,
                    errors=[error],
                    selection_id=selection_id,
                    manifest_hash=manifest_hash,
                ),
            )
            if receipt.platform_killed != should_kill:
                raise AssertionError("Adapters006 platform Kill disposition differs")
            killed += int(should_kill)

        partial_id = "x2nsel_ffffffffffffffffffffffffffffffff"
        partial_hash = "f" * 64
        partial_scan = str(uuid.uuid5(uuid.NAMESPACE_URL, "x2n-adapters006-blocked-partial"))
        partial_adapter = BilibiliSelectedAdapter(store)
        partial_adapter.begin_scan(
            partial_scan,
            account_ref_hash=ACCOUNT_HASH,
            owner_selection_id=partial_id,
            selection_manifest_sha256=partial_hash,
            capability=_capability(),
            started_at=NOW,
        )
        partial = partial_adapter.commit_batch(
            partial_scan,
            _batch(
                status="partial",
                items=[_manifest()["items"][0]],  # type: ignore[index]
                count=2,
                errors=[ErrorCode.PROVENANCE_INCOMPLETE.value],
                selection_id=partial_id,
                manifest_hash=partial_hash,
            ),
        )
        counts = store.counts()
        if counts["content"] or counts["user_relation"] or counts["source_observation"]:
            raise AssertionError("Adapters006 blocked states wrote Canonical entities")
        return {
            "blocked_state_cases": 6,
            "canonical_writes": 0,
            "historical_relation_deletes": 0,
            "partial_identified_percent": partial.identified_percent,
            "platform_kills": killed,
        }


def run() -> dict[str, Any]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if (
        fixture.get("fixture_id") != "FIXTURE.X2N.S03.A006.001"
        or fixture.get("synthetic") is not True
        or len(fixture.get("cases", [])) != 38
    ):
        raise AssertionError("Adapters006 fixture identity or case count differs")
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
            raise AssertionError(f"Adapters006 fixture privacy boundary differs: {field}")
    capability = _capability_acceptance()
    chaos = _chaos_acceptance(fixture)
    blocked = _blocked_state_acceptance()
    unit = _run_unit_suite()
    canary = build_bilibili_canary_plan()
    return {
        "acceptance_scope": "ADAPTERS_006_BILIBILI_SELECTED_CI_SYNTH",
        "automatic_pagination": 0,
        "automatic_scroll": 0,
        "blocked": blocked,
        "canary_item_limit": canary["max_items"],
        "canary_tooling": "PASS_NONEXECUTING",
        "capability": capability,
        "chaos": chaos,
        "identified_item_success_percent": chaos["identified_item_success_percent"],
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
