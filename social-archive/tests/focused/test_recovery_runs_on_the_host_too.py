"""恢复要在**出事那天**跑得起来（v0.0.0.7 / T16 / T17）。

2026-08-05 实测：在主机上直接跑恢复脚本，连着撞两堵墙——

    OBJECT_STORE_CONFIG_MISSING   读不到 R2 的两个键
    AGE_IDENTITY_MISSING          读不到 age 私钥

根因是 `.env` 里那几个 *_FILE 指的是 /run/secrets/…，**那是容器里的挂载点**，
主机上根本不存在；而主机上这些密钥就在 runtime/secrets/ 下，只是路径不同。

**恢复是出事那天才跑的东西。** 那一天再去现场发现「配置指向一个不存在的路径」，
是最坏的时机。所以恢复路径上加了一条边界卡死的兜底，并且**用过就报出来**。
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def restore_module():
    spec = importlib.util.spec_from_file_location(
        "restore_object_probe", ROOT / "scripts/restore_object.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._SECRET_FALLBACKS.clear()
    return module


def test_a_path_that_exists_is_used_as_is(restore_module, tmp_path) -> None:
    real = tmp_path / "r2_access_key_id"
    real.write_text("x", encoding="utf-8")
    assert restore_module._resolve_secret_path(str(real)) == str(real)
    assert restore_module._SECRET_FALLBACKS == [], "没兜底也记了一笔，报告会误导人"


def test_a_container_only_path_falls_back_to_the_host_copy(restore_module, tmp_path, monkeypatch) -> None:
    """这正是生产上的形状：配置指着 /run/secrets/…，主机上只有 runtime/secrets/…"""
    host_secrets = tmp_path / "runtime/secrets"
    host_secrets.mkdir(parents=True)
    (host_secrets / "r2_access_key_id").write_text("x", encoding="utf-8")
    monkeypatch.setattr(restore_module, "_SECRET_FALLBACK_DIR", host_secrets)
    resolved = restore_module._resolve_secret_path("/run/secrets/r2_access_key_id")
    assert resolved == str(host_secrets / "r2_access_key_id")
    assert restore_module._SECRET_FALLBACKS, (
        "**静默兜底比不兜底更坏**——它会让人以为配置本来就是对的，"
        "下一台机器上照抄配置又撞同一堵墙"
    )


def test_it_fails_closed_when_neither_place_has_it(restore_module, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(restore_module, "_SECRET_FALLBACK_DIR", tmp_path / "nowhere")
    assert restore_module._resolve_secret_path("/run/secrets/nope") == "/run/secrets/nope"
    assert restore_module._SECRET_FALLBACKS == []


def test_the_fallback_never_guesses_another_name(restore_module, tmp_path, monkeypatch) -> None:
    """只找同名文件、只在这一个目录里找。

    密钥这种东西，「找个像的顶上」是最坏的行为——它会把一份错的凭据
    当成对的用下去，而错误要到很久以后才显形。
    """
    host_secrets = tmp_path / "secrets"
    host_secrets.mkdir()
    (host_secrets / "r2_secret_access_key").write_text("x", encoding="utf-8")
    monkeypatch.setattr(restore_module, "_SECRET_FALLBACK_DIR", host_secrets)
    # 要的是 access_key_id，目录里只有 secret_access_key——绝不能拿它顶上
    assert restore_module._resolve_secret_path("/run/secrets/r2_access_key_id") == \
        "/run/secrets/r2_access_key_id"
    assert restore_module._SECRET_FALLBACKS == []


def test_both_outcomes_report_the_fallbacks() -> None:
    """成功和失败两条路都要把兜底列出来——失败那条尤其要，
    因为「读不到密钥」时最想知道的就是它到底去哪儿找过。"""
    source = (ROOT / "scripts/restore_object.py").read_text(encoding="utf-8")
    assert source.count('"secret_path_fallbacks"') >= 2, "只有一条路报了兜底"


TRACE = (ROOT / "scripts/golden_transaction_trace.py").read_text(encoding="utf-8")


def test_the_trace_compares_the_right_hash() -> None:
    """副本上有两个哈希，拿错了会把好数据报成坏的。

    实测：original_sha256 是明文（制品本身）的哈希，必须等于 artifact.sha256；
    verified_sha256 是上传上去那个**密文**的哈希，与明文不同是正常的。
    第一版拿 verified_sha256 去比，六条副本全报「对不上」——而数据是好的。
    """
    assert "replica[\"original_sha256\"] != artifact[\"sha256\"]" in TRACE, \
        "又拿密文哈希去比制品了"
    assert "三份副本存的不是同一份字节" in TRACE, \
        "没有守「三个仓存的是同一份密文」——那是三副本真正的意思"


def test_the_trace_uses_the_real_receipt_vocabulary() -> None:
    """生产实测词表只有 done / failed 两个。第一版按 delivered 判，
    于是一条投递成功的记录被报成失败。"""
    assert 'r["status"] == "done"' in TRACE, "成功态又写成别的词了"
    assert '"delivered"' not in TRACE, "delivered 这个词在这个库里不存在"


def test_the_trace_actually_fetches_bytes_back() -> None:
    """前面几站都是读数据库自述，只有取回那一站是真的把字节拿回来。"""
    assert "restore_object.py" in TRACE, "根本没去远端取"
    assert "--skip-restore" in TRACE, "没有留下「只读几站」的开关，排查时只能改代码"
    assert "取得那一站" in TRACE, (
        "没有说清它不覆盖什么——这条追踪证明的是取得之后的每一站，"
        "取得本身还缺，那正是 T17 剩下的一环"
    )
