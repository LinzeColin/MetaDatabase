r"""部署无论怎么退出，都要把远端目录的权限复原（2026-08-14）。

## 这是两次事故的机制，而它一直还在

`DEPLOY_SNAPSHOT` 是 `mktemp -d` 建的——**权限 700**。
`rsync -a` 含 `-p`（保留权限），`--omit-dir-times` **只省时间戳、不省权限**。
于是每次部署，rsync 都会把 `/opt/social-archive` 改成 700。

复原（`chgrp socialarchive` + `chmod 750`）原来只是**后面一条顺序执行的命令**。
中间只要出一次错——rsync 部分成功后 `|| fail`、网络断、有人 Ctrl-C——
脚本就退出了，而那个目录停在 700。

后果不在开发机上，在生产上：备份和复制都以 `socialarchive` 用户跑，
700 之后连工作目录都进不去，**每次触发都是 `200/CHDIR`，直到下一次部署成功**。
实测代价：

    2026-08-11 23:53 起  replication 连着失败 108 次、28 小时
    2026-08-12～13        备份连着两天没做出快照

文档里一直写着「有人把 `/opt/social-archive` 改回 700」——**那个「有人」就是这个脚本。**

## 这道判据钉三件事

1. EXIT 的 trap 里必须叫那个复原函数（**不能只挂在正常路径上**）
2. 复原函数里真的有 `chgrp` 和 `chmod`（不是一个空壳）
3. **标志必须在 rsync 之前立**——部分传输一样会改权限，
   而 `|| fail` 那一支根本走不到 rsync 之后
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "scripts/deploy_to_production.sh"

FLAG = "REMOTE_PERMS_TOUCHED"
RESTORE = "_restore_remote_perms"


def _code() -> str:
    """剥掉注释——**说明里提到某个名字不等于代码里有它。**

    这个仓当天为同一件事栽过：判据整篇 grep，命中的是解释文字。
    """
    return "\n".join(line.split("#", 1)[0]
                     for line in DEPLOY.read_text(encoding="utf-8").splitlines())


def test_退出兜底里真的会复原权限() -> None:
    code = _code()
    traps = re.findall(r"^trap\s+(.+?)\s+EXIT\s*$", code, flags=re.M)
    assert traps, "部署脚本里没有 EXIT 的 trap——中途退出时没有任何兜底"
    assert any(RESTORE in t for t in traps), (
        f"EXIT 的 trap 里没有叫 {RESTORE}：{traps}\n"
        "  复原只挂在正常路径上的话，rsync 失败那一支会把 /opt/social-archive 留在 700，\n"
        "  此后每次备份/复制都是 200/CHDIR——**直到下一次部署成功**。")


def test_复原函数不是空壳() -> None:
    code = _code()
    body = re.search(rf"{RESTORE}\(\)\s*\{{(.*?)\n\}}", code, flags=re.S)
    assert body, f"找不到 {RESTORE} 的函数体——改名了就把这里一起改"
    text = body.group(1)
    for token in ("chgrp", "chmod", "socialarchive", "750"):
        assert token in text, f"复原函数里没有 `{token}`，它复原不了什么：\n{text}"


def test_标志在rsync之前立() -> None:
    """**顺序就是这道门的全部意义。**

    立在 rsync 之后的话，`|| fail` 那一支根本走不到——
    而那正是最需要兜底的那一支（部分传输已经把权限改掉了）。
    """
    code = _code()
    # 锚到真正那条同步到生产的 rsync。
    #
    # **第一版用「rsync 行之后 400 字符里有没有 $HOST:$REMOTE_DIR」当判据，
    # 而两条 rsync 是相邻的**——本地那条（拷 evidence 到快照）的窗口溢到了
    # 下一条上，于是锚到了错的那条，报出一个假阳。
    # 第二版改成按 `|| fail` 切——**还是假阳**：本地那条 rsync 结尾是 `|| true`，
    # 于是它的块一路切到了下一条命令上。
    # 第三版取**逻辑整行**（续行 `\` 连起来，到不带续行符的那一行为止）——
    # 那才是"一条命令"的真边界。
    lines = code.splitlines()
    hits = []
    offset = 0
    offsets = []
    for line in lines:
        offsets.append(offset)
        offset += len(line) + 1
    index = 0
    while index < len(lines):
        if lines[index].startswith("rsync "):
            chunk, cursor = "", index
            while cursor < len(lines):
                chunk += lines[cursor]
                if not lines[cursor].rstrip().endswith("\\"):
                    break
                cursor += 1
            if '"$HOST:$REMOTE_DIR/"' in chunk:
                hits.append(offsets[index])
            index = cursor + 1
            continue
        index += 1
    assert len(hits) == 1, (
        f"行首的 rsync 里，目标是 $HOST:$REMOTE_DIR 的有 {len(hits)} 条（应当正好 1 条）。"
        "命令改写了就把这里一起改——否则这道判据会对着别的东西发表意见。")
    rsync_at = hits[0]

    set_at = code.find(f"{FLAG}=1")
    assert set_at != -1, f"代码里找不到 {FLAG}=1"
    assert set_at < rsync_at, (
        f"{FLAG}=1 立在 rsync 之后（{set_at} > {rsync_at}）。\n"
        "  rsync 部分成功后 `|| fail` 会直接退出，那一支永远走不到标志那一行，\n"
        "  于是兜底不会触发——**而那正是最需要它的一次**。")
