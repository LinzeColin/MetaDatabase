"""Shell 里裸 $var 紧跟多字节字符 = 脚本静默炸掉（v0.0.0.7）。

## 这条判据是从一个真实缺陷里长出来的

`scripts/start_readers.sh` 第 14 行本来是：

    echo "缺少 runtime/secrets/${secret}；请先运行 ..."

花括号被去掉之后变成 `$secret；`。bash 解析变量名时会把紧跟其后的字节
一起吞进去——全角分号「；」是 UTF-8 的 `EF BC 9B`，于是变量名成了
`secret\xef...`，脚本以 `unbound variable` 直接退出（set -u 下）。

**表现有多隐蔽**：`bash -n` 语法检查通过；文件本身是合法 UTF-8；
只有真的跑起来才炸，而且报错信息本身带着半个字符，
Python 用 text=True 读它还会再抛一个 UnicodeDecodeError 把真相盖住。
本仓的 3 条判据就是被这个连环遮蔽卡住的。

**花括号在这里是承重的**，不是风格。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 裸 $名字 紧跟一个非 ASCII 字节（即多字节字符的首字节）
BARE_THEN_MULTIBYTE = re.compile(rb"\$[A-Za-z_][A-Za-z0-9_]*[\x80-\xff]")


def _shell_files() -> list[Path]:
    return [
        p for p in ROOT.rglob("*.sh")
        if not any(part in {".venv", "node_modules", ".git"} for part in p.parts)
    ]


def test_no_bare_variable_is_glued_to_a_multibyte_character() -> None:
    files = _shell_files()
    assert files, "一个 .sh 都没扫到——判据在空转"
    offenders = []
    for path in files:
        raw = path.read_bytes()
        for match in BARE_THEN_MULTIBYTE.finditer(raw):
            line_no = raw[: match.start()].count(b"\n") + 1
            offenders.append(f"{path.relative_to(ROOT)}:{line_no} {match.group(0)!r}")
    assert not offenders, (
        "这些地方裸用了 $var 且紧跟多字节字符，bash 会把它们吞进变量名，"
        f"脚本会以 unbound variable 退出：{offenders}。改成 ${{var}}。"
    )


def test_the_guard_actually_catches_the_shape(tmp_path: Path) -> None:
    """先证明它抓得到——扫到 0 处和「没问题」长得一样。"""
    bad = tmp_path / "bad.sh"
    bad.write_bytes('echo "路径 $secret；请重试"\n'.encode("utf-8"))
    assert BARE_THEN_MULTIBYTE.search(bad.read_bytes()), "判据抓不到那个形状"
    good = tmp_path / "good.sh"
    good.write_bytes('echo "路径 ${secret}；请重试"\n'.encode("utf-8"))
    assert not BARE_THEN_MULTIBYTE.search(good.read_bytes()), "加了花括号还报红，判据太宽"


def test_every_shell_script_is_valid_utf8_and_parses() -> None:
    """顺带把另外两层遮蔽也钉住：文件编码、以及 bash -n。

    这两层都过、脚本仍然炸——正是上面那个缺陷的形状。三层齐了才说得上有覆盖。
    """
    import subprocess

    for path in _shell_files():
        raw = path.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:  # pragma: no cover
            raise AssertionError(f"{path.relative_to(ROOT)} 不是合法 UTF-8：{exc}") from exc
        completed = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True, check=False)
        assert completed.returncode == 0, (
            f"{path.relative_to(ROOT)} 语法错误：{completed.stderr.strip()[:200]}"
        )
