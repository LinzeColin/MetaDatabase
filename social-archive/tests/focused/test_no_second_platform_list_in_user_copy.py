"""用户可见的文案里，不许再抄一份平台名单（v0.0.0.7 / INV-REAL-USABLE）。

2026-08-05：全仓搜「一句话里点名 ≥2 个平台」，只剩两处，两处都是隐患：

  · apps/pwa/app.js 首页第 3 步
    「本版本能自动同步的是 Chrome 书签，**以及连接后的 X / Instagram**……」
    ——**已经在撒谎**：X 与 Instagram 当天都进了 NOT_SYNCABLE_YET。
  · apps/browser-extension/popup.js 诊断提示
    「请先打开小红书 / 抖音 / B站 / 快手 / X / Reddit / Instagram 的收藏页」
    ——今天恰好还对，但那正是「第二份名单」的样子：
    PLATFORM_RULES 一改它就漂，而没有任何东西会提醒。

两处都改成从真源现算。这条判据守的是「别再抄第三份」。
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLATFORM_WORDS = ("小红书", "抖音", "快手", "B站", "哔哩哔哩", "Instagram", "Reddit")

SCANNED = ("apps/pwa/app.js", "apps/browser-extension/popup.js",
           "apps/browser-extension/options.js", "src/social_archive/account_sync.py")

# NOT_SYNCABLE_YET 是**真源本身**，它当然会逐平台点名——那不是抄，那是原件。
SOURCE_OF_TRUTH_MARKERS = ("NOT_SYNCABLE_YET", "PLATFORM_LABELS", "PLATFORM_RELATIONS")


def _user_facing_strings(path: Path):
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith(("#", "//", "*", "/*")):
            continue
        for match in re.finditer(r'"([^"\n]{8,200})"|\'([^\'\n]{8,200})\'|`([^`\n]{8,200})`', line):
            text = match.group(1) or match.group(2) or match.group(3) or ""
            yield lineno, line, text


def test_no_user_facing_string_names_two_or_more_platforms() -> None:
    offenders = []
    for rel in SCANNED:
        path = ROOT / rel
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        for lineno, line, text in _user_facing_strings(path):
            named = [word for word in PLATFORM_WORDS if word in text]
            if len(named) < 2:
                continue
            # 真源自己那份不算
            window = source[max(0, source.index(line) - 600): source.index(line) + 200] if line in source else ""
            if any(marker in window for marker in SOURCE_OF_TRUTH_MARKERS):
                continue
            offenders.append(f"{rel}:{lineno} 点名了 {named}")
    assert not offenders, (
        "这些用户可见文案里内嵌了平台名单——真源一改它们就漂，"
        f"而没有任何东西会提醒：{offenders}"
    )


def test_the_diagnostic_hint_is_generated_from_the_rules() -> None:
    popup = (ROOT / "apps/browser-extension/popup.js").read_text(encoding="utf-8")
    code = "\n".join(l for l in popup.splitlines() if not l.lstrip().startswith("//"))
    assert "SA.PLATFORM_RULES" in code, "诊断提示里的平台名单不是现算的"
    assert "小红书 / 抖音" not in code, "又把名单抄回文案里了"
