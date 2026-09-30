"""原文缓存上限：研究层结束时把 SEC 原文缓存与正文缓存按「最近使用」淘汰到总量上限以内（默认 1 GiB）。

只淘汰可再生的缓存（SEC 响应与抽出的正文）；事实库、事件库、行情、抽取结果（structure-cache，小 JSON）、
证据快照与记分簿不在此列。一份缓存对象可能有多个文件（正文 + .meta.json），按「第一个点之前的名字」成组，整组一起淘汰。
"最近使用"取 max(atime, mtime)；缓存命中时读取端会显式 touch，不依赖文件系统的 atime 策略。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

DEFAULT_MAX_BYTES = 1 << 30


def touch(path: Path) -> None:
    """缓存命中时标记「最近使用」；失败（只读等）不影响读取。"""
    try:
        os.utime(path, None)
    except OSError:
        pass


def _group_key(path: Path) -> Tuple[str, str]:
    return str(path.parent), path.name.split(".", 1)[0]


def prune_lru(directories: Iterable[Path], max_bytes: int = DEFAULT_MAX_BYTES) -> Dict[str, int]:
    """把 directories 下所有缓存文件合计淘汰到 <= max_bytes。返回 {"before", "after", "removed_files"}（字节数）。"""
    groups: Dict[Tuple[str, str], List[Path]] = {}
    for directory in directories:
        root = Path(directory)
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                groups.setdefault(_group_key(path), []).append(path)
    entries = []
    total = 0
    for files in groups.values():
        size, used = 0, 0.0
        for file in files:
            try:
                stat = file.stat()
            except OSError:
                continue
            size += stat.st_size
            used = max(used, stat.st_atime, stat.st_mtime)
        entries.append((used, size, files))
        total += size
    before, removed = total, 0
    for used, size, files in sorted(entries, key=lambda item: item[0]):
        if total <= max_bytes:
            break
        for file in files:
            try:
                file.unlink()
                removed += 1
            except OSError:
                pass
        total -= size
    return {"before": before, "after": total, "removed_files": removed}
