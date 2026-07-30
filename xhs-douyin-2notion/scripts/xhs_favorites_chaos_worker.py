#!/usr/bin/env python3
"""Private-process worker used only by the public synthetic Adapters002 chaos lane."""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


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


NOW = datetime(2026, 7, 23, tzinfo=timezone.utc)


def _item(index: int) -> XhsFavoriteItem:
    collection = index % 2
    return XhsFavoriteItem(
        content_id=f"synth_xhs_favorite_{index:03d}",
        content_type="image_gallery" if index % 2 == 0 else "video",
        title=f"合成收藏条目 {index:03d}",
        collection_id=f"collection_{collection}",
        collection_name_private=f"合成收藏夹 {collection}",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan-id", required=True)
    parser.add_argument("--sequence", type=int, required=True, choices=range(5))
    parser.add_argument("--kill-label", required=True)
    args = parser.parse_args()
    parsed = uuid.UUID(args.scan_id)
    if str(parsed) != args.scan_id:
        return 2
    paths = RuntimePaths.from_environment(repository_root=PROJECT_ROOT, create=False)
    store = CanonicalStore(paths, busy_timeout_ms=30_000)
    items = tuple(_item(index) for index in range(args.sequence * 20, args.sequence * 20 + 20))
    batch = XhsFavoritesBatch(
        sequence=args.sequence,
        status="ready",
        completion_signal="authoritative_end" if args.sequence == 4 else "more_available",
        visible_card_count=20,
        items=items,
        error_codes=(),
        observed_at=NOW + timedelta(minutes=args.sequence),
    )

    def abrupt_exit(label: str) -> None:
        if label == args.kill_label:
            os._exit(79)

    XhsFavoritesAdapter(store, fault_injector=abrupt_exit).commit_batch(args.scan_id, batch)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
