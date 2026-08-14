r"""包里必须有它运行时才去取的那些文件（2026-08-14）。

## 这道判据补的是哪一档

`shipped_package_drill.py` 把 zip 真装进 Chrome，Chrome 会拒绝 manifest 指向的
缺失文件。**而运行时注入那一档它看不见**——2026-08-14 实测 `background.js`
用 `executeScript` 注入 6 个文件，manifest 里一个名字都没提过：

    content/bilibili-reader.js / extract-core.js / extract.js
    fab.js / net-relay.js / net-observer.js

manifest 里没有这些名字 ⇒ Chrome 装载期**结构上不可能**校验它们。
把 `content/bilibili-reader.js` 改个名：打包成功、zip 对得上 git、Chrome 装得上、
service worker 起得来、23 个演练全绿——而唯一跑通的那条 B 站读取路
在他按下「连接账号」那一刻才静静失败。

## 为什么反例要焊在测试里

这个仓的判据坏过太多次，形状都是「它一直绿着，而它守的东西早就没了」。
所以这里不只测「真包能过」，**每一条都配一个必须红的反例**：
少文件要红、空扫要红、注入机制整档消失也要红。
"""
from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts/check_the_package_ships_what_it_injects.py"
SOURCE = ROOT / "apps/browser-extension"


def _run(zip_path: Path) -> tuple[int, dict]:
    done = subprocess.run(
        [sys.executable, str(CHECKER), "--zip", str(zip_path), "--json"],
        capture_output=True, text=True, check=False, cwd=ROOT)
    try:
        payload = json.loads(done.stdout)
    except json.JSONDecodeError:
        payload = {"_stdout": done.stdout, "_stderr": done.stderr}
    return done.returncode, payload


@pytest.fixture(scope="module")
def real_zip(tmp_path_factory) -> Path:
    """现打一个包——**不要用 `dist/` 里那个**。

    那份是上一次部署留下的，可能比工作树旧；拿它当基准的话，
    「我刚改的东西有没有进包」这个问题会被一个陈旧产物回答。
    （这个仓栽过「残留产物冒充流水线产出」。）
    """
    out = tmp_path_factory.mktemp("pkg") / "extension.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(SOURCE.rglob("*")):
            if path.is_file() and path.name != ".DS_Store" and "__pycache__" not in path.parts:
                archive.writestr(path.relative_to(SOURCE).as_posix(), path.read_bytes())
    return out


def _rebuild_without(real: Path, target: Path, drop: str) -> int:
    with zipfile.ZipFile(real) as src, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as dst:
        kept = 0
        for info in src.infolist():
            if info.filename == drop:
                continue
            dst.writestr(info, src.read(info))
            kept += 1
    return kept


def test_真包过得去(real_zip: Path) -> None:
    code, payload = _run(real_zip)
    assert code == 0, f"当前这个包就过不去：{json.dumps(payload, ensure_ascii=False)[:900]}"
    assert payload["status"] == "PASS", payload
    # 扫描集不许悄悄缩水：真扫到了东西，不是空过。
    assert payload["references_found"] >= 15, payload
    assert payload["files_scanned"] >= 10, payload


def test_运行时注入的文件被抽掉必须红(real_zip: Path, tmp_path: Path) -> None:
    """**反例：Chrome 装得上而它必须红。**

    挑 `content/bilibili-reader.js`——它是唯一一条真跑通的读取路，
    而且 manifest 里根本没提过它，所以装载期一定查不出来。
    """
    broken = tmp_path / "broken.zip"
    kept = _rebuild_without(real_zip, broken, "content/bilibili-reader.js")
    with zipfile.ZipFile(real_zip) as archive:
        total = len(archive.infolist())
    # **先确认反例真的造出来了**（这个仓有过「反例根本没生效，3 passed 是假绿」）
    assert kept == total - 1, f"没抽掉那个文件：原 {total} 个，现 {kept} 个"

    code, payload = _run(broken)
    assert code == 1, f"抽掉了运行时注入的文件，判据却没红：{json.dumps(payload, ensure_ascii=False)[:900]}"
    assert "content/bilibili-reader.js" in payload["missing"], payload
    # 报告要说得出**谁**引用了它——否则他拿到一条孤零零的路径无从下手
    assert any("executeScript" in who
               for who in payload["missing"]["content/bilibili-reader.js"]), payload


def test_空扫要当失败(tmp_path: Path) -> None:
    """**空扫必须红。**

    这个仓有过判据因为路径前缀写错而跳过全部 27 个文件、打出「0 个不同」，
    差点被读成通过。给它一个几乎空的包：引用数够不着下限，必须 FAIL。
    """
    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"manifest_version": 3, "version": "0.0.0.0"}))
    code, payload = _run(empty)
    assert code == 1, f"空包被判成通过了：{payload}"
    assert payload["status"] == "FAIL", payload
    assert "判据自己坏了" in payload["why"], payload


def test_注入机制整档消失也要红(real_zip: Path, tmp_path: Path) -> None:
    """**另一种空过**：文件都在，而 `executeScript` 那一档一条都扫不到。

    要么产品换了注入机制、要么这道判据的正则失效了——两种都要人看一眼，
    不能悄悄变成「没有这类引用所以全绿」。
    这里把 background.js 换成一个不含任何注入的版本来模拟。
    """
    neutered = tmp_path / "neutered.zip"
    with zipfile.ZipFile(real_zip) as src, zipfile.ZipFile(neutered, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            raw = src.read(info)
            if info.filename == "background.js":
                raw = b"// no injection here\n"
            dst.writestr(info, raw)
    code, payload = _run(neutered)
    assert code == 1, f"注入机制整档消失而判据全绿：{json.dumps(payload, ensure_ascii=False)[:600]}"
    assert "executeScript" in payload["why"], payload


def test_查询串和锚点不许被当成文件名(real_zip: Path) -> None:
    """`getURL("options.html?onboarding=1")` 要按 `options.html` 算。

    这道判据第一版就是这么误报的——报「缺 options.html?onboarding=1」，
    而那个文件当然不存在。**误报比漏报更容易被当成产品缺陷去改产品。**
    """
    background = (SOURCE / "background.js").read_text(encoding="utf-8")
    assert "options.html?" in background or "options.html#" in background, (
        "产品里已经没有带查询串/锚点的 getURL 了——"
        "这条测试守的东西不存在了，删掉它，别留着一条永远绿的门。")
    code, payload = _run(real_zip)
    assert code == 0, payload
    assert not any("?" in path or "#" in path for path in payload["missing"]), payload
