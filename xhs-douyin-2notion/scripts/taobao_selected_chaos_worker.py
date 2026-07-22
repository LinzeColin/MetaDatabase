#!/usr/bin/env python3
"""Abrupt-process worker for the public synthetic Adapters009 chaos lane."""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "apps/companion/src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages/contracts/src"))

from x2n_companion.taobao_selected import (  # noqa: E402
    TaobaoCapabilityReceipt,
    TaobaoSelectedAdapter,
    TaobaoSelectedIterator,
)
from x2n_companion.canonical_store import CanonicalStore  # noqa: E402
from x2n_companion.runtime import RuntimePaths  # noqa: E402


NOW = datetime(2026, 7, 23, tzinfo=timezone.utc)
AUTH_HASH = "b" * 64
PRICE_HASH = "d" * 64
QUOTA_HASH = "e" * 64
RETENTION_HASH = "f" * 64
MANIFEST_HASH = "c" * 64
SELECTION_ID = "x2nsel_0123456789abcdef0123456789abcdef"


def _capability() -> TaobaoCapabilityReceipt:
    return TaobaoCapabilityReceipt(
        environment="ci_synthetic",
        source_kind="owner_explicit_item_ids_for_authorized_item_get",
        policy_revision="2026-07-23",
        authorization_ref_sha256=AUTH_HASH,
        pricing_ref_sha256=PRICE_HASH,
        quota_ref_sha256=QUOTA_HASH,
        retention_ref_sha256=RETENTION_HASH,
        application_approved=False,
        owner_oauth_active=False,
        item_get_scope_granted=False,
        pricing_confirmed=False,
        quota_confirmed=False,
        approved_budget_units=0,
        projected_cost_units=None,
        remaining_quota_requests=None,
        official_top_transport_attested=False,
        sanitized_transport_attested=False,
        local_only_storage_attested=False,
        canonical_route_attested=False,
        purpose_scope_disclosure_approved=False,
        retention_period_approved=False,
        delete_revoke_flow_ready=False,
        deletion_receipt_ready=False,
        authorization_revoked=False,
        credential_material_present=False,
    )


def _manifest() -> dict[str, object]:
    items = []
    for index in range(20):
        num_iid = f"9900000000000{index:06d}"
        items.append(
            {
                "num_iid": num_iid,
                "title": f"合成淘宝选定商品 {index:03d}",
            }
        )
    return {
        "automatic_pagination": False,
        "automatic_scroll": False,
        "error_codes": [],
        "explicit_owner_action": True,
        "has_more": True,
        "http_status": None,
        "items": items,
        "owner_selection_id": SELECTION_ID,
        "page_number": 1,
        "page_size": 20,
        "platform": "taobao",
        "policy_revision": "2026-07-23",
        "retry_after": None,
        "schema_version": "1.0",
        "selected_manifest_count": 20,
        "selection_manifest_sha256": MANIFEST_HASH,
        "source_kind": "owner_explicit_item_ids_for_authorized_item_get",
        "status": "ready",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan-id", required=True)
    parser.add_argument("--kill-label", required=True)
    args = parser.parse_args()
    parsed = uuid.UUID(args.scan_id)
    if str(parsed) != args.scan_id:
        return 2
    paths = RuntimePaths.from_environment(repository_root=PROJECT_ROOT, create=False)
    batch = TaobaoSelectedIterator(_capability()).one_explicit_batch(_manifest(), observed_at=NOW)

    def abrupt_exit(label: str) -> None:
        if label == args.kill_label:
            os._exit(79)

    TaobaoSelectedAdapter(CanonicalStore(paths, busy_timeout_ms=30_000), fault_injector=abrupt_exit).commit_batch(
        args.scan_id, batch
    )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
