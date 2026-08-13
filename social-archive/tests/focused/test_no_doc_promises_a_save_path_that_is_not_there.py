r"""文档不许承诺一条不存在的保存路径（2026-08-14）。

## 三份文档，同一句假话

`README.md`、`docs/00_我在哪.md`、`docs/00_零门槛运行手册.md` 都写着
「没装插件时，首页仍可**粘贴链接**保存」，其中一份还加了「也可使用 **PWA 分享**」。

实测（不是读代码推的）：

    apps/pwa/index.html 的三个 input  →  搜索框 / 导入时填平台名 / 上传文件
    apps/pwa/manifest.webmanifest     →  **没有 share_target**
    apps/ 下唯一的 type="url"          →  扩展高级设置里的「服务地址」，不是保存路径

**两条路都不存在。** 而它们承诺的正是「**还没装插件的人**」——第一次来的那个人。
给他一条不存在的退路比不给更坏：**他会以为是自己没找到。**

## 为什么之前没人抓到

`check_docs_match_the_ui.py` 查的是**直角引号里的界面词**。
这句是**散文里的承诺**，一个引号都没有，所以它看不见。
`AGENTS.md` 里也写着这一类没有门、而且**不该硬做一个通用的**
（判断「这句承诺证得了吗」要看外部系统，机器判会大量误报）。

**这道门不通用，只钉这一条**：文档一旦说「粘贴链接/贴上链接就能保存」
或「PWA 分享」，产品里就必须真的有那个入口。
窄，但它守的是这三份文档里都出现过的一句真假话。

## 修完之后还要数一遍它压着谁

我先只改了 `README.md`，以为修完了；**另外两份是 grep 之后才发现的**。
所以这道门扫**全部** `.md`（除了 CHANGELOG 那种按设计要引用旧写法的）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PWA = ROOT / "apps/pwa"

# 说了这些，就等于承诺了一条不用插件的保存路径
PASTE_CLAIM = re.compile(r"(粘贴链接|贴上链接|粘贴.{0,4}保存|首页.{0,6}粘贴)")
SHARE_CLAIM = re.compile(r"PWA\s*分享|分享到.{0,4}档案馆")

# 按设计会引用旧写法（讲它为什么被删）的文档
SKIP = {"CHANGELOG.md"}


def _docs() -> list[Path]:
    out = []
    for path in list(ROOT.glob("*.md")) + list((ROOT / "docs").rglob("*.md")):
        if path.name in SKIP:
            continue
        out.append(path)
    return out


def _has_paste_entry() -> bool:
    """首页上真的有一个可以贴链接的地方吗。"""
    index = PWA / "index.html"
    if not index.exists():
        return False
    text = index.read_text(encoding="utf-8")
    return bool(re.search(r'<input[^>]*type="url"', text))


def _has_share_target() -> bool:
    manifest = PWA / "manifest.webmanifest"
    if not manifest.exists():
        return False
    try:
        return "share_target" in json.loads(manifest.read_text(encoding="utf-8"))
    except ValueError:
        return "share_target" in manifest.read_text(encoding="utf-8")


def test_没有贴链接入口就不许在文档里承诺它() -> None:
    if _has_paste_entry():
        return  # 产品真有这条路，随便写
    offenders = []
    for doc in _docs():
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith(">"):
                continue  # 注解（在说"这条已经删了"），不是承诺
            if PASTE_CLAIM.search(line):
                offenders.append(f"{doc.relative_to(ROOT)}:{lineno} {line.strip()[:60]}")
    assert not offenders, (
        "文档承诺了「粘贴链接就能保存」，而首页上没有这个入口：\n  "
        + "\n  ".join(offenders)
        + "\n\n  实测 apps/pwa/index.html 的 input 只有搜索／导入平台名／上传文件。\n"
          "  这条承诺给的是**还没装插件的人**——给他一条不存在的退路比不给更坏。")


def test_没有share_target就不许承诺PWA分享() -> None:
    if _has_share_target():
        return
    offenders = []
    for doc in _docs():
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith(">"):
                continue
            if SHARE_CLAIM.search(line):
                offenders.append(f"{doc.relative_to(ROOT)}:{lineno} {line.strip()[:60]}")
    assert not offenders, (
        "文档承诺了「PWA 分享」，而 manifest 里没有 `share_target`：\n  "
        + "\n  ".join(offenders))


def test_这套检测本身还能判() -> None:
    """**先拿已知答案自检。** 正则失效或路径读空时，上面两条会安静地全绿。"""
    assert PASTE_CLAIM.search("没有安装插件时，仍可在首页粘贴链接保存"), "承诺句的正则失效了"
    assert not PASTE_CLAIM.search("我照着它改取数路，不用你复制粘贴"), "正则太宽，会误报"
    assert SHARE_CLAIM.search("也可使用 PWA 分享"), "分享句的正则失效了"
    assert (PWA / "index.html").exists(), "读不到首页，这道门此刻判不了任何东西"
    assert _docs(), "一份文档都没扫到——扫描集空了"
