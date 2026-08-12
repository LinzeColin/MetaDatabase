#!/usr/bin/env python3
r"""他把东西拿进 Obsidian 的那条路，在**生产上**还通吗（2026-08-11）。

## 为什么补这一道

《使用说明》第二节写着两条取法，两条的第一步都是同一颗按钮：
**资料库右上角「下载全部 Markdown」**。那颗按钮打的是 `/v1/library/markdown.zip`。

而**没有任何一步在生产上验过它**：
`tests/focused/test_he_can_take_his_markdown_away.py` 跑在本机 TestClient 上，
部署脚本里一次都没出现过 `markdown.zip`。我上一次真去点它是 0.0.0.29，
到今天已经隔了十几版——正是「47 道门全在验暂存目录，没人打开过最终那个 zip」
那条教训的形状（`never-verified-the-final-artifact-itself`）。

## 它怎么验，以及为什么不碰他的令牌

在**容器里**用它自己环境里的令牌打自己的回环口，把 zip 落在容器的临时目录里，
只回四个数和几个缺陷名。**令牌不出容器，正文一个字都不出来**：

    条目数           /v1/library 的 total
    zip 里的文件数    应该和条目数对得上
    空标题           `# ` 后面什么都没有的（我在生产上写出过 4 个）
    标题带互动数     「2.0万文案文案」那种（抖音 86 条里 31 条曾经如此）
    作者是点赞数     frontmatter 里 `author: "26.6万"` 那种

跑完删掉临时文件。**只读、只数数：不取任何内容正文、不打印令牌。**

## 它不保证什么

不保证他电脑上那个 Obsidian 库是对的——那要他双击那个 `.command`
（`test_he_can_load_the_vault_without_ssh.py` 管那一段）。
这里只回答：**那颗按钮现在按下去，拿到的那个 zip 是不是好的。**
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from social_archive.title_repair import undouble_title  # noqa: E402


def classify(text: str) -> dict:
    """一份 Markdown 有没有那几种毛病。**容器里跑的和判据测的是同一份代码。**

    容器里只有标准库，所以这个函数不许引第三方，也不许引本仓的东西——
    它的源码会被 `inspect.getsource` 取出来、原样送进 `docker exec`。
    「抓重了」那一条用的 `undouble_title` 也一样：不是 import 进来的，
    是把 `src/social_archive/title_repair.py` 整个文本一起注进去
    （那个模块只用标准库 `re`），所以**全项目仍然只有一份实现**。
    """
    import re as _re

    heading = _re.search(r"^#[ \t]?(.*)$", text, _re.M)
    title = (heading.group(1).strip() if heading else "")
    out = {"empty_heading": 0, "doubled_caption": 0,
           "starts_with_number": 0, "like_count_author": 0}
    if not title:
        out["empty_heading"] = 1
    # 「2.0万文案文案」——**真正的缺陷是"重复"，不是"以数字开头"**。
    # 第一版只判前缀，生产上量到 29 个「命中」，而「10万个冷知识」这种
    # 正当标题会被一起算进去：那是判据过宽，不是他数据的毛病。
    if _re.match(r"^\d+(?:\.\d+)?[万千亿]?", title):
        out["starts_with_number"] = 1
    # **这里原来自己写了第三套「重复」判定**（2026-08-12）。三套里两套都
    # 要求「去掉数字前缀后正好对半分成一样的两半」，而他库里那条前一遍结尾
    # 多一个空格，长度成了奇数，两半永远对不上；`[万千]` 也不含「亿」。
    # 现在统一走 `undouble_title`——同一批文本一把尺子。
    if undouble_title(title) != title:
        out["doubled_caption"] = 1
    author = _re.search(r'^author:\s*"([^"]*)"', text, _re.M)
    if author and _re.fullmatch(r"\d+(?:\.\d+)?[万千]?", author.group(1).strip()):
        out["like_count_author"] = 1
    return out


# 在容器里跑的那一段。**只回数字和缺陷计数**，不回任何正文。
INSIDE_TEMPLATE = r"""
import io, json, os, urllib.request, zipfile

__CLASSIFY__

port = os.environ.get("SOCIAL_ARCHIVE_PORT", "8765")
# **令牌是以文件给的，不是环境变量。**（L0：密钥走 /run/secrets，不进环境）
# 我第一版读 SOCIAL_ARCHIVE_API_TOKEN，容器里根本没有那个键，
# 于是 /v1/library 回 401 而我差点把它记成「生产坏了」。
token_file = os.environ.get("SOCIAL_ARCHIVE_API_TOKEN_FILE", "")
token = ""
if token_file and os.path.isfile(token_file):
    with open(token_file, encoding="utf-8") as handle:
        token = handle.read().strip()
if not token:
    token = os.environ.get("SOCIAL_ARCHIVE_API_TOKEN", "")
base = f"http://127.0.0.1:{port}"

def get(path):
    request = urllib.request.Request(base + path,
                                     headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.status, response.read()

out = {}
try:
    status, body = get("/v1/library?limit=1")
    out["library_status"] = status
    out["items_in_library"] = json.loads(body).get("total")
except Exception as error:
    out["error"] = f"读资料库失败：{type(error).__name__}"
    print(json.dumps(out, ensure_ascii=False)); raise SystemExit

try:
    status, blob = get("/v1/library/markdown.zip")
except Exception as error:
    out["error"] = f"下载 markdown.zip 失败：{type(error).__name__}"
    print(json.dumps(out, ensure_ascii=False)); raise SystemExit

out["zip_status"] = status
out["zip_bytes"] = len(blob)
archive = zipfile.ZipFile(io.BytesIO(blob))
names = [n for n in archive.namelist() if n.endswith(".md")]
out["files_in_zip"] = len(names)

totals = {"empty_heading": 0, "doubled_caption": 0,
          "starts_with_number": 0, "like_count_author": 0}
unreadable = 0
for name in names:
    try:
        text = archive.read(name).decode("utf-8")
    except Exception:
        unreadable += 1
        continue
    for key, value in classify(text).items():
        totals[key] += value

out["empty_heading"] = totals["empty_heading"]
out["title_is_a_doubled_caption"] = totals["doubled_caption"]
out["title_merely_starts_with_a_number"] = totals["starts_with_number"]
out["author_is_a_like_count"] = totals["like_count_author"]
out["unreadable_files"] = unreadable
print(json.dumps(out, ensure_ascii=False))
"""


def _inside() -> str:
    """把 classify 的源码原样塞进要送进容器的那段脚本。

    连 `title_repair` 那份模块的**文本**一起塞——它只用标准库 `re`，
    所以容器里不用装什么就能跑，而「抓重了」的判定全项目仍然只有一份实现。
    注入的是文件本身，不是抄一遍：那个模块改了，这里跟着改。
    """
    import inspect
    shared = (ROOT / "src/social_archive/title_repair.py").read_text(encoding="utf-8")
    # **`from __future__ import annotations` 必须在文件最前面。** 这段是塞进
    # 模板中间的，带着它整段编译不过（`SyntaxError`），送进容器就是当场崩。
    # 容器跑 3.13，`str | None` 本来就原生成立，去掉它没有副作用。
    shared = "\n".join(line for line in shared.splitlines()
                       if not line.startswith("from __future__ import"))
    return (INSIDE_TEMPLATE
            .replace("__CLASSIFY__", shared + "\n\n" + inspect.getsource(classify)))



def main() -> int:
    parser = argparse.ArgumentParser(description="生产上「下载全部 Markdown」还通吗")
    parser.add_argument("--host", default=None)
    parser.add_argument("--container", default="social-archive-core-api-1")
    args = parser.parse_args()
    host = args.host or (ROOT / "deploy/PRODUCTION_HOST").read_text(encoding="utf-8").strip()

    done = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=20", host,
         f"sudo docker exec -i {args.container} python -"],
        input=_inside(), capture_output=True, text=True, check=False)
    raw = done.stdout.strip().splitlines()
    payload = None
    for line in reversed(raw):
        try:
            payload = json.loads(line)
            break
        except ValueError:
            continue
    if payload is None:
        print(json.dumps({"status": "FAIL", "error_code": "NO_JSON_FROM_CONTAINER",
                          "detail": (done.stdout + done.stderr)[-400:]},
                         ensure_ascii=False, indent=2))
        return 2

    problems: list[str] = []
    if payload.get("error"):
        problems.append(payload["error"])
    if payload.get("zip_status") != 200:
        problems.append(f"「下载全部 Markdown」不是 200，而是 {payload.get('zip_status')}"
                        "——他点那颗按钮会拿不到东西")
    items = payload.get("items_in_library")
    files = payload.get("files_in_zip")
    if isinstance(items, int) and isinstance(files, int) and items and files != items:
        problems.append(f"库里 {items} 条，zip 里只有 {files} 个文件——差 {items - files} 条")
    if not files:
        problems.append("zip 里一个 .md 都没有")
    for key, why in (
        ("empty_heading", "标题是空的（我在生产上写出过 4 个）"),
        ("title_is_a_doubled_caption", "标题是「互动数＋文案＋同一段文案」那种（后半截和前半截重复）"),
        ("author_is_a_like_count", "作者字段装的是点赞数（他那条写着 26.6万）"),
        ("unreadable_files", "读不出来的文件（编码坏了）"),
    ):
        count = payload.get(key) or 0
        if count:
            problems.append(f"{count} 个文件{why}")

    print(json.dumps({
        "status": "FAIL" if problems else "PASS",
        "host": host,
        "measured": payload,
        "problems": problems,
        "boundary_zh": "只读、只数数：不取任何内容正文，不打印令牌（令牌不出容器）。",
        "what_this_does_not_prove":
            "不保证他电脑上那个 Obsidian 库是对的——那要他双击那个 .command；"
            "这里只回答「那颗按钮现在按下去，拿到的 zip 是不是好的」。",
    }, ensure_ascii=False, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
