#!/usr/bin/env python3
"""Run Adapters009 official-scope, Canonical and 50-process-kill acceptance."""

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
from x2n_companion.taobao_selected import (  # noqa: E402
    TaobaoCapabilityReceipt,
    TaobaoSelectedAdapter,
    TaobaoSelectedIterator,
    build_taobao_canary_plan,
    evaluate_taobao_capability,
)
from x2n_companion.canonical_store import CanonicalStore  # noqa: E402
from x2n_companion.runtime import RuntimePaths, X2NRuntimeError  # noqa: E402


TASK_ID = "TSK.x2n.adapters.009"
PHASE = "PH.X2N.3.8"
FIXTURE = PROJECT_ROOT / "packages/test-fixtures/adapters/v1/taobao_selected/fixture_manifest.json"
WORKER = PROJECT_ROOT / "scripts/taobao_selected_chaos_worker.py"
NOW = datetime(2026, 7, 23, tzinfo=timezone.utc)
ACCOUNT_HASH = "a" * 64
AUTH_HASH = "b" * 64
PRICE_HASH = "d" * 64
QUOTA_HASH = "e" * 64
RETENTION_HASH = "f" * 64
MANIFEST_HASH = "c" * 64
SELECTION_ID = "x2nsel_0123456789abcdef0123456789abcdef"


def _capability(environment: str = "ci_synthetic", **overrides: Any) -> TaobaoCapabilityReceipt:
    values: dict[str, Any] = {
        "environment": environment,
        "source_kind": "owner_explicit_item_ids_for_authorized_item_get",
        "policy_revision": "2026-07-23",
        "authorization_ref_sha256": AUTH_HASH,
        "pricing_ref_sha256": PRICE_HASH,
        "quota_ref_sha256": QUOTA_HASH,
        "retention_ref_sha256": RETENTION_HASH,
        "application_approved": False,
        "owner_oauth_active": False,
        "item_get_scope_granted": False,
        "pricing_confirmed": False,
        "quota_confirmed": False,
        "approved_budget_units": 0,
        "projected_cost_units": None,
        "remaining_quota_requests": None,
        "official_top_transport_attested": False,
        "sanitized_transport_attested": False,
        "local_only_storage_attested": False,
        "canonical_route_attested": False,
        "purpose_scope_disclosure_approved": False,
        "retention_period_approved": False,
        "delete_revoke_flow_ready": False,
        "deletion_receipt_ready": False,
        "authorization_revoked": False,
        "credential_material_present": False,
    }
    values.update(overrides)
    return TaobaoCapabilityReceipt(**values)


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
        for index in range(20):
            num_iid = f"9900000000000{index:06d}"
            items.append(
                {
                    "num_iid": num_iid,
                    "title": f"合成淘宝选定商品 {index:03d}",
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
        "platform": "taobao",
        "policy_revision": "2026-07-23",
        "retry_after": retry_after,
        "schema_version": "1.0",
        "selected_manifest_count": len(items) + len(errors) if count is None else count,
        "selection_manifest_sha256": manifest_hash,
        "source_kind": "owner_explicit_item_ids_for_authorized_item_get",
        "status": status,
    }


def _batch(**kwargs: Any) -> Any:
    return TaobaoSelectedIterator(_capability()).one_explicit_batch(_manifest(**kwargs), observed_at=NOW)


def _run_unit_suite() -> dict[str, int]:
    spec = importlib.util.spec_from_file_location(
        "x2n_adapters_009_tests",
        PROJECT_ROOT / "apps/companion/tests/test_taobao_selected.py",
    )
    if spec is None or spec.loader is None:
        raise AssertionError("Adapters009 unit test module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(
        unittest.TestLoader().loadTestsFromModule(module)
    )
    if not result.wasSuccessful():
        raise AssertionError("Adapters009 unit suite failed")
    return {
        "errors": len(result.errors),
        "failures": len(result.failures),
        "skips": len(result.skipped),
        "tests": result.testsRun,
    }


def _capability_acceptance() -> dict[str, Any]:
    synthetic = evaluate_taobao_capability(_capability())
    budget_zero = evaluate_taobao_capability(_capability("owner_runtime"))
    price_quota_unknown = evaluate_taobao_capability(_capability("owner_runtime", approved_budget_units=1))
    budget_exceeded = evaluate_taobao_capability(
        _capability(
            "owner_runtime",
            approved_budget_units=1,
            pricing_confirmed=True,
            projected_cost_units=2,
            quota_confirmed=True,
            remaining_quota_requests=1,
        )
    )
    quota_exhausted = evaluate_taobao_capability(
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
    retention_missing = evaluate_taobao_capability(_capability("owner_runtime", **priced))
    retention_ready = {
        "purpose_scope_disclosure_approved": True,
        "retention_period_approved": True,
        "delete_revoke_flow_ready": True,
        "deletion_receipt_ready": True,
    }
    missing = evaluate_taobao_capability(_capability("owner_runtime", **priced, **retention_ready))
    eligible = evaluate_taobao_capability(
        _capability(
            "owner_runtime",
            **priced,
            **retention_ready,
            application_approved=True,
            owner_oauth_active=True,
            item_get_scope_granted=True,
            official_top_transport_attested=True,
            sanitized_transport_attested=True,
            local_only_storage_attested=True,
            canonical_route_attested=True,
        )
    )
    revoked = evaluate_taobao_capability(_capability("owner_runtime", authorization_revoked=True))
    if (
        synthetic.status != "PASS_CI_SYNTHETIC"
        or not synthetic.offline_mapping_permitted
        or synthetic.platform_requests_permitted
        or budget_zero.status != "BLOCKED_BUDGET_ZERO"
        or price_quota_unknown.status != "BLOCKED_PRICE_OR_QUOTA_UNKNOWN"
        or budget_exceeded.status != "BLOCKED_BUDGET_EXCEEDED"
        or quota_exhausted.status != "BLOCKED_QUOTA_EXHAUSTED"
        or retention_missing.status != "BLOCKED_RETENTION_UNKNOWN"
        or len(retention_missing.missing_requirements) != 4
        or missing.status != "BLOCKED_MISSING_AUTHORIZATION"
        or len(missing.missing_requirements) != 7
        or eligible.status != "BLOCKED_FEATURE_DISABLED"
        or revoked.status != "BLOCKED_AUTHORIZATION_REVOKED"
        or not revoked.authorization_cleanup_required
        or revoked.platform_requests_permitted
    ):
        raise AssertionError("Adapters009 capability gate differs")
    return {
        "ci_synthetic_mapping": True,
        "canonical_public_route": "UNVERIFIED_DISABLED",
        "authorization_revoked_status": revoked.status,
        "authorization_cleanup_required": True,
        "budget_exceeded_status": budget_exceeded.status,
        "budget_zero_status": budget_zero.status,
        "documented_source_kind": "owner_explicit_item_ids_for_authorized_item_get",
        "documented_endpoint": "taobao.item.get",
        "item_get_scope_required": True,
        "missing_requirement_count": 7,
        "new_requests_after_revocation": 0,
        "official_scope": "minimum_num_iid_and_title_fields_plus_owner_oauth",
        "owner_runtime_status": eligible.status,
        "owner_oauth_required": True,
        "personal_favorites_list_api": "NOT_VERIFIED_UNKNOWN_DISABLED",
        "owner_explicit_item_ids_only": True,
        "platform_requests": 0,
        "price_quota_unknown_status": price_quota_unknown.status,
        "production_enabled": False,
        "quota_exhausted_status": quota_exhausted.status,
        "retention_unknown_status": retention_missing.status,
        "retention_receipt_required": True,
        "raw_open_api_responses": 0,
    }


def _chaos_acceptance(fixture: dict[str, Any]) -> dict[str, Any]:
    rng = random.Random(fixture["chaos"]["seed"])
    with tempfile.TemporaryDirectory(prefix="x2n-a009-chaos-") as value:
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
        scan_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "x2n-adapters009-chaos-20"))
        adapter = TaobaoSelectedAdapter(store)
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
                raise AssertionError("Adapters009 chaos worker did not stop at the selected kill point")
            recovered = TaobaoSelectedAdapter(CanonicalStore(paths, busy_timeout_ms=30_000)).checkpoint(scan_id)
            if recovered.next_sequence != 0 or recovered.manifest_items != 0:
                raise AssertionError("Adapters009 checkpoint advanced across an uncommitted kill")

        adapter = TaobaoSelectedAdapter(CanonicalStore(paths, busy_timeout_ms=30_000))
        receipt = adapter.commit_batch(scan_id, _batch())
        replay = adapter.commit_batch(scan_id, _batch())

        connection = CanonicalStore(paths)._open(writable=False)
        try:
            content_ids = {str(row[0]) for row in connection.execute("SELECT platform_content_id FROM content")}
            relation_count = int(connection.execute("SELECT COUNT(*) FROM user_relation").fetchone()[0])
            owner_confirmed_saved_current = int(
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
        expected_ids = {f"9900000000000{index:06d}" for index in range(20)}
        if (
            content_ids != expected_ids
            or relation_count != 20
            or owner_confirmed_saved_current != 20
            or fake_relations != 0
            or observations != 20
            or receipt.identified_percent != 100.0
            or replay.disposition != "replayed"
        ):
            raise AssertionError("Adapters009 final Canonical identity or cardinality differs")
        if removed or candidates or classifications or taxonomy:
            raise AssertionError("Adapters009 deletion or taxonomy safety metric differs")
        return {
            "automatic_pagination": 0,
            "automatic_scroll": 0,
            "checkpoint_state": receipt.checkpoint_state,
            "content_auto_deletes": 0,
            "content_count": len(content_ids),
            "duplicate_side_effects": 0,
            "fake_liked_or_favorited_relations": fake_relations,
            "final_id_set_exact": True,
            "identified_item_success_percent": receipt.identified_percent,
            "kill_runs": 50,
            "lost_ids": 0,
            "observation_count": observations,
            "owner_confirmed_saved_current_relations": owner_confirmed_saved_current,
            "physical_deletes": 0,
            "relation_count": relation_count,
            "removed_relations": removed,
            "authorization_cleanup_required": receipt.authorization_cleanup_required,
            "approved_budget_units": receipt.approved_budget_units,
            "retention_receipt_sha256": receipt.retention_receipt_sha256,
            "retention_policy_ready": receipt.retention_policy_ready,
            "platform_requests": 0,
            "resume_from_durable_checkpoint": True,
            "silent_losses": 0,
            "taxonomy_mutations": taxonomy,
            "tombstone_candidates": candidates,
        }


def _blocked_state_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-a009-blocked-") as value:
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
        historical_scan = str(uuid.uuid5(uuid.NAMESPACE_URL, "x2n-adapters009-historical"))
        historical = TaobaoSelectedAdapter(store)
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
            ("retention_blocked", ErrorCode.POLICY_BLOCKED.value, True),
            ("policy_blocked", ErrorCode.POLICY_BLOCKED.value, True),
            ("empty_unverified", ErrorCode.PROVENANCE_INCOMPLETE.value, False),
            ("platform_changed", ErrorCode.PLATFORM_CHANGED.value, False),
        )
        killed = 0
        cleanup_required = 0
        for index, (status, error, should_kill) in enumerate(cases):
            selection_id = f"x2nsel_{index + 1:032x}"
            manifest_hash = f"{index + 1:064x}"
            scan_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"x2n-adapters009-blocked-{status}"))
            adapter = TaobaoSelectedAdapter(store)
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
                raise AssertionError("Adapters009 platform Kill disposition differs")
            if receipt.authorization_cleanup_required != (status == "oauth_revoked"):
                raise AssertionError("Adapters009 revocation cleanup disposition differs")
            if receipt.safe_dict()["new_requests_after_revocation"] != 0:
                raise AssertionError("Adapters009 made a request after revocation")
            killed += int(should_kill)
            cleanup_required += int(receipt.authorization_cleanup_required)

        partial_id = "x2nsel_ffffffffffffffffffffffffffffffff"
        partial_hash = "f" * 64
        partial_scan = str(uuid.uuid5(uuid.NAMESPACE_URL, "x2n-adapters009-blocked-partial"))
        partial_adapter = TaobaoSelectedAdapter(store)
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
            raise AssertionError("Adapters009 blocked states changed historical Canonical entities")
        return {
            "blocked_state_cases": 8,
            "canonical_writes": 0,
            "historical_relation_deletes": 0,
            "historical_relations_preserved": baseline["user_relation"],
            "new_requests_after_revocation": 0,
            "partial_identified_percent": partial.identified_percent,
            "platform_kills": killed,
            "authorization_cleanup_required_receipts": cleanup_required,
        }


def _rate_limit_acceptance() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="x2n-a009-rate-") as value:
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
        scan_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "x2n-adapters009-rate-limit"))
        adapter = TaobaoSelectedAdapter(store)
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
            raise AssertionError("Adapters009 Retry-After receipt differs")
        early = TaobaoSelectedIterator(_capability()).one_explicit_batch(
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
            raise AssertionError("Adapters009 retried before Retry-After")
        corrected = TaobaoSelectedIterator(_capability()).one_explicit_batch(
            _manifest(items=[_manifest()["items"][0]], count=1),  # type: ignore[index]
            observed_at=NOW + timedelta(seconds=120),
        )
        completed = adapter.commit_batch(scan_id, corrected)
        safe = completed.safe_dict()
        if completed.checkpoint_state != "complete" or completed.rate_limited or completed.relation_count != 1:
            raise AssertionError("Adapters009 explicit post-hold recovery differs")
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
        fixture.get("fixture_id") != "FIXTURE.X2N.S03.A009.001"
        or fixture.get("synthetic") is not True
        or len(fixture.get("cases", [])) != 70
    ):
        raise AssertionError("Adapters009 fixture identity or case count differs")
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
            raise AssertionError(f"Adapters009 fixture privacy boundary differs: {field}")
    capability = _capability_acceptance()
    chaos = _chaos_acceptance(fixture)
    blocked = _blocked_state_acceptance()
    rate_limit = _rate_limit_acceptance()
    unit = _run_unit_suite()
    canary = build_taobao_canary_plan()
    return {
        "acceptance_scope": "ADAPTERS_009_TAOBAO_SELECTED_CI_SYNTH",
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
        "retention_receipt": {
            "delete_revoke_flow": "UNKNOWN_DISABLED",
            "deletion_receipt": "NOT_IMPLEMENTED",
            "retention_period": "UNKNOWN_NOT_APPROVED",
            "receipt_sha256": RETENTION_HASH,
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
