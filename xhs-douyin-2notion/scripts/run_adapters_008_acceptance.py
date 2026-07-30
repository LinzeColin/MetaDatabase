#!/usr/bin/env python3
"""Run Adapters008 official-scope, Canonical and 50-process-kill acceptance."""

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

from x2n_contracts import ErrorCode  # noqa: E402
from x2n_companion.weibo_selected import (  # noqa: E402
    WeiboCapabilityReceipt,
    WeiboSelectedAdapter,
    WeiboSelectedIterator,
    build_weibo_canary_plan,
    evaluate_weibo_capability,
)
from x2n_companion.canonical_store import CanonicalStore  # noqa: E402
from x2n_companion.runtime import RuntimePaths, X2NRuntimeError  # noqa: E402


TASK_ID = "TSK.x2n.adapters.008"
PHASE = "PH.X2N.3.7"
FIXTURE = PROJECT_ROOT / "packages/test-fixtures/adapters/v1/weibo_selected/fixture_manifest.json"
WORKER = PROJECT_ROOT / "scripts/weibo_selected_chaos_worker.py"
NOW = datetime(2026, 7, 23, tzinfo=timezone.utc)
ACCOUNT_HASH = "a" * 64
AUTH_HASH = "b" * 64
PRICE_HASH = "d" * 64
QUOTA_HASH = "e" * 64
MANIFEST_HASH = "c" * 64
SELECTION_ID = "x2nsel_0123456789abcdef0123456789abcdef"


def _capability(environment: str = "ci_synthetic", **overrides: Any) -> WeiboCapabilityReceipt:
    values: dict[str, Any] = {
        "environment": environment,
        "source_kind": "current_authorized_user_favorites",
        "policy_revision": "2026-07-23",
        "authorization_ref_sha256": AUTH_HASH,
        "pricing_ref_sha256": PRICE_HASH,
        "quota_ref_sha256": QUOTA_HASH,
        "application_approved": False,
        "owner_oauth_active": False,
        "favorites_interface_granted": False,
        "pricing_confirmed": False,
        "quota_confirmed": False,
        "approved_budget_units": 0,
        "projected_cost_units": None,
        "remaining_quota_requests": None,
        "sanitized_transport_attested": False,
        "local_only_storage_attested": False,
        "canonical_route_attested": False,
        "authorization_revoked": False,
        "credential_material_present": False,
    }
    values.update(overrides)
    return WeiboCapabilityReceipt(**values)


def _manifest(
    *,
    status: str = "ready",
    items: list[dict[str, object]] | None = None,
    count: int | None = None,
    errors: list[str] | None = None,
    selection_id: str = SELECTION_ID,
    manifest_hash: str = MANIFEST_HASH,
    http_status: int | None = None,
    retry_after: str | None = None,
) -> dict[str, object]:
    if items is None:
        items = []
        content_types = ("text", "image_gallery", "video", "mixed")
        for index in range(20):
            status_id = f"synthetic-wb-favorite-{index:03d}"
            items.append(
                {
                    "status_id": status_id,
                    "canonical_page_url": f"https://www.weibo.com/detail/{status_id}",
                    "content_type": content_types[index % len(content_types)],
                    "published_at": f"2026-07-23T00:{index:02d}:00Z",
                    "title": f"合成授权作品 {index:03d}",
                }
            )
    errors = errors or []
    return {
        "automatic_pagination": False,
        "automatic_scroll": False,
        "error_codes": errors,
        "explicit_owner_action": True,
        "has_more": True,
        "http_status": http_status,
        "items": items,
        "owner_selection_id": selection_id,
        "page_number": 1,
        "page_size": 20,
        "platform": "weibo",
        "policy_revision": "2026-07-23",
        "retry_after": retry_after,
        "schema_version": "1.0",
        "selected_manifest_count": len(items) + len(errors) if count is None else count,
        "selection_manifest_sha256": manifest_hash,
        "source_kind": "current_authorized_user_favorites",
        "status": status,
    }


def _batch(**kwargs: Any) -> Any:
    return WeiboSelectedIterator(_capability()).one_explicit_batch(_manifest(**kwargs), observed_at=NOW)


def _run_unit_suite() -> dict[str, int]:
    spec = importlib.util.spec_from_file_location(
        "x2n_adapters_008_tests",
        PROJECT_ROOT / "apps/companion/tests/test_weibo_selected.py",
    )
    if spec is None or spec.loader is None:
        raise AssertionError("Adapters008 unit test module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(
        unittest.TestLoader().loadTestsFromModule(module)
    )
    if not result.wasSuccessful():
        raise AssertionError("Adapters008 unit suite failed")
    return {
        "errors": len(result.errors),
        "failures": len(result.failures),
        "skips": len(result.skipped),
        "tests": result.testsRun,
    }


def _capability_acceptance() -> dict[str, Any]:
    synthetic = evaluate_weibo_capability(_capability())
    budget_zero = evaluate_weibo_capability(_capability("owner_runtime"))
    price_quota_unknown = evaluate_weibo_capability(_capability("owner_runtime", approved_budget_units=1))
    budget_exceeded = evaluate_weibo_capability(
        _capability(
            "owner_runtime",
            approved_budget_units=1,
            pricing_confirmed=True,
            projected_cost_units=2,
            quota_confirmed=True,
            remaining_quota_requests=1,
        )
    )
    quota_exhausted = evaluate_weibo_capability(
        _capability(
            "owner_runtime",
            approved_budget_units=2,
            pricing_confirmed=True,
            projected_cost_units=1,
            quota_confirmed=True,
            remaining_quota_requests=0,
        )
    )
    priced = {
        "approved_budget_units": 2,
        "pricing_confirmed": True,
        "projected_cost_units": 1,
        "quota_confirmed": True,
        "remaining_quota_requests": 1,
    }
    missing = evaluate_weibo_capability(_capability("owner_runtime", **priced))
    eligible = evaluate_weibo_capability(
        _capability(
            "owner_runtime",
            **priced,
            application_approved=True,
            owner_oauth_active=True,
            favorites_interface_granted=True,
            sanitized_transport_attested=True,
            local_only_storage_attested=True,
            canonical_route_attested=True,
        )
    )
    revoked = evaluate_weibo_capability(_capability("owner_runtime", authorization_revoked=True))
    if (
        synthetic.status != "PASS_CI_SYNTHETIC"
        or not synthetic.offline_mapping_permitted
        or synthetic.platform_requests_permitted
        or budget_zero.status != "BLOCKED_BUDGET_ZERO"
        or price_quota_unknown.status != "BLOCKED_PRICE_OR_QUOTA_UNKNOWN"
        or budget_exceeded.status != "BLOCKED_BUDGET_EXCEEDED"
        or quota_exhausted.status != "BLOCKED_QUOTA_EXHAUSTED"
        or missing.status != "BLOCKED_MISSING_AUTHORIZATION"
        or len(missing.missing_requirements) != 6
        or eligible.status != "BLOCKED_FEATURE_DISABLED"
        or revoked.status != "BLOCKED_AUTHORIZATION_REVOKED"
        or not revoked.authorization_cleanup_required
        or revoked.platform_requests_permitted
    ):
        raise AssertionError("Adapters008 capability gate differs")
    return {
        "ci_synthetic_mapping": True,
        "canonical_public_route": "UNVERIFIED_DISABLED",
        "authorization_revoked_status": revoked.status,
        "authorization_cleanup_required": True,
        "budget_exceeded_status": budget_exceeded.status,
        "budget_zero_status": budget_zero.status,
        "documented_source_kind": "current_authorized_user_favorites",
        "documented_endpoint": "GET /2/favorites.json",
        "interface_permission_required": True,
        "missing_requirement_count": 6,
        "new_requests_after_revocation": 0,
        "official_scope": "ordinary_interface_permission_plus_owner_oauth",
        "owner_runtime_status": eligible.status,
        "owner_oauth_required": True,
        "personal_favorites_api": "DOCUMENTED_APP_ACCESS_UNKNOWN_DISABLED",
        "personal_likes_api": "UNKNOWN_DISABLED",
        "platform_requests": 0,
        "price_quota_unknown_status": price_quota_unknown.status,
        "production_enabled": False,
        "quota_exhausted_status": quota_exhausted.status,
        "raw_open_api_responses": 0,
    }


def _chaos_acceptance(fixture: dict[str, Any]) -> dict[str, Any]:
    rng = random.Random(fixture["chaos"]["seed"])
    with tempfile.TemporaryDirectory(prefix="x2n-a008-chaos-") as value:
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
        scan_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "x2n-adapters008-chaos-20"))
        adapter = WeiboSelectedAdapter(store)
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
                raise AssertionError("Adapters008 chaos worker did not stop at the selected kill point")
            recovered = WeiboSelectedAdapter(CanonicalStore(paths, busy_timeout_ms=30_000)).checkpoint(scan_id)
            if recovered.next_sequence != 0 or recovered.manifest_items != 0:
                raise AssertionError("Adapters008 checkpoint advanced across an uncommitted kill")

        adapter = WeiboSelectedAdapter(CanonicalStore(paths, busy_timeout_ms=30_000))
        receipt = adapter.commit_batch(scan_id, _batch())
        replay = adapter.commit_batch(scan_id, _batch())

        connection = CanonicalStore(paths)._open(writable=False)
        try:
            content_ids = {str(row[0]) for row in connection.execute("SELECT platform_content_id FROM content")}
            relation_count = int(connection.execute("SELECT COUNT(*) FROM user_relation").fetchone()[0])
            scan_confirmed_favorited = int(
                connection.execute(
                    "SELECT COUNT(*) FROM user_relation WHERE relation_type = 'favorited' AND confirmed_by = 'scan'"
                ).fetchone()[0]
            )
            fake_relations = int(
                connection.execute(
                    "SELECT COUNT(*) FROM user_relation WHERE relation_type IN ('liked', 'saved_current')"
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
        expected_ids = {f"synthetic-wb-favorite-{index:03d}" for index in range(20)}
        if (
            content_ids != expected_ids
            or relation_count != 20
            or scan_confirmed_favorited != 20
            or fake_relations != 0
            or observations != 20
            or receipt.identified_percent != 100.0
            or replay.disposition != "replayed"
        ):
            raise AssertionError("Adapters008 final Canonical identity or cardinality differs")
        if removed or candidates or classifications or taxonomy:
            raise AssertionError("Adapters008 deletion or taxonomy safety metric differs")
        return {
            "automatic_pagination": 0,
            "automatic_scroll": 0,
            "checkpoint_state": receipt.checkpoint_state,
            "content_auto_deletes": 0,
            "content_count": len(content_ids),
            "duplicate_side_effects": 0,
            "fake_liked_or_saved_current_relations": fake_relations,
            "final_id_set_exact": True,
            "identified_item_success_percent": receipt.identified_percent,
            "kill_runs": 50,
            "lost_ids": 0,
            "observation_count": observations,
            "scan_confirmed_favorited_relations": scan_confirmed_favorited,
            "physical_deletes": 0,
            "relation_count": relation_count,
            "removed_relations": removed,
            "authorization_cleanup_required": receipt.authorization_cleanup_required,
            "approved_budget_units": receipt.approved_budget_units,
            "platform_requests": 0,
            "resume_from_durable_checkpoint": True,
            "silent_losses": 0,
            "taxonomy_mutations": taxonomy,
            "tombstone_candidates": candidates,
        }


def _blocked_state_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-a008-blocked-") as value:
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
        historical_id = "x2nsel_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
        historical_hash = "e" * 64
        historical_scan = str(uuid.uuid5(uuid.NAMESPACE_URL, "x2n-adapters008-historical"))
        historical = WeiboSelectedAdapter(store)
        historical.begin_scan(
            historical_scan,
            account_ref_hash=ACCOUNT_HASH,
            owner_selection_id=historical_id,
            selection_manifest_sha256=historical_hash,
            capability=_capability(),
            started_at=NOW,
        )
        historical.commit_batch(
            historical_scan,
            _batch(items=[_manifest()["items"][0]], count=1, selection_id=historical_id, manifest_hash=historical_hash),
        )
        baseline = store.counts()
        cases = (
            ("auth_required", ErrorCode.ADAPTER_AUTH_EXPIRED.value, True),
            ("oauth_revoked", ErrorCode.POLICY_BLOCKED.value, True),
            ("budget_blocked", ErrorCode.POLICY_BLOCKED.value, True),
            ("policy_blocked", ErrorCode.POLICY_BLOCKED.value, True),
            ("empty_unverified", ErrorCode.PROVENANCE_INCOMPLETE.value, False),
            ("platform_changed", ErrorCode.PLATFORM_CHANGED.value, False),
        )
        killed = 0
        cleanup_required = 0
        for index, (status, error, should_kill) in enumerate(cases):
            selection_id = f"x2nsel_{index + 1:032x}"
            manifest_hash = f"{index + 1:064x}"
            scan_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"x2n-adapters008-blocked-{status}"))
            adapter = WeiboSelectedAdapter(store)
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
                raise AssertionError("Adapters008 platform Kill disposition differs")
            if receipt.authorization_cleanup_required != (status == "oauth_revoked"):
                raise AssertionError("Adapters008 revocation cleanup disposition differs")
            if receipt.safe_dict()["new_requests_after_revocation"] != 0:
                raise AssertionError("Adapters008 made a request after revocation")
            killed += int(should_kill)
            cleanup_required += int(receipt.authorization_cleanup_required)

        partial_id = "x2nsel_ffffffffffffffffffffffffffffffff"
        partial_hash = "f" * 64
        partial_scan = str(uuid.uuid5(uuid.NAMESPACE_URL, "x2n-adapters008-blocked-partial"))
        partial_adapter = WeiboSelectedAdapter(store)
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
        if any(counts[key] != baseline[key] for key in ("content", "user_relation", "source_observation")):
            raise AssertionError("Adapters008 blocked states changed historical Canonical entities")
        return {
            "blocked_state_cases": 7,
            "canonical_writes": 0,
            "historical_relation_deletes": 0,
            "historical_relations_preserved": baseline["user_relation"],
            "new_requests_after_revocation": 0,
            "partial_identified_percent": partial.identified_percent,
            "platform_kills": killed,
            "authorization_cleanup_required_receipts": cleanup_required,
        }


def _rate_limit_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-a008-rate-") as value:
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
        scan_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "x2n-adapters008-rate-limit"))
        adapter = WeiboSelectedAdapter(store)
        adapter.begin_scan(
            scan_id,
            account_ref_hash=ACCOUNT_HASH,
            owner_selection_id=SELECTION_ID,
            selection_manifest_sha256=MANIFEST_HASH,
            capability=_capability(),
            started_at=NOW,
        )
        limited = _batch(
            status="rate_limited",
            items=[],
            count=0,
            errors=[ErrorCode.RATE_LIMITED.value],
            http_status=429,
            retry_after="120",
        )
        receipt = adapter.commit_batch(scan_id, limited)
        if (
            receipt.checkpoint_state != "active"
            or receipt.cursor_kind != "rate_limited_retry_after"
            or not receipt.rate_limited
            or receipt.retry_after_seconds != 120
            or receipt.retry_not_before != "2026-07-23T00:02:00Z"
            or receipt.relation_count != 0
        ):
            raise AssertionError("Adapters008 Retry-After receipt differs")
        early = WeiboSelectedIterator(_capability()).one_explicit_batch(
            _manifest(items=[_manifest()["items"][0]], count=1),  # type: ignore[index]
            observed_at=NOW + timedelta(seconds=119),
        )
        early_blocks = 0
        try:
            adapter.commit_batch(scan_id, early)
        except X2NRuntimeError as error:
            if error.code != ErrorCode.POLICY_BLOCKED:
                raise
            early_blocks = 1
        if early_blocks != 1:
            raise AssertionError("Adapters008 retried before Retry-After")
        corrected = WeiboSelectedIterator(_capability()).one_explicit_batch(
            _manifest(items=[_manifest()["items"][0]], count=1),  # type: ignore[index]
            observed_at=NOW + timedelta(seconds=120),
        )
        completed = adapter.commit_batch(scan_id, corrected)
        safe = completed.safe_dict()
        if completed.checkpoint_state != "complete" or completed.rate_limited or completed.relation_count != 1:
            raise AssertionError("Adapters008 explicit post-hold recovery differs")
        return {
            "automatic_retries": 0,
            "canonical_writes_on_429": 0,
            "checkpoint_advances_on_429": 0,
            "early_resume_blocks": early_blocks,
            "http_429_cases": 1,
            "platform_requests": safe["cost"]["platform_requests"],
            "proxy_rotations": safe["rate_limit"]["proxy_rotations"],
            "retry_after_seconds": 120,
            "resume_after_hold": True,
        }


def run() -> dict[str, Any]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if (
        fixture.get("fixture_id") != "FIXTURE.X2N.S03.A008.001"
        or fixture.get("synthetic") is not True
        or len(fixture.get("cases", [])) != 58
    ):
        raise AssertionError("Adapters008 fixture identity or case count differs")
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
            raise AssertionError(f"Adapters008 fixture privacy boundary differs: {field}")
    capability = _capability_acceptance()
    chaos = _chaos_acceptance(fixture)
    blocked = _blocked_state_acceptance()
    rate_limit = _rate_limit_acceptance()
    unit = _run_unit_suite()
    canary = build_weibo_canary_plan()
    return {
        "acceptance_scope": "ADAPTERS_008_WEIBO_SELECTED_CI_SYNTH",
        "automatic_pagination": 0,
        "automatic_scroll": 0,
        "blocked": blocked,
        "canary_item_limit": canary["max_items"],
        "canary_tooling": "PASS_NONEXECUTING",
        "capability": capability,
        "chaos": chaos,
        "cost_receipt": {
            "approved_budget_units": 0,
            "automatic_plan_upgrades": 0,
            "platform_requests": 0,
            "price_state": "UNKNOWN_NOT_APPROVED",
            "quota_state": "UNKNOWN_NOT_APPROVED",
        },
        "identified_item_success_percent": chaos["identified_item_success_percent"],
        "network_calls": 0,
        "owner_canary": "NOT_RUN",
        "owner_profile_login": "NOT_RUN",
        "phase": PHASE,
        "platform_calls": 0,
        "real_account_execution": "NOT_RUN",
        "rate_limit": rate_limit,
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
