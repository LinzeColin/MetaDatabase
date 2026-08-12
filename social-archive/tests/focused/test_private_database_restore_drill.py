"""守住 Private-Database 那条链的取回演练（v0.0.0.7 / INV-REVERSIBLE）。

## 它为什么存在

2026-08-05 把「备份 timer 自主触发过」验完之后，我在证据里写下一句自认的缺口：
那 100 条 fact 的副本**仍然只有它自己的回执作证**。去看才发现缺口更实在：
`scripts/` 下只有 `sync_private_database.py`（写的那一半），
**没有任何东西把它写出去的东西读回来**——建好了没接上。

## 这个演练自己犯过的错，正是它最该守住的那一类

第一版按「一个 fact 一个文件」去数，跑出 `restored_count: 2`（而不是 100）。
**差一点就当成「远端那份少了 98 条」报出去。** 去看包里到底是什么：

    facts.ndjson   —— 100 条，一行一个 JSON
    snapshot.json  —— 清单副本

包一点问题都没有，是**我对它的结构猜错了**。指错原因比不报更糟：
那一条要是发出去，下一个人会去查一个根本没坏的备份链。
"""

import hashlib
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRILL_PATH = ROOT / "scripts/restore_private_database_drill.py"
DRILL_SOURCE = DRILL_PATH.read_text(encoding="utf-8")

sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
_spec = importlib.util.spec_from_file_location("_restore_private_database_drill", DRILL_PATH)
_drill = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_drill)


def _write_facts(tmp_path: Path, lines: list[bytes], trailing_newline: bool = True) -> Path:
    body = b"\n".join(lines) + (b"\n" if trailing_newline else b"")
    (tmp_path / "facts.ndjson").write_bytes(body)
    (tmp_path / "snapshot.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_it_hashes_lines_not_files(tmp_path) -> None:
    """**这就是第一版栽的地方。**

    包里只有两个文件；fact 是 facts.ndjson 里的行。按文件数会数出 2，
    而 manifest 说 100——那不是数据少了，是数法错了。
    """
    lines = [b'{"a":1}', b'{"b":2}', b'{"c":3}']
    variants = _drill._hash_variants(_write_facts(tmp_path, lines))
    for digests in variants.values():
        assert len(digests) == len(lines), f"数出来 {len(digests)} 条，而文件里有 {len(lines)} 行"


def test_it_offers_both_line_ending_conventions(tmp_path) -> None:
    """行尾算不算进哈希**不猜**——两种都算，让调用方挑对得上的那一种。

    生产那份实测是 `line_with_newline`。猜错的那一半会让 100 条全部对不上，
    而现象和「远端整个坏了」一模一样。
    """
    lines = [b'{"a":1}', b'{"b":2}']
    variants = _drill._hash_variants(_write_facts(tmp_path, lines))
    assert set(variants) == {"line_without_newline", "line_with_newline"}
    assert variants["line_with_newline"] == sorted(
        hashlib.sha256(line + b"\n").hexdigest() for line in lines)
    assert variants["line_without_newline"] == sorted(
        hashlib.sha256(line).hexdigest() for line in lines)
    assert variants["line_with_newline"] != variants["line_without_newline"], (
        "两种口径算出来一样，那这个选择就是假的"
    )


def test_a_blank_trailing_line_does_not_become_a_fact(tmp_path) -> None:
    """ndjson 末尾那个换行不该被数成第 101 条。"""
    lines = [b'{"a":1}', b'{"b":2}']
    variants = _drill._hash_variants(_write_facts(tmp_path, lines, trailing_newline=True))
    assert all(len(digests) == 2 for digests in variants.values())


def test_a_missing_facts_file_is_reported_not_treated_as_zero(tmp_path) -> None:
    """**「一条都没有」和「文件不在」是两件事。**

    返回空字典让调用方去报 FACTS_FILE_MISSING；要是这里返回「0 条」，
    上层会拿它去和 100 比，报成「少了 100 条」——又是指错原因。
    """
    (tmp_path / "snapshot.json").write_text("{}", encoding="utf-8")
    assert _drill._hash_variants(tmp_path) == {}
    assert "FACTS_FILE_MISSING" in DRILL_SOURCE, "上层没有为「文件不在」单列一个码"


def test_it_refuses_to_restore_into_the_running_data_plane() -> None:
    """恢复演练最坏的失手是盖在生产数据上。

    实测过：第一次把 --target 指向 /var/lib/social-archive/drills，
    脚本当场拒绝，理由是「恢复目标不能落入运行数据面」。那个拒绝是对的。
    """
    assert "RECOVERY_TARGET_INVALID" in DRILL_SOURCE
    assert "settings.data_root" in DRILL_SOURCE and "guard in target.parents" in DRILL_SOURCE, (
        "没有真去比目标路径在不在数据面下"
    )


def test_it_requires_per_fact_hashes_in_the_manifest() -> None:
    """没有逐条哈希时必须拒绝，**不能拿「整包哈希对上了」冒充「100 条都在」**。"""
    assert "MANIFEST_HAS_NO_FACT_HASHES" in DRILL_SOURCE


def test_it_only_reads_copies_the_manifest_calls_verified() -> None:
    assert "COPY_NOT_VERIFIED" in DRILL_SOURCE


def test_it_never_echoes_age_stderr() -> None:
    """解密失败的输出里可能带密钥材料的片段，绝不回显。"""
    code = "\n".join(line for line in DRILL_SOURCE.splitlines()
                     if not line.strip().startswith("#"))
    assert "AGE_DECRYPT_FAILED" in code
    assert "completed.stderr" not in code and "stderr=" not in code, (
        "把 age 的 stderr 带进了输出"
    )


def test_it_extracts_with_the_safe_filter() -> None:
    """取回来的包必须只能落在 --target 里面：绝对路径、`..`、设备文件一律拒绝。"""
    assert 'filter="data"' in DRILL_SOURCE, "tar 解包没有用安全过滤器"


def test_it_never_touches_production_paths() -> None:
    for forbidden in ("linze-ovh", "social-archive.linzezhang.com"):
        assert forbidden not in DRILL_SOURCE, f"演练里出现了生产的东西：{forbidden}"
