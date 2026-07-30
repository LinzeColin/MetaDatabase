from __future__ import annotations

import argparse
import json
from pathlib import Path

from social_archive.config import Settings
from social_archive.db import RuntimeStore
from social_archive.storage import ContentAddressedStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("content_id")
    parser.add_argument("wacz")
    args = parser.parse_args()
    settings = Settings.from_env()
    settings.ensure_directories()
    if not settings.l2_enabled:
        print(json.dumps({"status": "BLOCKED_BY_DEFAULT", "message": "L2 默认关闭。显式设置 SOCIAL_ARCHIVE_L2_ENABLED=true 后重跑。"}, ensure_ascii=False))
        return 3

    store = RuntimeStore(settings.runtime_db)
    store.initialize()
    if not store.get_content(args.content_id):
        print(json.dumps({"status": "CONTENT_NOT_FOUND", "message": "内容不存在，未导入 WACZ 文件。"}, ensure_ascii=False))
        return 2

    try:
        obj = ContentAddressedStore(settings.staging_root / "objects").import_file(
            Path(args.wacz), media_type="application/wacz"
        )
    except (FileNotFoundError, ValueError) as exc:
        print(json.dumps({"status": "INVALID_WACZ_INPUT", "message": str(exc)}, ensure_ascii=False))
        return 2
    artifact_id = store.add_artifact(
        content_id=args.content_id,
        archive_level="L2",
        artifact_type="wacz",
        sha256=obj.sha256,
        byte_size=obj.byte_size,
        media_type=obj.media_type,
        local_path=str(obj.path),
    )
    print(json.dumps({"status": "PASS", "artifact_id": artifact_id, "sha256": obj.sha256}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
