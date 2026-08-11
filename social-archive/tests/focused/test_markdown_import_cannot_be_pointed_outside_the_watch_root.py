"""Markdown 导入的**目录围栏**，此前只挡住了最直白的那一种（v0.0.0.7 / T05）。

## 为什么补这个

2026-08-05 数了一遍：44 条路由里判据一次都没出现过的还剩两条，
其中一条是 `POST /v1/import/markdown`。它在 `find_endpoints_no_client_calls.py`
里登记着「**没有任何调用方**，已被 ZIP 导入取代但没删」。

没人调不等于打不到——**它在生产上是活的**，而且是个**写入口**：
请求体里那个 `root` 是一个**由客户端指定的服务器路径**。
`_safe_root` 会把它挡在 `SOCIAL_ARCHIVE_WATCH_ROOT` 里，
`scan` 还会跳过符号链接。这两条都是安全性质，而当时的判据只有一条：
「传一个围栏外的路径会 ValueError」。

**符号链接那条一个字都没有。** 而它才是真正绕得过去的那一种：
路径本身老老实实在围栏里，链接指向的东西不在。

## 这里钉两件事

「围栏外的路径要拒」那条已经有了，在
`tests/focused/test_markdown_importer.py::test_markdown_watch_rejects_escape`，
**不在这里重复**——一条性质两处断言，改的时候必然漏一处。这里补的是它没覆盖的：

1. **围栏内指向围栏外的文件链接**不许被导入 —— 靠代码里那句 `path.is_symlink()`
2. **围栏内指向围栏外的目录链接**不许被走进去 —— 这条**不是我们的代码挡的**，
   是 `Path.rglob` 自己不跟着目录链接走。代码里没有任何一处写着它依赖这件事，
   而**一条靠别人的默认行为成立的安全性质，没有判据钉住就等于没人知道它哪天会没**。

   （原先这里写的是「3.12 及以前 `**` 会跟着目录链接走」。**那句是错的，
   而且我是先写下来才去量的。** 本机 3.13.14 和生产镜像里的 3.12.13
   各跑了一次同样的实验，两边都没走进去；3.13 加的 `recurse_symlinks`
   是把既有行为变成可配，不是改了默认。）

## 边界

· 只验「有没有被读进来」。不验读进来之后怎么存——那是 capture 那条链的事。
· 第 2 条钉的是**行为**（链接后面的东西没进来），不是实现。
  将来换了实现只要行为不变，它照样绿；行为变了它就红，这正是要的。
"""

from __future__ import annotations

from social_archive.connectors.markdown_watch import MarkdownWatchImporter

FRONT = "---\nurl: https://example.invalid/{name}\ntitle: {name}\n---\n{body}"


def _write(path, name: str, body: str) -> None:
    path.write_text(FRONT.format(name=name, body=body), encoding="utf-8")


def _scan(importer, root=None):
    return importer.scan(requested_root=root, platform_hint="import",
                         relation_type="saved", limit=100)


def test_a_symlinked_file_inside_the_fence_is_not_imported(settings, tmp_path):
    """**路径在围栏里，链接指向围栏外。**

    这是 `_safe_root` 挡不住的那一种：它只看 root 这一个路径合不合法，
    围栏里放什么它管不着。挡住它的是 scan 里那句 `path.is_symlink()`。
    """
    secret = tmp_path / "secret"
    secret.mkdir()
    _write(secret / "private.md", "private", "围栏外的内容")
    (settings.watch_root / "looks-normal.md").symlink_to(secret / "private.md")
    _write(settings.watch_root / "really-mine.md", "mine", "围栏内的内容")

    titles = {item.title for item in _scan(MarkdownWatchImporter(settings.watch_root))}
    assert "mine" in titles, "围栏内的正常文件反而没导进来——那是把围栏修成了「功能没了」"
    assert "private" not in titles, (
        "**顺着文件符号链接把围栏外的内容读进来了。** "
        "root 合法不代表围栏里每个条目都合法。"
    )


def test_a_symlinked_directory_inside_the_fence_is_not_walked(settings, tmp_path):
    """**这一条不是我们的代码挡的，是 `rglob` 自己不跟着目录链接走。**

    代码里没有任何一处写着它依赖这件事——`scan` 只显式跳过了**文件**链接
    （`path.is_symlink()`），目录链接是白捡的。白捡的性质最容易在
    换实现、换运行时的时候悄悄没掉。

    两个 Python 都实测过：本机 3.13.14、生产镜像里的 3.12.13，
    目录链接后面的 .md 都不会被 rglob 看到。钉住的是这个**行为**——
    哪天它变了，这里先红，而不是等生产上把别人的目录导进档案馆才发现。
    """
    secret = tmp_path / "secret"
    secret.mkdir()
    _write(secret / "private.md", "private", "围栏外的内容")
    (settings.watch_root / "shortcut").symlink_to(secret, target_is_directory=True)
    _write(settings.watch_root / "really-mine.md", "mine", "围栏内的内容")

    titles = {item.title for item in _scan(MarkdownWatchImporter(settings.watch_root))}
    assert "mine" in titles
    assert "private" not in titles, (
        "**走进了目录符号链接。** 在 3.12 及以前这是默认行为——"
        "如果运行环境换回了那种 Python，围栏就只是个摆设。"
    )
