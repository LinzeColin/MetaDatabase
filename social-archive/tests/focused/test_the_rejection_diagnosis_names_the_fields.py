r"""认不出列表时那段诊断，要带字段名、且不带任何值（2026-08-14）。

## 它修的是什么

抖音那条取数路 2026-08-06 换过，**换过之后从没真跑过**——只在
`list_shape_end_to_end_drill.py` 里那份**我自己编的响应**上验过
（那个演练自己的注释写着：「编的夹具只会给出假绿或假红，两种都比没有更坏」）。
所以 Owner 按下「连接账号」的那一下，是它第一次遇到真站的响应。

认不出时产品会给一段**可整段复制**的诊断，让他发给我。
而 `score()` 明明算出了 `id_keys` / `id_path` / `core_path`，
被淘汰的那一条却只留 `{url, why}`——**整个 stats 被丢掉**。
于是诊断里只有比率（多少元素有 id/标题/作者），**没有一个字段叫什么**，
而 `docs/使用说明.md` 承诺的是「只写下有哪几个字段、各是什么类型」。
结果就是我得再问他一次，而他说过不要这种来回。

## 两件事一起钉

1. **带字段名**：`item_keys` / `id_keys` / `id_path` / `core_path` / `count` / `path`
2. **不带任何值**——这段是他要复制发出来的，里面不能有他的标题、链接或 id。
   这一条比第一条更硬：多给一个键名只是啰嗦，多给一个值是把他的内容送出去。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "apps/browser-extension/content/list-shape.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="本机没有 node")


def _reject_diagnosis() -> dict:
    """喂一批**认不出**的响应，把那段诊断取回来。

    元素带 id 但没有标题/作者/时间——按打分规则「光有 id 不算内容」，
    正是会被淘汰的那一种，也正是真站上最可能发生的一种。
    """
    payload = {
        "data": {
            "items": [
                {"aweme_id": f"{7000 + index}", "seq": index,
                 "extra_flag": True, "trace": "abc"}
                for index in range(12)
            ]
        }
    }
    script = f"""
const api = require({json.dumps(str(MODULE))});
const captured = [{{ url: "https://www.douyin.com/aweme/v1/web/favorite/list/?a=1&sig=SECRET",
                     text: {json.dumps(json.dumps(payload))} }}];
const out = api.recogniseList(captured);
process.stdout.write(JSON.stringify(out));
"""
    done = subprocess.run(["node", "-e", script], cwd=ROOT,
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, (
        f"跑不起来那个模块（退出码 {done.returncode}）：\n{done.stderr[:600]}\n"
        "  导出名变了就把这里一起改——**不许把跑不起来当成通过**。")
    return json.loads(done.stdout)


def test_诊断里带得出字段名() -> None:
    out = _reject_diagnosis()
    rejected = out.get("rejected") or []
    assert rejected, f"这批响应本该被淘汰并留下诊断，实际：{out}"
    entry = rejected[0]
    for key in ("item_keys", "id_keys", "id_path", "core_path", "count", "path", "why"):
        assert key in entry, (
            f"诊断里没有 `{key}`：{entry}\n"
            "  他把这段整段发我时，我要靠它直接改取数路——"
            "  少一样就得再问他一次，而他说过不要这种来回。")
    assert entry["item_keys"], f"字段名是空的，等于没带：{entry}"
    assert "aweme_id" in entry["item_keys"], f"没认出真实存在的键：{entry['item_keys']}"


def test_诊断里不许带任何值() -> None:
    """**比上一条更硬。** 多给一个键名只是啰嗦，多给一个值是把他的内容送出去。"""
    out = _reject_diagnosis()
    blob = json.dumps(out, ensure_ascii=False)
    # 上面那批响应里出现过的**值**，一个都不许出现在诊断里
    for leaked in ("7000", "7005", "abc", "SECRET"):
        assert leaked not in blob, (
            f"诊断里出现了响应里的值 `{leaked}`——这段是他要整段复制发出来的：\n{blob[:400]}")
    # 地址要剥掉查询串（签名就在里面）
    for entry in out.get("rejected") or []:
        assert "?" not in str(entry.get("url", "")), f"地址没剥查询串：{entry['url']}"
