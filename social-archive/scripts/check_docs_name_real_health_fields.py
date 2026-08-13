#!/usr/bin/env python3
r"""文档点名的 `/health` 字段，必须真的在 `/health` 里（2026-08-14）。

## 它修的是什么

整个交接策略压在四个字段名上。`HANDOFF.md` 的可粘提示词写着：

    curl -s https://social-archive-api.linzezhang.com/health
    看 version / worker.alive / backup.stale / replication.stale（后两个要是 false）

接手的人（或 AI）不会去读源码，**他只会照着这几个名字去找**。名字一旦漂了：

  · `json.get("stale")` 对不存在的字段返回 `None`
  · 打印出来是 `None`，和「系统坏了」长得一模一样
  · 更糟的方向：他看到 `None` 不等于 `True`，于是判「没 stale，正常」——
    **一条真的停摆会被读成健康**

不是假想。2026-08-14 我自己按猜的字段名（`last_snapshot` / `last`）读生产，
两条链都印出 `last=None`，我差点写进结论；真名是 `last_backup_at` / `last_run_at`，
而且两条链**字段名和时间格式都不一样**（紧凑 `20260813T085049Z` vs ISO 带微秒）。
我读的是自己五小时前刚写的那格，照样读错。

## 已有的门都盖不住这一格

  test_every_health_field_is_read_by_something.py   反方向（每格都得有人读），且**只查顶层**
  check_docs_match_the_ui.py                        只扫 `ROOT/docs`，**HANDOFF.md 在仓根，它一个字没看过**
  check_docs_point_at_things_that_exist.py          只查文档提到的 `scripts/xxx` 在不在磁盘上

文档点名的是**嵌套**字段（`backup.stale`），三道门没有一道查这个方向。

## 口径（写出来，免得被当成覆盖了全部）

- **只查值是 dict 的顶层键。** 标量键（`version`、`status`、`project` 之类）跳过，
  因为 `/v1/status` 是**另一个端点**，文档里 `status.storage` 说的是它，
  在这里查会造出假红。少查一档是自觉的取舍，不是疏忽。
- 后缀落在 `IGNORED_SUFFIXES` 里的不算字段引用：`social-archive-backup.timer`
  的尾巴会被 `\b` 切成 `backup.timer`，`backup.sh` 同理。
- 不扫 `CHANGELOG.md` 和 `evidence/`：那里按设计留着历史上的旧字段名，
  查它会造出一个**永远变不绿的红**，而永远红的灯和坏掉的灯长得一样。
- 扫描集用 `git ls-files -z`：这个仓有 `docs/使用说明.md` 这种非 ASCII 路径，
  不带 `-z` 时 git 会给它套引号，open 直接失败而判据照样绿。

## 底线计数

写这道门之前先预测过：HANDOFF.md 三行里已知 7 处引用。所以设了 `FLOOR = 7`——
**扫出来少于 7 处就判自己坏了**，而不是判文档干净。没有这条底线时，
一个把扫描集砍空的改动会让这道门安静地全绿。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 这些后缀不是字段名，是文件名/systemd 单元名的尾巴。
IGNORED_SUFFIXES = {
    "sh", "py", "js", "mjs", "md", "json", "html", "css", "txt", "log",
    "yml", "yaml", "env", "sqlite", "db", "zip", "png", "svg", "ini", "toml",
    "timer", "service", "socket", "target", "mount", "path",
    "com", "cn", "org", "net", "io", "dev",  # 域名尾巴
}

SKIPPED_DOCS = {"CHANGELOG.md"}
SKIPPED_DIRS = ("evidence/",)

FLOOR = 7


def _health_in_state(build) -> dict:
    """在进程内起真 app 拿一次 `/health`；`build(data_root)` 先把状态造出来。

    必须走真接口：要验的正是「这个端点实际下发什么字段」，
    照着源码里的字面量重抄一遍等于两边共用同一个错。
    """
    tmp = tempfile.mkdtemp(prefix="sa-health-schema-")
    root = Path(tmp) / "data"
    pwa = Path(tmp) / "pwa"
    pwa.mkdir(parents=True)
    (pwa / "index.html").write_text("ok", encoding="utf-8")
    root.mkdir(parents=True, exist_ok=True)
    build(root)
    for key, value in {
        "SOCIAL_ARCHIVE_DATA_ROOT": root,
        "SOCIAL_ARCHIVE_RUNTIME_DB": root / "db.sqlite",
        "SOCIAL_ARCHIVE_STAGING_ROOT": root / "staging",
        "SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT": root / "private",
        "SOCIAL_ARCHIVE_WATCH_ROOT": root / "import",
        "SOCIAL_ARCHIVE_PWA_ROOT": pwa,
    }.items():
        os.environ[key] = str(value)

    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    import importlib  # noqa: PLC0415

    from fastapi.testclient import TestClient  # noqa: PLC0415
    import social_archive.api as api  # noqa: PLC0415

    importlib.reload(api)
    response = TestClient(api.app).get("/health")
    if response.status_code != 200:
        raise SystemExit(f"**不合格** /health 起不来：HTTP {response.status_code}")
    return response.json()


def _healthy_state(root: Path) -> None:
    """两条链都跑成过的样子。"""
    import json as _json  # noqa: PLC0415

    for chain in ("private-database", "runtime-db"):
        snapshot = root / "backups" / chain / "20260814T030000Z"
        snapshot.mkdir(parents=True)
        (snapshot / "manifest.json").write_text("{}", encoding="utf-8")
    (root / "status").mkdir(parents=True, exist_ok=True)
    (root / "status/object-replication.json").write_text(
        _json.dumps({"generated_at": "2026-08-14T03:05:00Z", "status": "PASS"}),
        encoding="utf-8")


def _live_health() -> dict:
    """拿 `/health` 的字段表——**要观测两种状态，不是一种。**

    2026-08-14 这道门第一版只起了一个空数据根，于是量到的是「什么都没跑过」
    那一支的键集。当时两条链的分支键集不一样：

      · `backup` 的降级支多一个 `why`      → 文档写 `backup.why` 会被**放行**，
                                             而生产上（正常支）根本取不到
      · `replication` 的降级支**少** `hours_since`/`message_zh`
                                           → 文档写这两个会被**报成不存在**（假红）

    一次观测同时造出了假阴和假阳。产品那侧已经改成键集恒定，
    但「恒定」不能靠记得——所以这里主动观测两种状态并**断言键集相同**，
    把这道门自己的前提变成它自己检查的东西。
    """
    empty = _health_in_state(lambda root: None)
    healthy = _health_in_state(_healthy_state)

    drift = []
    for key, value in empty.items():
        if not isinstance(value, dict):
            continue
        other = healthy.get(key)
        if not isinstance(other, dict):
            drift.append(f"{key}：空状态下是对象，正常状态下不是")
            continue
        if set(value) != set(other):
            only_empty = "、".join(sorted(set(value) - set(other))) or "无"
            only_ok = "、".join(sorted(set(other) - set(value))) or "无"
            drift.append(
                f"{key}：键集随状态变。只在降级时有：{only_empty}；只在正常时有：{only_ok}")
    if drift:
        print("**不合格** /health 的字段表取决于当时是哪一支，"
              "这道门没法用一份 schema 去核对文档：")
        for line in drift:
            print(f"  · {line}")
        print("\n  修法是让所有分支返回同样的键（没有值的给空串/None），"
              "\n  而不是在这里挑一支来信。")
        raise SystemExit(1)

    return healthy


# git 钩子会把 GIT_DIR 之类塞进环境，子进程继承之后会去问**那个**仓，
# `cwd=` 压不过它——单独跑绿、在 pre-commit 里跑红，而且不偶发，是必错。
# 这几个名字照抄 check_docs_point_at_things_that_exist.py。
_LEAKED_BY_GIT_HOOKS = ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE",
                        "GIT_COMMON_DIR", "GIT_PREFIX", "GIT_OBJECT_DIRECTORY")


def _markdown_files() -> list[Path]:
    environment = {k: v for k, v in os.environ.items() if k not in _LEAKED_BY_GIT_HOOKS}
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.md"],
        cwd=ROOT, env=environment, capture_output=True, text=True, check=True,
    ).stdout
    files = []
    for name in out.split("\0"):
        if not name:
            continue
        if Path(name).name in SKIPPED_DOCS:
            continue
        if any(name.startswith(d) for d in SKIPPED_DIRS):
            continue
        files.append(ROOT / name)
    return files


def main() -> int:
    health = _live_health()
    objects = {k: v for k, v in health.items() if isinstance(v, dict)}
    if not objects:
        print("**不合格** /health 里一个对象字段都没有——判据自己该重写了")
        return 1

    pattern = re.compile(
        r"\b(" + "|".join(sorted(map(re.escape, objects))) + r")\.([A-Za-z_][A-Za-z0-9_]*)"
    )

    checked = 0
    problems: list[str] = []
    docs = _markdown_files()
    for path in docs:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:                      # 读不出来 ≠ 没问题
            problems.append(f"{path.relative_to(ROOT)}：读不出来（{exc}）")
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for obj, field in pattern.findall(line):
                if field in IGNORED_SUFFIXES:
                    continue
                checked += 1
                if field not in objects[obj]:
                    have = "、".join(sorted(objects[obj])) or "（空对象）"
                    problems.append(
                        f"{path.relative_to(ROOT)}:{lineno} 写着 `{obj}.{field}`，"
                        f"而 /health 的 {obj} 里没有这一格。实际有：{have}"
                    )

    print(f"扫了 {len(docs)} 份 md，核了 {checked} 处 /health 字段引用")
    print(f"  /health 的对象字段：{'、'.join(sorted(objects))}")

    if checked < FLOOR:
        print(
            f"\n**不合格** 只核到 {checked} 处，低于底线 {FLOOR}。\n"
            "  这不是「文档很干净」，是**这道门自己瞎了**：扫描集、正则、\n"
            "  或者跳过规则把该查的整批吃掉了。先去修判据，不要放行。"
        )
        return 1

    if problems:
        print(f"\n**不合格** {len(problems)} 处文档点名了不存在的 /health 字段：")
        for p in problems:
            print(f"  · {p}")
        print(
            "\n  为什么这是硬伤：接手的人只会照这个名字去找。取不到时\n"
            "  `.get()` 给的是 None——它既不等于 True 也不等于 False，\n"
            "  于是「一条链真的停了」会被读成「没事」。"
        )
        return 1

    print("\n✓ 文档点名的 /health 字段，每一个都真的在 /health 里。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
