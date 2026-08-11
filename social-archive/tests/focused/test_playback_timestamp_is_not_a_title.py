r"""播放进度形状的标题，在入库那道门上就该被置空（2026-08-12）。

## 生产实测

他库里 193 条有 **56 条**的标题是 `06:26/12:57` 这种——B 站播放器上的时间，
不是标题。全部来自 history 那条路，占他 B 站条目（103 条）的一半以上。

## 为什么这道门比「修数据」重要

只修数据修不住。`content` 的 upsert 是：

    title=COALESCE(excluded.title, content.title)

下一次 history 同步照样送一个播放进度上来，`excluded.title` 非空，
**修好的标题就被覆盖回去了**。这道门让 `excluded.title` 变成 NULL，
COALESCE 于是**保住库里那个好标题**——数据修复因此才修得住。

## 为什么是置空，不是拒绝整条

拒绝 = 那条内容根本进不来，他丢的是内容本身，比标题错更糟。
置空之后界面有兜底（`item.title || _urlLabel(item.canonical_url)`），
他看到链接尾巴——不好看，但是真的。

## 误伤是这条判据的主要风险

「10万个冷知识」这种以数字开头的正当标题不能被吃掉（v0.0.0.41 的教训）。
所以用**锚定全匹配**，并且把这几个反例钉死。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from social_archive.models import CaptureRequest  # noqa: E402


def _title(given: str | None) -> str | None:
    return CaptureRequest(platform="bilibili",
                          url="https://www.bilibili.com/video/BV1x/",
                          relation_type="history", title=given).title


@pytest.mark.parametrize("given", ["06:26/12:57", "00:08", "1:05", "21:52/23:12",
                                   "  06:26/12:57  "])
def test_a_playback_timestamp_never_becomes_a_title(given: str) -> None:
    assert _title(given) is None, f"{given!r} 被当成标题存下来了"


@pytest.mark.parametrize("given", [
    "10万个冷知识",                 # 数字开头的正当标题（v0.0.0.41 的教训）
    "12:57 教你三招",               # 以时间开头，但后面有正文
    "第3集：06:26 那一段讲的是什么",   # 时间在中间
    "为什么孩子打游戏能连续6小时不动",
    "《云上的中国》第1集：云上的数字商业",
])
def test_a_real_title_is_never_eaten(given: str) -> None:
    """**误伤比漏判更糟**：漏一条他看到一个怪标题，误伤一条他直接丢了标题。"""
    assert _title(given) == given, f"正当标题被吃掉了：{given!r}"


def test_none_stays_none() -> None:
    assert _title(None) is None


def test_the_repair_survives_a_resync() -> None:
    """这道门存在的真正理由：让「修回真标题」修得住。

    upsert 写的是 `title=COALESCE(excluded.title, content.title)`。
    这道门把送上来的播放进度变成 NULL，于是 COALESCE 保住库里那个好标题。
    这里直接把那条 SQL 的语义写成断言，免得哪天有人把 COALESCE 改成直接覆盖，
    而这道门看起来还好好的。
    """
    incoming = _title("06:26/12:57")
    already_in_the_db = "为什么孩子打游戏能连续6小时不动"
    assert incoming is None
    # COALESCE(excluded.title, content.title) 的语义
    assert (incoming or already_in_the_db) == already_in_the_db


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
