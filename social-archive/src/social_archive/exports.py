from __future__ import annotations

import csv
import html
import io
import json
from pathlib import Path
from typing import Any

from .db import RuntimeStore
from .utils import atomic_write, clean_display_author, safe_slug, sha256_bytes, utcnow


class StandardExporter:
    """Create portable, deterministic projections without changing Canonical facts."""

    def __init__(self, store: RuntimeStore, output_root: Path):
        self.store = store
        self.output_root = output_root.resolve()

    @staticmethod
    def _metadata(item: dict[str, Any]) -> dict[str, Any]:
        raw = item.get("metadata_json")
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            return {}
        try:
            parsed = json.loads(raw)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @classmethod
    def _jsonl_record(cls, item: dict[str, Any]) -> dict[str, Any]:
        """Keep the public export stable and sufficient for another importer."""
        return {
            "schema_version": "1.0",
            "content_id": item["id"],
            "canonical_url": item["canonical_url"],
            "platform": item["platform"],
            "title": item.get("title"),
            "author_name": clean_display_author(item.get("author_name")) or None,
            "text": item.get("body"),
            "published_at": item.get("published_at"),
            "first_observed_at": item.get("first_observed_at"),
            "last_observed_at": item.get("last_observed_at"),
            "relation_type": item.get("relation_type"),
            "collection_key": item.get("collection_key") or None,
            "relation_status": item.get("relation_status"),
            "artifact_count": int(item.get("artifact_count") or 0),
            "verified_replica_count": int(item.get("verified_replica_count") or 0),
            "metadata": cls._metadata(item),
        }

    @staticmethod
    def _write_if_changed(path: Path, data: bytes) -> bool:
        try:
            if path.read_bytes() == data:
                return False
        except FileNotFoundError:
            pass
        atomic_write(path, data)
        if path.read_bytes() != data:
            raise OSError(f"标准导出写入后回读不一致：{path}")
        return True

    def _items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        offset = 0
        while True:
            page = self.store.list_library(limit=500, offset=offset)
            if not page:
                break
            items.extend(page)
            offset += len(page)
            if len(page) < 500:
                break
        # list_library is presentation-ordered.  A portable export must keep a
        # deterministic order even when two rows have the same observation time.
        items = sorted(items, key=lambda item: str(item["id"]))
        bodies = self.store.content_bodies([str(item["id"]) for item in items])
        for item in items:
            item["body"] = bodies.get(str(item["id"]), "")
        return items

    def _previous_manifest(self) -> dict[str, Any]:
        path = self.output_root / "EXPORT_MANIFEST.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    def export_all(self) -> dict[str, str | int]:
        items = self._items()
        self.output_root.mkdir(parents=True, exist_ok=True)
        vault = self.output_root / "obsidian-vault"
        vault.mkdir(parents=True, exist_ok=True)
        changed_files = 0
        attempted_files = 0

        for item in items:
            title = item.get("title") or item["id"]
            front = {
                "id": item["id"],
                "platform": item["platform"],
                "url": item["canonical_url"],
                "relation_type": item.get("relation_type"),
                "collection": item.get("collection_key"),
                "author": clean_display_author(item.get("author_name")) or None,
                "saved_at": item.get("last_observed_at"),
                "artifact_count": item.get("artifact_count", 0),
            }
            body = str(item.get("body") or "").strip()
            lines = [
                "---",
                *[f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in front.items()],
                "---",
                "",
                f"# {title}",
                "",
                f"原始链接：{item['canonical_url']}",
            ]
            if body:
                lines.extend(["", body])
            path = vault / f"{safe_slug(str(title), item['id'])}-{item['id'][-8:]}.md"
            attempted_files += 1
            changed_files += self._write_if_changed(path, ("\n".join(lines) + "\n").encode("utf-8"))

        jsonl_bytes = b"".join(
            (
                json.dumps(self._jsonl_record(item), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            ).encode("utf-8")
            for item in items
        )
        snapshot_sha256 = sha256_bytes(jsonl_bytes)

        csv_path = self.output_root / "notion-import.csv"
        csv_buffer = io.StringIO(newline="")
        writer = csv.DictWriter(
            csv_buffer,
            fieldnames=["标题", "平台", "关系", "收藏夹", "作者", "原始链接", "最近观察", "制品数", "内容ID"],
        )
        writer.writeheader()
        for item in items:
            writer.writerow(
                {
                    "标题": item.get("title") or "",
                    "平台": item["platform"],
                    "关系": item.get("relation_type") or "",
                    "收藏夹": item.get("collection_key") or "",
                    "作者": clean_display_author(item.get("author_name")),
                    "原始链接": item["canonical_url"],
                    "最近观察": item.get("last_observed_at") or "",
                    "制品数": item.get("artifact_count", 0),
                    "内容ID": item["id"],
                }
            )
        csv_bytes = ("\ufeff" + csv_buffer.getvalue()).encode("utf-8")
        attempted_files += 1
        changed_files += self._write_if_changed(csv_path, csv_bytes)

        bookmark_lines = [
            "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
            '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
            "<TITLE>Social Archive</TITLE>",
            "<H1>Social Archive</H1>",
            "<DL><p>",
        ]
        for item in items:
            title = html.escape(str(item.get("title") or item["canonical_url"]))
            url = html.escape(str(item["canonical_url"]), quote=True)
            tags = html.escape(
                ",".join(
                    filter(
                        None,
                        [str(item.get("platform") or ""), str(item.get("relation_type") or ""), str(item.get("collection_key") or "")],
                    )
                ),
                quote=True,
            )
            bookmark_lines.append(f'<DT><A HREF="{url}" TAGS="{tags}">{title}</A>')
        bookmark_lines.append("</DL><p>")
        static_outputs = {
            "library.jsonl": jsonl_bytes,
            "bookmarks.html": ("\n".join(bookmark_lines) + "\n").encode("utf-8"),
            "archivebox-urls.txt": (
                "\n".join(sorted({str(item["canonical_url"]) for item in items})) + "\n"
            ).encode("utf-8"),
            "feed.json": (
                json.dumps(
                    {
                        "version": "https://jsonfeed.org/version/1.1",
                        "title": "Social Archive",
                        "home_page_url": "https://social-archive.linzezhang.com",
                        "items": [
                            {
                                "id": item["id"],
                                "url": item["canonical_url"],
                                "title": item.get("title") or item["canonical_url"],
                                "date_modified": item.get("last_observed_at"),
                                "tags": [
                                    value
                                    for value in [item.get("platform"), item.get("relation_type"), item.get("collection_key")]
                                    if value
                                ],
                            }
                            for item in items
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            ).encode("utf-8"),
        }
        for name, data in static_outputs.items():
            attempted_files += 1
            changed_files += self._write_if_changed(self.output_root / name, data)

        previous = self._previous_manifest()
        generated_at = previous.get("generated_at") if previous.get("snapshot_sha256") == snapshot_sha256 else utcnow()
        manifest = {
            "schema_version": "1.1",
            "generated_at": generated_at,
            "snapshot_sha256": snapshot_sha256,
            "item_count": len(items),
            "outputs": [
                "obsidian-vault/",
                "library.jsonl",
                "notion-import.csv",
                "bookmarks.html",
                "archivebox-urls.txt",
                "feed.json",
            ],
            "archivewebpage_import": "把 .wacz 放入 wacz-import/，运行 scripts/import_wacz.py 登记 L2 制品。",
        }
        attempted_files += 1
        changed_files += self._write_if_changed(
            self.output_root / "EXPORT_MANIFEST.json",
            (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
        return {
            "status": "done" if changed_files else "noop",
            "item_count": len(items),
            "changed_files": changed_files,
            "noop_files": attempted_files - changed_files,
            "output_root": str(self.output_root),
        }
