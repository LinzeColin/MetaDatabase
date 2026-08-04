"""抓到即固化——但只固化**读得懂**的那一条（v0.0.0.7 / T09）。

平台目录里那段注释写着：「没实测过的一律写 null，而不是写一个看着像的。」
猜错前缀的后果是「观察器装上了、页面正常、一条都没拦到、而界面显示已连接」——
和「这个人真的没有收藏」长得一模一样。

所以这个脚本必须**拒绝**三种情况：没有读得懂的地址、推出来的前缀只到域名、
报告里根本没有那个平台。
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/freeze_intercept_prefix.py"


def _run(tmp_path, rows, *extra):
    report = tmp_path / "extension-diagnostics.jsonl"
    report.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                      encoding="utf-8")
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--platform", "bilibili", "--report", str(report), *extra],
        cwd=ROOT, capture_output=True, text=True, check=False)
    return done, json.loads(done.stdout.strip().splitlines()[-1])


def test_a_readable_capture_becomes_a_prefix(tmp_path) -> None:
    done, out = _run(tmp_path, [{
        "at": "2026-08-05T00:00:00Z", "platform": "bilibili",
        "urls": ["https://api.bilibili.com/x/web-interface/nav"],
        "readable_urls": ["https://api.bilibili.com/x/v3/fav/resource/list?media_id=1&pn=1"],
    }])
    assert done.returncode == 0, done.stdout + done.stderr
    assert out["prefix"] == "api.bilibili.com/x/v3/fav/resource/list"
    assert out["applied"] is False, "没给 --apply 却动了文件"


def test_it_refuses_when_nothing_was_readable(tmp_path) -> None:
    """**这条是整个脚本的理由。**

    只知道「拦到了」而不知道哪一条是收藏列表接口，这时候写进去的就是
    「看着像的」——正是平台目录明确不许做的事。
    """
    done, out = _run(tmp_path, [{
        "at": "2026-08-05T00:00:00Z", "platform": "bilibili",
        "urls": ["https://api.bilibili.com/x/web-interface/nav"],
        "readable_urls": [], "capture_count": 37, "readable_count": 0,
    }])
    assert done.returncode != 0
    assert out["error_code"] == "NOTHING_READABLE"
    assert out["diagnostics_seen"] == 1


def test_it_refuses_a_prefix_that_is_only_a_domain(tmp_path) -> None:
    """诊断模式的前缀是从域名推的，页面上每个请求都会被抓。

    如果读得懂的那几条只能收敛到一个域名，那不是前缀，是「拦下所有东西」。
    """
    done, out = _run(tmp_path, [{
        "at": "2026-08-05T00:00:00Z", "platform": "bilibili",
        "readable_urls": ["https://api.bilibili.com/x/v3/fav/list",
                          "https://api.bilibili.com/y/other"],
    }])
    assert done.returncode != 0
    assert out["error_code"] == "PREFIX_TOO_BROAD"


def test_multiple_readable_urls_collapse_on_path_segments_not_characters(tmp_path) -> None:
    """公共前缀按 `/` 切，不按字符切。

    按字符切会切出 `api.bilibili.com/x/v3/fav/resou` 这种半截路径段——
    看着像个前缀，实际匹配行为完全不可预期。
    """
    done, out = _run(tmp_path, [{
        "at": "2026-08-05T00:00:00Z", "platform": "bilibili",
        "readable_urls": ["https://api.bilibili.com/x/v3/fav/resource/list?pn=1",
                          "https://api.bilibili.com/x/v3/fav/resource/ids"],
    }])
    assert done.returncode == 0
    assert out["prefix"] == "api.bilibili.com/x/v3/fav/resource"


def test_it_refuses_when_the_platform_has_no_diagnostic(tmp_path) -> None:
    done, out = _run(tmp_path, [{"at": "x", "platform": "douyin", "readable_urls": ["https://a/b"]}])
    assert done.returncode != 0
    assert out["error_code"] == "NO_DIAGNOSTIC_FOR_PLATFORM"


def test_apply_writes_the_catalog_and_says_it_is_still_unverified(tmp_path) -> None:
    catalog = tmp_path / "platform-catalog.js"
    catalog.write_text(
        "const INTERCEPT_PREFIXES = Object.freeze({\n"
        "    bilibili: Object.freeze([\"old.example/x\"]),\n"
        "    xiaohongshu: null,\n"
        "  });\n", encoding="utf-8")
    done, out = _run(tmp_path, [{
        "at": "2026-08-05T00:00:00Z", "platform": "bilibili",
        "readable_urls": ["https://api.bilibili.com/x/v3/fav/resource/list?pn=1"],
    }], "--apply", "--catalog", str(catalog))
    assert done.returncode == 0, done.stdout + done.stderr
    assert out["applied"] is True
    written = catalog.read_text(encoding="utf-8")
    assert 'bilibili: Object.freeze(["api.bilibili.com/x/v3/fav/resource/list"])' in written
    assert "xiaohongshu: null" in written, "改了不该改的那一项"
    assert "还没有人验过它真能拦到" in out["reminder"], (
        "写进去就说完了——而「写进去」和「真能拦到」是两件事，这个项目一直栽在这上面"
    )
