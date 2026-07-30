from __future__ import annotations

import io
import stat
import zipfile
from pathlib import PurePosixPath

from ..models import CaptureRequest
from .markdown_watch import MarkdownWatchImporter


class SocialArchiverBundleImporter:
    MAX_BUNDLE_BYTES = 200 * 1024 * 1024
    MAX_ENTRY_BYTES = 20 * 1024 * 1024
    MAX_TOTAL_MARKDOWN_BYTES = 200 * 1024 * 1024
    MAX_ENTRIES = 10_000

    def parse_zip(
        self,
        payload: bytes,
        *,
        bundle_name: str,
        platform_hint: str,
        relation_type: str,
        limit: int,
    ) -> list[CaptureRequest]:
        if not payload or len(payload) > self.MAX_BUNDLE_BYTES:
            raise ValueError("导入包为空或超过 200 MiB")
        stream = io.BytesIO(payload)
        if not zipfile.is_zipfile(stream):
            raise ValueError("只接受 Social Archiver/Markdown ZIP 导出包")
        stream.seek(0)
        captures: list[CaptureRequest] = []
        total = 0
        with zipfile.ZipFile(stream) as archive:
            infos = archive.infolist()
            if len(infos) > self.MAX_ENTRIES:
                raise ValueError("ZIP 条目过多")
            for info in infos:
                name = info.filename.replace("\\", "/")
                pure = PurePosixPath(name)
                mode = (info.external_attr >> 16) & 0xFFFF
                if pure.is_absolute() or ".." in pure.parts or stat.S_ISLNK(mode):
                    raise ValueError("ZIP 包含不安全路径或符号链接")
                if info.is_dir() or not name.lower().endswith(".md"):
                    continue
                if info.flag_bits & 0x1:
                    raise ValueError("不接受加密 ZIP；请先在本地解压后重新打包")
                if info.file_size > self.MAX_ENTRY_BYTES:
                    raise ValueError("单个 Markdown 超过 20 MiB")
                total += info.file_size
                if total > self.MAX_TOTAL_MARKDOWN_BYTES:
                    raise ValueError("Markdown 解压总量超过 200 MiB")
                text = archive.read(info).decode("utf-8", errors="replace")
                item = MarkdownWatchImporter.parse_text(
                    text,
                    source_name=name,
                    platform_hint=platform_hint,
                    relation_type=relation_type,
                    extra_metadata={"import_bundle": bundle_name, "import_entry": name, "import_format": "social_archiver_zip"},
                )
                if item:
                    captures.append(item)
                if len(captures) >= limit:
                    break
        if not captures:
            raise ValueError("ZIP 中没有可识别 URL 的 Markdown 内容")
        return captures
