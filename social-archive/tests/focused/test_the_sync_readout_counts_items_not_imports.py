r"""部署播报里那句「共 N 条」，数的必须是条目，不是导入次数（2026-08-12）。

## 它错在哪儿

一次同步的 `imported_count` 是「这次导入了几条」。同一条被两次同步各导一次，
就在两个 run 里各记一次。播报把它们**相加**当成条数报出来：

    生产实测   bilibili  两次 run 报 102 + 67 = 169   而去重后只有 101
              douyin    两次 run 报  35 + 56 =  91   而去重后只有  85
                                     相加 260        去重 186（他库里一共 193）

于是每一次部署日志都告诉他「自动同步进了 260 条」，而他打开档案馆看到 193。
**多报了 74，而读的人没有任何办法看出那是次数不是条数。**

## 为什么判据没抓到

那几道门查的是 JSON 里的字段，这一句是 `main()` 里的一句 f-string——
散文没有主人。所以这里先把它抽成 `summary_line()`，再对**它**写反例。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from read_production_sync_history import summary_line  # noqa: E402

# 数字取自 2026-08-12 的生产实测，不是我编的：
# 两个平台各两次 run，相加 260，去重 186。
REPORT = {
    "platforms_that_really_imported": ["bilibili", "douyin"],
    "import_events_summed_across_runs": 260,
    "distinct_items_still_in_the_archive": 186,
}


def test_the_headline_number_is_the_deduplicated_one() -> None:
    line = summary_line(REPORT)
    assert "186" in line, f"播报没报去重后的真数：{line}"


def test_the_import_event_count_is_labelled_not_passed_off_as_items() -> None:
    """260 可以出现，但**不能不带口径**。

    这一条不是在挑措辞。260 和 186 差 74，两个都印出来而不说哪个是什么，
    比只印一个更容易被读成「有 260 条」。
    """
    line = summary_line(REPORT)
    if "260" not in line:
        return  # 不报那个数也行——不报就不会被误读
    tail = line.split("260", 1)[1]
    assert "次数" in tail, f"报了 260 却没说它是次数：{line}"


def test_it_does_not_report_the_summed_number_as_the_item_count() -> None:
    """反例的核心。

    构造一份「相加数和去重数差得很远」的报告——如果哪天有人把那个
    f-string 换回相加数，下面这条会立刻红。
    """
    skewed = dict(REPORT, import_events_summed_across_runs=9999,
                  distinct_items_still_in_the_archive=7)
    line = summary_line(skewed)
    head = line.split("（", 1)[0]
    assert "7" in head, f"开头报的不是去重数：{head}"
    assert "9999" not in head, f"把相加数当条数报了：{head}"


def test_no_platforms_does_not_crash() -> None:
    """一条都没进过的时候也得说得出话——**空列表不许被读成「正常」**。"""
    line = summary_line(dict(REPORT, platforms_that_really_imported=[]))
    assert "一个都没有" in line


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
