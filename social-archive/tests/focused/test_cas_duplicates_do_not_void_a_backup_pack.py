"""内容寻址下的重复路径不是损坏（v0.0.0.7 / T16 / INV-REVERSIBLE）。

2026-08-04 实测：对一个三份副本全 `verified` 的制品做取回演练，

    r2      PASS
    oci     PASS
    github  **FAIL — GITHUB_PACK_INVALID「对象路径非法或重复」**

查下去：那个包 500 个对象里有 **3 组**路径重复。而路径是
`objects/{原文 sha256}.age`——**两个制品只要字节相同，就必然指向同一条路径**。
清单里保留两条记录是对的：它记的是「哪个 artifact 对应哪个对象」，多对一是
这套设计的正常结果。

原来一见重复就整包判废，于是**整包 500 个对象一个都恢复不了**。
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("_restore_object", ROOT / "scripts/restore_object.py")
restore_object = importlib.util.module_from_spec(_spec)
sys.modules["_restore_object"] = restore_object
_spec.loader.exec_module(restore_object)


def _source() -> str:
    return "\n".join(
        line for line in (ROOT / "scripts/restore_object.py").read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )


def test_a_repeated_path_is_no_longer_an_automatic_failure() -> None:
    code = _source()
    assert 'if path != expected_path or path in expected_members:' not in code, (
        "还是一见重复就整包判废——内容寻址下重复是正常的"
    )
    assert "previous = expected_members.get(path)" in code, "没有区分「同一份」和「两份不同的」"


def test_the_same_path_with_different_ciphertext_still_fails() -> None:
    """放宽的只是「同一份内容出现两次」。同一路径挂两份不同的密文，仍然是坏了。"""
    code = _source()
    block = code.split("previous = expected_members.get(path)", 1)[1][:700]
    assert 'previous.get("cipher_sha256") != cipher' in block, "没有比对密文哈希"
    assert "GITHUB_PACK_INVALID" in block, "两份不同的内容没有判废"


def test_the_check_still_pins_the_path_to_the_content_hash() -> None:
    """路径必须仍然等于 objects/{原文 sha256}.age——这条不能一起放宽。"""
    code = _source()
    assert 'expected_path = f"objects/{original}.age"' in code
    assert "if path != expected_path:" in code
