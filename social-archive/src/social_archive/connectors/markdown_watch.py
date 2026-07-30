from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from ..models import CaptureRequest

URL_RE = re.compile(r"https?://[^\s<>\]\)\"']+")


class MarkdownWatchImporter:
    def __init__(self, allowed_root: Path):
        self.allowed_root = allowed_root.resolve()
        self.allowed_root.mkdir(parents=True, exist_ok=True)

    def _safe_root(self, requested: str | None) -> Path:
        root = Path(requested).resolve() if requested else self.allowed_root
        if root != self.allowed_root and self.allowed_root not in root.parents:
            raise ValueError("导入目录必须位于 SOCIAL_ARCHIVE_WATCH_ROOT 内")
        return root

    @staticmethod
    def parse_text(
        text: str,
        *,
        source_name: str,
        platform_hint: str,
        relation_type: str,
        extra_metadata: dict[str, Any] | None = None,
    ) -> CaptureRequest | None:
        front: dict[str, Any] = {}
        body = text
        if text.startswith("---\n"):
            end = text.find("\n---\n", 4)
            if end != -1:
                parsed = yaml.safe_load(text[4:end]) or {}
                if isinstance(parsed, dict):
                    front = parsed
                body = text[end+5:]
        raw_url = front.get("url") or front.get("source") or front.get("link")
        if not raw_url:
            match = URL_RE.search(body)
            raw_url = match.group(0) if match else None
        if not raw_url:
            return None
        platform = str(front.get("platform") or platform_hint)
        rel = str(front.get("relation_type") or relation_type)
        allowed = {"manual_save","bookmark","saved","favorite","like","upvoted","watch_later","history","collection"}
        if rel not in allowed:
            rel = relation_type
        return CaptureRequest(
            platform=platform, url=str(raw_url), relation_type=rel,
            title=str(front.get("title") or Path(source_name).stem), author_name=front.get("author"),
            text=body, collection_key=str(front.get("collection") or front.get("folder") or ""),
            raw_metadata={"import_path": source_name, "frontmatter": front, **(extra_metadata or {})}, requested_levels=["L0","L1","L3"]
        )

    @staticmethod
    def parse(path: Path, platform_hint: str, relation_type: str) -> CaptureRequest | None:
        return MarkdownWatchImporter.parse_text(
            path.read_text(encoding="utf-8", errors="replace"),
            source_name=path.name,
            platform_hint=platform_hint,
            relation_type=relation_type,
        )

    def scan(self, *, requested_root: str | None, platform_hint: str, relation_type: str, limit: int) -> list[CaptureRequest]:
        root = self._safe_root(requested_root)
        results: list[CaptureRequest] = []
        for path in sorted(root.rglob("*.md")):
            if path.is_symlink() or not path.is_file():
                continue
            item = self.parse(path, platform_hint, relation_type)
            if item:
                results.append(item)
            if len(results) >= limit:
                break
        return results
