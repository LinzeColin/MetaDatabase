"""无人值守的一次调度：判断时段 -> 刷新公开数据 -> 分析 -> 渲染报告 -> 发布 Release。

由 systemd timer 在原设计的 10 个北京时段（工作日 08:30-17:30，每小时半点）触发；
迟到（重启/补跑）时按“最近一个 3 小时内未跑的时段”补，报告里写的是实际运行时间。
"""

from __future__ import annotations

import fcntl
import gzip
import json
import shutil
import sqlite3
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config import Settings
from app.core.pipeline import run_slot
from app.headless import publish as pub
from app.headless import sources as src
from app.headless.refresh import DataHealth, refresh_public_data
from app.headless.report import markdown_to_html, render_release_body, render_report
from app.scheduler import SCHEDULE_SLOTS, is_business_day

CST = ZoneInfo("Asia/Shanghai")
LAST_SLOT = list(SCHEDULE_SLOTS)[-1]
KEEP_OUT_DAYS = 14


def latest_due_slot(now: datetime, catch_up_minutes: int = 180) -> str | None:
    """最近一个 scheduled_time <= now 且没超过补跑窗口的时段。"""
    local = now.astimezone(CST)
    best: str | None = None
    for slot, hhmm in SCHEDULE_SLOTS.items():
        hour, minute = (int(x) for x in hhmm.split(":"))
        scheduled = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if scheduled <= local + timedelta(minutes=2):  # 定时器可能早到几秒
            best = slot
            if local - scheduled > timedelta(minutes=catch_up_minutes):
                best = None
    return best


def _ledger_path(settings: Settings) -> Path:
    return settings.data_dir / "service_ledger.json"


def _load_ledger(settings: Settings) -> dict[str, dict[str, object]]:
    path = _ledger_path(settings)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_ledger(settings: Settings, ledger: dict[str, dict[str, object]]) -> None:
    _ledger_path(settings).write_text(json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _write_status(settings: Settings, payload: dict[str, object]) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "status.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _db_snapshot_gz(db_path: Path) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "snapshot.sqlite"
        source = sqlite3.connect(db_path)
        target = sqlite3.connect(copy)
        with target:
            source.backup(target)
        source.close()
        target.close()
        return gzip.compress(copy.read_bytes(), mtime=0)


def _prune_out_dirs(settings: Settings, today: str) -> None:
    root = settings.output_root() / "service"
    if not root.exists():
        return
    cutoff = (datetime.fromisoformat(today) - timedelta(days=KEEP_OUT_DAYS)).date().isoformat()
    for child in root.iterdir():
        if child.is_dir() and child.name < cutoff:
            shutil.rmtree(child, ignore_errors=True)


def _publish(
    settings: Settings,
    entry: dict[str, object],
    day: str,
    slot: str,
    result: dict[str, object],
    health: dict[str, object],
    ledger: dict[str, dict[str, object]],
    publisher: pub.ReleasePublisher | None,
) -> dict[str, object]:
    out_dir = Path(str(entry["out_dir"]))
    if publisher is None:
        publisher = pub.ReleasePublisher(pub.read_token(), repo=__import__("os").environ.get("SERENITY_RELEASE_REPO", pub.DEFAULT_REPO), index_path=settings.data_dir / "release_index.json")
    publisher.assert_private_repo()
    run_count = 1 + sum(1 for k, v in ledger.items() if k.startswith(day) and v.get("state") == "published" and v.get("run_id") != entry["run_id"])
    body = render_release_body(result, health, slot=slot, run_count=run_count)
    release = publisher.ensure_release(day, f"Serenity 每日分析 {day}", body)
    run_id = str(entry["run_id"])
    publisher.upload_asset(release, f"{run_id}_report.md", (out_dir / "report.md").read_bytes(), "text/markdown; charset=utf-8")
    publisher.upload_asset(release, f"{run_id}_report.html", (out_dir / "report.html").read_bytes(), "text/html; charset=utf-8")
    publisher.upload_asset(release, f"{run_id}_result.json", (out_dir / "result.json").read_bytes(), "application/json")
    if slot == LAST_SLOT:
        publisher.upload_asset(release, f"serenity_daily_{day}.sqlite.gz", _db_snapshot_gz(settings.db_path), "application/gzip")
    publisher.update_body(release, body)
    return {"release_url": release.html_url, "release_id": release.id, "tag": release.tag}


def service_tick(
    settings: Settings,
    *,
    now: datetime | None = None,
    force_slot: str | None = None,
    catch_up_minutes: int = 180,
    publish: bool = True,
    allow_duplicate: bool = False,
    client: src.HttpClient | None = None,
    publisher: pub.ReleasePublisher | None = None,
    seed_dir: Path | None = None,
) -> dict[str, object]:
    settings.ensure_dirs()
    lock = (settings.data_dir / "service.lock").open("w")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return {"action": "skipped_locked"}
    try:
        current = (now or datetime.now(CST)).astimezone(CST)
        if not force_slot and not is_business_day(current):
            return {"action": "non_business_day"}
        slot = (force_slot or latest_due_slot(current, catch_up_minutes) or "").upper()
        if not slot:
            return {"action": "no_due_slot"}
        day = current.date().isoformat()
        key = f"{day}|{slot}"
        ledger = _load_ledger(settings)
        entry = ledger.get(key)
        if entry and entry.get("state") == "published" and not allow_duplicate:
            return {"action": "skipped_duplicate", "slot": slot, "run_id": entry.get("run_id")}

        if entry and entry.get("state") == "computed" and not allow_duplicate:
            out_dir = Path(str(entry["out_dir"]))
            saved = json.loads((out_dir / "result.json").read_text(encoding="utf-8"))
            result, health_dict = saved["result"], saved["health"]
        else:
            health = refresh_public_data(settings, client=client, now=current, seed_dir=seed_dir)
            run_settings = replace(settings, candidate_universe_live_fetch_enabled=False)  # 全市场清单已在刷新阶段按日取过
            result = run_slot(run_settings, slot, dry_run=False, run_datetime_bj=current, data_health=health)
            health_dict = health.to_dict()
            run_id = str(result["run_id"])
            out_dir = settings.output_root() / "service" / day / run_id
            out_dir.mkdir(parents=True, exist_ok=True)
            markdown = render_report(result, health_dict, slot=slot)
            (out_dir / "report.md").write_text(markdown, encoding="utf-8")
            (out_dir / "report.html").write_text(markdown_to_html(markdown, f"Serenity 每日分析 {day} {slot}"), encoding="utf-8")
            (out_dir / "result.json").write_text(json.dumps({"result": result, "health": health_dict}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            entry = {"run_id": run_id, "state": "computed", "out_dir": str(out_dir), "slot": slot}
            ledger[key] = entry
            _save_ledger(settings, ledger)

        summary: dict[str, object] = {
            "action": "ran",
            "slot": slot,
            "run_id": entry["run_id"],
            "status": result["status"],
            "data_quality_status": result["data_quality_status"],
            "top5": result["top5"],
            "candidate_count": result["candidate_count"],
            "data_health": health_dict.get("status"),
            "latest_nav_date": health_dict.get("latest_nav_date"),
        }
        if publish:
            summary.update(_publish(settings, entry, day, slot, result, health_dict, ledger, publisher))
            entry["state"] = "published"
            ledger[key] = entry
            _save_ledger(settings, ledger)
            summary["published"] = True
        _write_status(settings, {**summary, "finished_at": datetime.now(CST).isoformat(timespec="seconds")})
        _prune_out_dirs(settings, day)
        return summary
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()
