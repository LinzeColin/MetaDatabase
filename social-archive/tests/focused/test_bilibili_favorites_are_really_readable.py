"""B 站收藏夹取数路（v0.0.0.7 / G1 / INV-NO-SILENT-ZERO）。

Owner 2026-08-06 的验收原话里那半句是「多平台聚合到一起」。在这之前
`SYNCABLE_NOW` 只有 `generic-web`，九个平台里八个 `sync_supported=false`——
那句话没有兑现。G1 把 B 站收藏夹那条取数路做出来了。

这里跑的是**离线固定装置**那一段：喂假响应，看分支走对没有。
打真实接口那一段在 `scripts/bilibili_acquisition_drill.py`（要网络，
不进测试套件），它的结论落在 `evidence/G1/BILIBILI_ACQUISITION.json`。

**这两段的可信度不一样，所以分开放：**
固定装置是我写的，它和实现共用我的假设——它只能证明分支走对了，
不能证明「我对 B 站接口的理解是对的」。后者只有打真接口才算数。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
READER = ROOT / "apps/browser-extension/content/bilibili-reader.js"
EVIDENCE = ROOT / "evidence/G1/BILIBILI_ACQUISITION.json"


def _node(body: str) -> dict:
    script = (
        'const R = require("./apps/browser-extension/content/bilibili-reader.js");\n'
        'const reply = (b) => ({ ok: true, json: async () => b });\n'
        "(async () => {\n" + body + "\n})().catch(e => "
        'console.log(JSON.stringify({ _error: String(e && e.message || e) })));'
    )
    done = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True,
                          text=True, timeout=90)
    assert done.returncode == 0, f"node 跑失败：{done.stderr[-500:]}"
    payload = json.loads(done.stdout.strip().splitlines()[-1])
    assert "_error" not in payload, payload.get("_error")
    return payload


def test_the_reader_file_exists() -> None:
    assert READER.is_file(), "取数器不在——SYNCABLE_NOW 里的 bilibili 就没有实现"


def test_success_code_with_null_data_is_not_read_as_empty() -> None:
    """**这条是整条路上最要紧的判据。**

    实测（2026-08-06 打真接口）：看不见的收藏夹回的是
        {"code":0,"message":"OK","ttl":1,"data":null}
    成功码、成功文案、空数据。照着 `data?.list || []` 写就得到
    「同步成功，0 条」——INV-NO-SILENT-ZERO 禁的正是这个，
    而 v0.0.0.6 生产上「永远是 0」就是这么来的。
    """
    out = _node("""
      const r = R.classify({ code: 0, message: "OK", ttl: 1, data: null });
      console.log(JSON.stringify(r));
    """)
    assert out["ok"] is False, "「成功码 + 空数据」被当成读到了——这就是那种静默的零"
    assert out["failureCode"] == "BILIBILI_FOLDER_NOT_VISIBLE"


def test_no_folders_never_reports_success_with_zero_items() -> None:
    """一个收藏夹都没有 → 必须是显式失败，不能是「成功，0 条」。

    这两种情况在字节上分不开（没带登录态时接口也回空），
    而其中一种他自己就能解决——所以不许合并成一句「你没有收藏」。
    """
    out = _node("""
      const fetchImpl = async (url) => String(url).includes("/nav")
        ? reply({ code: 0, data: { isLogin: true, mid: 42, uname: "u" } })
        : reply({ code: 0, data: { count: 0, list: [] } });
      console.log(JSON.stringify(await R.readAllFavorites({ fetchImpl })));
    """)
    assert out["ok"] is False
    assert out["failureCode"] == "BILIBILI_NO_FOLDERS"


def test_app_deeplinks_never_become_archived_urls() -> None:
    """`media.link` 的真实值是 `bilibili://video/116980698843032`——App 深链。

    直接拿它当网址用的话，入库的每一条都是在浏览器里点不开的。
    网址必须由 bvid 拼。读不出网址的条目要**跳过并记下**，不能默默丢
    （默默丢等于静默的少读，而少读会让后面的"消失检测"把它当成取消收藏）。
    """
    out = _node("""
      const fetchImpl = async () => reply({ code: 0, data: {
        info: { title: "t", media_count: 2 },
        medias: [{ id: 1, link: "bilibili://video/1", title: "只有深链" },
                 { id: 2, bvid: "BV11111111", title: "正常", upper: { name: "a" } }],
        has_more: false } });
      const r = await R.readFolder("1", { fetchImpl, pageSize: 20 });
      console.log(JSON.stringify({ kept: r.items.length, skipped: r.skipped.length,
                                   url: r.items[0] ? r.items[0].url : "" }));
    """)
    assert out["kept"] == 1, "深链那条没有被挡下来"
    assert out["skipped"] == 1, "被跳过的条目没有记下来——那是静默的少读"
    assert out["url"].startswith("https://www.bilibili.com/video/BV")


def test_reading_fewer_than_declared_is_not_reported_as_complete() -> None:
    """接口自己说有 10 条、只给了 2 条 → 不许报 complete。

    报了 complete 的后果不是难看，是**会丢数据**：没读到的那 8 条
    会被"消失检测"当成他取消了收藏。
    """
    out = _node("""
      const fetchImpl = async () => reply({ code: 0, data: {
        info: { title: "t", media_count: 10 },
        medias: [{ id: 1, bvid: "BV11111111", upper: { name: "a" } },
                 { id: 2, bvid: "BV22222222", upper: { name: "a" } }],
        has_more: false } });
      const r = await R.readFolder("1", { fetchImpl, pageSize: 20 });
      console.log(JSON.stringify({ partial: r.partial, code: r.failureCode,
                                   declared: r.expected, read: r.items.length }));
    """)
    assert out["partial"] is True
    assert out["code"] == "BILIBILI_COUNT_MISMATCH"


def test_pagination_cannot_spin_forever() -> None:
    """接口说「还有更多」却给空页时，必须停下并报出来，不能死循环。"""
    out = _node("""
      let calls = 0;
      const fetchImpl = async () => { calls += 1; return reply({ code: 0, data: {
        info: { title: "t", media_count: 99 },
        medias: calls === 1 ? [{ id: 1, bvid: "BV11111111", upper: { name: "a" } }] : [],
        has_more: true } }); };
      const r = await R.readFolder("1", { fetchImpl, pageSize: 1 });
      console.log(JSON.stringify({ code: r.failureCode, calls, kept: r.items.length }));
    """)
    assert out["code"] == "BILIBILI_PAGINATION_STUCK"
    assert out["calls"] < 10, "空页没有让它停下来"
    assert out["kept"] == 1, "已经读到的那条没有保住"


def test_not_logged_in_is_its_own_answer() -> None:
    out = _node("""
      const fetchImpl = async () => reply({ code: -101, message: "账号未登录",
                                            data: { isLogin: false } });
      console.log(JSON.stringify(await R.currentUser(fetchImpl)));
    """)
    assert out["ok"] is False
    assert out["failureCode"] == "BILIBILI_NOT_LOGGED_IN"


def test_the_happy_path_marks_itself_complete_and_keeps_folder_membership() -> None:
    out = _node("""
      const fetchImpl = async (url) => {
        const t = String(url);
        if (t.includes("/nav")) return reply({ code: 0, data: { isLogin: true, mid: 42 } });
        if (t.includes("list-all")) return reply({ code: 0, data: { count: 2, list: [
          { id: 11, title: "夹一", media_count: 1 }, { id: 22, title: "夹二", media_count: 1 }] } });
        const id = t.match(/media_id=(\\d+)/)[1];
        // bvid 要像真的：真实值形如 BV1nB3u6tERu（BV 后面 10 位）。
        // 第一版这里写的是 "BV" + id + "00000"，BV 后面只有 7 位，
        // 被取数器判成"读不出网址"而跳过 —— 于是 completeness 变成 partial。
        // **是固定装置造得不像，不是判据太严**：短 bvid 在 B 站上根本不存在。
        return reply({ code: 0, data: { info: { title: "夹" + id, media_count: 1 },
          medias: [{ id: Number(id), bvid: "BV" + id + "AbCdEfGh", upper: { name: "a" } }],
          has_more: false } });
      };
      const r = await R.readAllFavorites({ fetchImpl });
      console.log(JSON.stringify({ ok: r.ok, completeness: r.completeness,
        items: r.items.length, collections: r.cursor.collections_found,
        keys: r.items.map(i => i.collection_key) }));
    """)
    assert out["ok"] is True
    assert out["completeness"] == "complete"
    assert out["items"] == 2
    assert out["collections"] == 2, "收藏夹个数没有报出来——回执上会写 0 个"
    # 每条都要记得自己属于哪个收藏夹，否则聚合视图里分不了组
    assert sorted(out["keys"]) == ["11", "22"]


def test_every_field_we_emit_is_one_the_server_accepts() -> None:
    """服务端 `CaptureRequest` 是 `extra="forbid"`：**多一个键整批 422**。

    而批次是 200 条一发——一个拼错的键能让 200 条一起落空。
    """
    from social_archive.models import CaptureRequest

    out = _node("""
      const fetchImpl = async () => reply({ code: 0, data: {
        info: { title: "t", media_count: 1 },
        medias: [{ id: 7, bvid: "BV77777777", title: "标题", intro: "简介",
                   cover: "https://i0.hdslb.com/x.jpg", upper: { name: "作者" },
                   pubtime: 1700000000, fav_time: 1700000001, duration: 60, page: 1 }],
        has_more: false } });
      const r = await R.readFolder("99", { fetchImpl, pageSize: 20 });
      console.log(JSON.stringify(r.items[0]));
    """)
    allowed = set(CaptureRequest.model_fields)
    extra = sorted(set(out) - allowed)
    assert not extra, f"取数器产出了 CaptureRequest 不认的字段：{extra}——整批会 422"
    # 真的构造一次，字段类型也得过得去（url 是 HttpUrl，时间是字符串…）
    built = CaptureRequest(platform="bilibili", relation_type="favorite", **out)
    assert str(built.url).startswith("https://www.bilibili.com/video/BV")
    assert built.title == "标题"
    assert built.author_name == "作者"


@pytest.mark.skipif(not EVIDENCE.is_file(), reason="实测证据还没跑出来")
def test_the_evidence_says_it_really_hit_the_live_api() -> None:
    """证据文件得说明它**真的打过接口**，而不是离线降级跑出来的 PASS。

    「降级当通过」是这个项目反复踩的坑：只看 status 的话，
    一次 `--no-live` 的 PASS 和一次真实测的 PASS 长得一模一样。
    """
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert data["status"] == "PASS"
    assert data["live_probe_ran"] is True, "这份证据是离线跑的，不能当作「量过了」"
    folder = data["live"]["live_folder"]
    assert folder["declared"] == folder["read"], "声明条数和实际读到的对不上"
    assert folder["all_urls_openable"] is True
    assert data["live"]["live_invisible_folder"]["behaved_as_expected"] is True
    # 零费用与不碰 cookie 这两条是 Owner 的硬边界，证据里必须留痕
    assert data["zero_cost"]["api_key_required"] is False
    assert data["cookie_handling"]["transmits_cookie_values"] is False
