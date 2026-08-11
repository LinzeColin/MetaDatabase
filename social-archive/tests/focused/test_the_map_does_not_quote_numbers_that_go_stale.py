"""交接表是地图，地图上不许写会陈的数字（v0.0.0.7）。

2026-08-05 实测：交接表里「Owner 要动手的只有一件」那一段——**最多人读、
最该准的一段**——写着下载包的 sha256 `540f2aea…`。而那个包当天被重打了
十几次，写下的那一刻起它就在变陈。

两种用法长得很像，性质完全相反：

    「**当前**下载页发的是 540f2aea」   → 会陈，是隐患
    「**08-04 那次**量到的是 540f2aea」 → 永远为真，是证据

后者属于 evidence/（带日期、记一次测量）；前者不该存在——要核就现场量。
部署第 8 道门每次都从机器内部打一次下载路由比对，比任何写死的数字可靠。

这条判据只管交接表：**证据文件里的哈希是历史记录，一个都不许动。**
"""

import re
from pathlib import Path

HANDOFF = Path(__file__).resolve().parents[2] / "evidence/HANDOFF_v0007.md"

# 12 位以上连续十六进制——短于这个的是版本号、端口、uid 之类，不误伤。
LOOKS_LIKE_A_HASH = re.compile(r"\b[0-9a-f]{12,}\b")


def test_the_handoff_quotes_no_artifact_hashes() -> None:
    text = HANDOFF.read_text(encoding="utf-8")
    offenders = []
    for number, line in ((m.group(0), line)
                         for line in text.splitlines()
                         for m in [LOOKS_LIKE_A_HASH.search(line)] if m):
        offenders.append(f"{number[:12]}… 在「{line.strip()[:60]}」")
    assert not offenders, (
        "交接表里出现了会陈的哈希——它是地图，地图错了就把下一个人带偏。"
        "要记一次测量就写进 evidence/ 并带上日期；要核当前值就现场量"
        "（部署第 8 道门每次都比对下载路由）。命中：" + "；".join(offenders)
    )


def test_the_reason_is_written_down_where_someone_will_read_it() -> None:
    """光有判据不够——被它拦下的人得知道为什么，否则只会想办法绕过去。"""
    text = HANDOFF.read_text(encoding="utf-8")
    assert "这里不写包的 sha256" in text, (
        "交接表里没有解释为什么不写哈希；下一个人会以为是漏了，然后补回去"
    )
