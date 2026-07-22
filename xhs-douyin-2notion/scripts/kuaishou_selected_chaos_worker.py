#!/usr/bin/env python3
"""Abrupt-process worker for the public synthetic Adapters007 chaos lane."""

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

from x2n_companion.kuaishou_selected import (  # noqa: E402
    KuaishouCapabilityReceipt,
    KuaishouSelectedAdapter,
    KuaishouSelectedIterator,
)
from x2n_companion.canonical_store import CanonicalStore  # noqa: E402
from x2n_companion.runtime import RuntimePaths  # noqa: E402


NOW = datetime(2026, 7, 23, tzinfo=timezone.utc)
AUTH_HASH = "b" * 64
MANIFEST_HASH = "c" * 64
SELECTION_ID = "x2nsel_0123456789abcdef0123456789abcdef"


def _capability() -> KuaishouCapabilityReceipt:
    return KuaishouCapabilityReceipt(
        environment="ci_synthetic",
        source_kind="authorized_user_published_videos",
        policy_revision="2026-07-23",
        authorization_ref_sha256=AUTH_HASH,
        application_approved=False,
        owner_consent_active=False,
        user_video_info_granted=False,
        sanitized_transport_attested=False,
        canonical_route_attested=False,
        retention_delete_route_ready=False,
        consent_revoked=False,
        credential_material_present=False,
    )


def _manifest() -> dict[str, object]:
    items = []
    for index in range(20):
        photo_id = f"synthetic-ks-selected-{index:03d}"
        items.append(
            {
                "photo_id": photo_id,
                "canonical_page_url": f"https://www.kuaishou.com/short-video/{photo_id}",
                "content_type": "video",
                "published_at": f"2026-07-23T00:{index:02d}:00Z",
                "title": f"合成授权作品 {index:03d}",
            }
        )
    return {
        "automatic_pagination": False,
        "automatic_scroll": False,
        "error_codes": [],
        "explicit_owner_action": True,
        "has_more": True,
        "items": items,
        "owner_selection_id": SELECTION_ID,
        "page_number": 1,
        "page_size": 20,
        "platform": "kuaishou",
        "policy_revision": "2026-07-23",
        "schema_version": "1.0",
        "selected_manifest_count": 20,
        "selection_manifest_sha256": MANIFEST_HASH,
        "source_kind": "authorized_user_published_videos",
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
    batch = KuaishouSelectedIterator(_capability()).one_explicit_batch(_manifest(), observed_at=NOW)

    def abrupt_exit(label: str) -> None:
        if label == args.kill_label:
            os._exit(79)

    KuaishouSelectedAdapter(
        CanonicalStore(paths, busy_timeout_ms=30_000), fault_injector=abrupt_exit
    ).commit_batch(args.scan_id, batch)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
