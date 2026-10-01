"""事实库与候选池缓存的总量上限（研究层结束时执行；SEC 原文/正文缓存的上限在 cache_cap.py）。

- universe-cache（候选池构建时缓存的 SEC 响应与日线）：全部可再生，按「最近使用」淘汰到上限以内（cache_cap.prune_lru）；
  淘汰掉的下次构建候选池时重取，不影响当前研究用的数据（候选池快照、证据快照都不在这个目录）。
- facts.sqlite（时点事实库）：不能整库按 LRU 删。超过上限时只做两件事，且都不碰「当前研究还会读」的数据：
    1. 删除 period_end 早于 keep_from 的事实行。keep_from = min(as_of - retention_years, event_start - FACT_LOOKBACK_YEARS)。
       各分支只读近几年的财务期（TTM、同比往前 1 年、增长序列最多往前 4 年；回测与前瞻训练的最早 as_of 是 event_start 附近），
       所以 event_start 之前再多 6 年的事实永远不会被读到；retention_years 只在 as_of 远离 event_start 时更保守地扩大保留窗口。
       实体表、申报清单（filings）、摄入日志不删（体量很小，且「退市公司不删」是幸存者偏差守卫）。
    2. VACUUM 回收空页（删行不会让文件变小）；没超上限但空页占比超过 FREE_PAGE_RATIO 时也回收。
  没有一行会在「仍在读取窗口内」被删；超过上限但已无可删行时只告警，不破坏窗口。
  VACUUM 与大批量删除需要额外临时磁盘（约等于库大小），可用空间不足时整体跳过并告警，不做半截操作。
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import date
from pathlib import Path
from typing import Dict, Optional, Union

from . import cache_cap

FACTS_DEFAULT_MAX_BYTES = 2 << 30          # 2 GiB：线上现在约 1.5 GB，留出增长；超过才开始清旧期事实
UNIVERSE_CACHE_DEFAULT_MAX_BYTES = 256 << 20   # 256 MiB：线上现在约 190 MB
FACT_RETENTION_YEARS = 8
FACT_LOOKBACK_YEARS = 6                    # 分支往前读财务期的最长跨度是 4 年，再留 2 年余量
FREE_PAGE_RATIO = 0.25
DISK_HEADROOM = 1.15


def _years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


def keep_from(as_of: Union[str, date], event_start: Union[str, date], retention_years: int = FACT_RETENTION_YEARS) -> str:
    """period_end 早于它的事实行不会再被任何分支读到。"""
    as_of_day = as_of if isinstance(as_of, date) else date.fromisoformat(as_of)
    start_day = event_start if isinstance(event_start, date) else date.fromisoformat(event_start)
    return min(_years_before(as_of_day, retention_years), _years_before(start_day, FACT_LOOKBACK_YEARS)).isoformat()


def file_bytes(path: Path) -> int:
    total = 0
    for suffix in ("", "-wal", "-shm"):
        try:
            total += Path(str(path) + suffix).stat().st_size
        except OSError:
            pass
    return total


def prune_facts(path: Path, max_bytes: int, cutoff: str, *, free_bytes: Optional[int] = None, lock_timeout: float = 30.0) -> Dict[str, object]:
    """把 facts.sqlite 控制在 max_bytes 以内（见模块说明）。max_bytes <= 0 = 不处理。返回统计，全部可写进运行日志。"""
    path = Path(path)
    stats: Dict[str, object] = {"path": str(path), "max_bytes": max_bytes, "keep_from": cutoff, "deleted_rows": 0, "vacuumed": False}
    if max_bytes <= 0 or not path.is_file():
        stats["skipped"] = "disabled" if max_bytes <= 0 else "missing"
        return stats
    stats["before"] = file_bytes(path)
    try:
        connection = sqlite3.connect(str(path), timeout=lock_timeout)
    except sqlite3.Error as exc:
        stats["skipped"] = "open failed: %s" % exc
        return stats
    try:
        pages = connection.execute("PRAGMA page_count").fetchone()[0]
        free_pages = connection.execute("PRAGMA freelist_count").fetchone()[0]
        over_cap = stats["before"] > max_bytes
        wasteful = pages > 0 and free_pages / pages > FREE_PAGE_RATIO
        stats["free_page_ratio"] = round(free_pages / pages, 4) if pages else 0.0
        if not over_cap and not wasteful:
            stats["after"] = stats["before"]
            return stats
        available = free_bytes if free_bytes is not None else shutil.disk_usage(str(path.parent)).free
        if available < stats["before"] * DISK_HEADROOM:
            stats["skipped"] = "磁盘可用空间 %d 字节不足（需要约 %d）" % (available, int(stats["before"] * DISK_HEADROOM))
            stats["after"] = stats["before"]
            return stats
        if over_cap:
            cursor = connection.execute("DELETE FROM facts WHERE period_end < ?", (cutoff,))
            connection.commit()
            stats["deleted_rows"] = cursor.rowcount
        connection.execute("VACUUM")
        stats["vacuumed"] = True
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.Error as exc:               # 被写锁挡住等：下一轮再试，不影响研究结果
        stats["skipped"] = "sqlite: %s" % exc
    finally:
        connection.close()
    stats["after"] = file_bytes(path)
    stats["still_over_cap"] = stats["after"] > max_bytes
    return stats


def prune_universe_cache(directory: Path, max_bytes: int) -> Dict[str, int]:
    """候选池缓存（SEC 响应 + 日线）按最近使用淘汰到上限以内。0 = 不处理。"""
    if max_bytes <= 0:
        return {"before": 0, "after": 0, "removed_files": 0}
    return cache_cap.prune_lru([Path(directory)], max_bytes)
