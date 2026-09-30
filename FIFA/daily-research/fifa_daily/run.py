"""一次运行：抓数据 -> 出报告 -> 写站点目录。失败时如实写状态，绝不拿旧数据冒充新的。

站点目录（--site）里的文件：
  index.html / latest.json / status.json     首页、最新报告、机器可读状态
  archive/YYYY-MM-DD.{html,json}             每天一份存档（保留 60 天）
  data/ledger.json                           预测账本（赛前预测冻结 + 赛后打分）
  data/runs.json                             运行记录（第一屏的 14 天条带、缺跑判断）
  data/backtest.json                         回测缓存（一天算一次）
  data/matches-cache.json.gz                 上次成功抓取的比赛（上游临时失败时降级用，会在页面上标明）
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config, sources
from .backtest import walk_forward
from .build import SYD, build
from .dataset import prepare
from .render import render, render_empty

ARCHIVE_KEEP_DAYS = 60
RUNS_KEEP = 240


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _save(path: Path, obj, *, indent: int | None = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=indent)
    if not path.exists() or path.read_text(encoding="utf-8") != text:  # 内容没变就不动文件，避免无谓的提交
        path.write_text(text, encoding="utf-8")


def _load_cache(path: Path) -> dict:
    try:
        return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
    except (OSError, ValueError):
        return {"updated_at": None, "sources": {}}


def _save_cache(path: Path, cache: dict) -> None:
    data = gzip.compress(json.dumps(cache, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"), mtime=0)
    if not path.exists() or path.read_bytes() != data:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def apply_cache(raw: dict, cache: dict, now: datetime) -> list[str]:
    """失败的来源如果有缓存就用缓存并标明；成功的来源刷新缓存。返回要显示在第一屏的降级说明。"""
    degraded: list[str] = []
    changed = False
    for name, info in raw["sources"].items():
        cached = cache["sources"].get(name)
        if info.get("ok") and not info.get("absent"):
            rows = raw["by_source"][name]
            if cached != {"matches": rows}:
                cache["sources"][name] = {"matches": rows}
                changed = True
        elif not info.get("ok") and cached:
            raw["by_source"][name] = cached["matches"]
            info["stale_cache_from"] = cache.get("updated_at") or "未知"
            info["ok"] = True
            degraded.append(f"数据源 {name} 本次抓取失败（{info.get('error', '')[:80]}），已改用上次成功抓取的缓存（缓存更新于 "
                            f"{info['stale_cache_from']}），该部分数据可能不是最新。")
    if changed:
        cache["updated_at"] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    raw["matches"] = [m for rows in raw["by_source"].values() for m in rows]
    return degraded


def core_problem(raw: dict) -> str | None:
    """没有这些就没法出可信的报告。"""
    need = [f"openfootball:{c}:{config.CURRENT_SEASON}" for c in config.REPORT_COMPS if c != "uefa.cl"]
    for n in need:
        info = raw["sources"].get(n, {})
        if not info.get("ok") or info.get("absent"):
            return f"核心数据源不可用：{n}（{info.get('error', '上游没有该文件')}）"
    if not any(raw["sources"].get(f"openfootball:uefa.cl:{s}", {}).get("ok") for s in config.CL_TXT_SEASONS):
        return "欧冠历史数据全部不可用，无法把各联赛的强弱连起来"
    return None


def run_strip(runs: list[dict], today: str) -> tuple[list[dict], list[str]]:
    ok_days = {r["date"] for r in runs if r["ok"]}
    fail_days = {r["date"] for r in runs if not r["ok"]}
    first = min((r["date"] for r in runs), default=today)
    t = datetime.fromisoformat(today).date()
    strip, missed = [], []
    for i in range(13, -1, -1):
        d = (t - timedelta(days=i)).isoformat()
        if d in ok_days:
            strip.append({"date": d, "state": "ok", "label": "成功"})
        elif d in fail_days:
            strip.append({"date": d, "state": "fail", "label": "只有失败的运行"})
        elif d >= first and d != today:
            strip.append({"date": d, "state": "miss", "label": "缺跑"})
            missed.append(d)
        elif d == today:
            strip.append({"date": d, "state": "none", "label": "今天（等待/运行中）"})
        else:
            strip.append({"date": d, "state": "none", "label": "更早，无记录"})
    return strip, missed


def _write_site(site: Path, report: dict, status: dict, archive: bool = False) -> None:
    (site / "index.html").write_text(render(report, status), encoding="utf-8")


def run(site: Path, now: datetime, *, raw: dict | None = None, skip_backtest: bool = False) -> int:
    data = site / "data"
    runs = _load(data / "runs.json", [])
    ledger = _load(data / "ledger.json", {"entries": {}})
    cache = _load_cache(data / "matches-cache.json.gz")
    prev_status = _load(site / "status.json", {})
    today = now.astimezone(SYD).date().isoformat()

    error: str | None = None
    degraded: list[str] = []
    report = None
    try:
        raw = raw or sources.fetch_all()
        degraded = apply_cache(raw, cache, now)
        error = core_problem(raw)
        if error is None:
            bt_cache = _load(data / "backtest.json", {})
            backtest = bt_cache.get("result")
            if not skip_backtest and bt_cache.get("computed_on") != today:
                try:
                    ds = prepare(raw["matches"])
                    backtest = walk_forward(ds, set(config.REPORT_COMPS), (now.date() + timedelta(days=0)).isoformat())
                    _save(data / "backtest.json", {"computed_on": today, "result": backtest})
                except Exception as exc:  # 回测失败不该拦住日报，但要说出来
                    degraded.append(f"回测本次没算成（{type(exc).__name__}: {str(exc)[:80]}），成绩单沿用上次结果。")
            report, ledger = build(raw, now, ledger, backtest)
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:200]}"
        traceback.print_exc()

    ok = error is None and report is not None
    runs.append({"at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "date": today, "ok": ok, "note": (error or "")[:200]})
    runs = runs[-RUNS_KEEP:]
    strip, missed = run_strip(runs, today)
    status = {
        "ok": ok, "today": today, "last_attempt_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "error": error, "degraded": degraded, "missed_days": missed, "strip": strip,
        "last_success_at": now.strftime("%Y-%m-%dT%H:%M:%SZ") if ok else prev_status.get("last_success_at"),
        "report_date": report["report_date"] if ok else prev_status.get("report_date"),
        "stale_after_hours": config.STALE_AFTER_HOURS,
    }
    # 本次失败，但今天早些时候已经成功出过报告：首页仍算「今天有新报告」，同时如实说明最近一次刷新失败
    status["fresh_today"] = ok or (prev_status.get("report_date") == today and prev_status.get("ok") is not None
                                   and (site / "latest.json").exists())

    _save(data / "runs.json", runs)
    _save_cache(data / "matches-cache.json.gz", cache)
    if ok:
        _save(data / "ledger.json", ledger)
        _save(site / "latest.json", report, indent=None)
        _save(site / "archive" / f"{report['report_date']}.json", report, indent=None)
        page = render(report, status)
        (site / "index.html").write_text(page, encoding="utf-8")
        arch_status = {**status, "today": report["report_date"]}
        (site / "archive" / f"{report['report_date']}.html").write_text(render(report, arch_status, archive=True), encoding="utf-8")
        cutoff = (now - timedelta(days=ARCHIVE_KEEP_DAYS)).strftime("%Y-%m-%d")
        for f in (site / "archive").glob("*.*"):
            if f.stem < cutoff:
                f.unlink()
    else:
        old = _load(site / "latest.json", None)
        (site / "index.html").write_text(render(old, status) if old else render_empty(status), encoding="utf-8")
    _save(site / "status.json", status, indent=1)
    print(f"[fifa-daily] ok={ok} date={today} error={error} degraded={len(degraded)} "
          f"fixtures={len(report['fixtures']) if report else '-'}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fifa_daily")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="生成日报并写入站点目录")
    r.add_argument("--site", required=True, type=Path)
    r.add_argument("--now", help="覆盖当前时间（UTC ISO，测试用）")
    r.add_argument("--skip-backtest", action="store_true")
    args = ap.parse_args(argv)
    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
    return run(args.site, now, skip_backtest=args.skip_backtest)


if __name__ == "__main__":
    sys.exit(main())
