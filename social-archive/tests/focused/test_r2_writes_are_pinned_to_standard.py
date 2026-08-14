"""往 R2 写对象必须显式钉 Standard 存储类（2026-08-10）。

## 为什么这条不能丢

Owner 的铁律 7 写得最重的一条：

    **禁止 `InfrequentAccess` 存储类**（建桶 / 写对象 / 生命周期转换一律不许）：
    R2 免费额度只覆盖 Standard，IA 从第 1 次操作起计费且**按整单位向上取整**——
    实账单 **51 次 IA 操作 = $9.00**，同周期 301 万次 Standard 操作 = $0.00。

`origin/main` 上 2026-08-09 的 `a0e201baa fix(r2): pin active writers to Standard`
已经把两个写入点钉住了。**而这一支（比 main 多 550 个提交）没有那次改动**——
它会在合并那天把 main 的这道保护顶掉，而且是**静悄悄地**顶掉：
R2 今天的默认就是 Standard，不钉也不会立刻出账单，
所以出问题的时刻不是合并那天，是以后某天默认变了 / 某个客户端换了默认值。

## 生产上这条真的会生效吗——量过

    SOCIAL_ARCHIVE_OCI_S3_COMPATIBILITY=oci      ← 只有 OCI 显式设了
    R2 没有设 → 取默认的 "aws" → **这条钉子作用在 R2 的写入上**

OCI 那一侧不钉是对的：它不认 AWS 的存储类名字，钉了会被拒。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

from social_archive.storage import S3ReplicaStore


class _Client:
    def __init__(self) -> None:
        self.extra: dict = {}

    def upload_file(self, filename, bucket, key, ExtraArgs):   # noqa: N803
        self.extra = dict(ExtraArgs)
        self.metadata = ExtraArgs["Metadata"]

    def head_object(self, Bucket, Key):                        # noqa: N803
        return {"Metadata": self.metadata, "ETag": '"etag"'}


def _store(tmp_path: Path, compatibility: str) -> tuple[S3ReplicaStore, _Client, object]:
    cipher = tmp_path / "object.age"
    cipher.write_bytes(b"cipher")
    # 形状照抄 tests/focused/test_s3_replication.py 里那个——**别自己发明一个**。
    obj = SimpleNamespace(
        original_sha256="b" * 64,
        cipher_sha256=hashlib.sha256(b"cipher").hexdigest(),
        original_byte_size=4, cipher_byte_size=6, path=cipher,
        media_type="application/octet-stream", algorithm="age-x25519")
    store = object.__new__(S3ReplicaStore)
    store.store_id = "r2"
    store.bucket = "fixture"
    store.prefix = "primary-objects"
    store.s3_compatibility = compatibility
    client = _Client()
    store.client = client
    return store, client, obj


def test_an_aws_compatible_write_pins_standard(tmp_path: Path) -> None:
    """**R2 走的就是这一档**（生产上它没设 S3_COMPATIBILITY，取默认 aws）。"""
    store, client, obj = _store(tmp_path, "aws")
    store.put_encrypted(obj)
    assert client.extra.get("StorageClass") == "STANDARD", (
        f"往 R2 写对象没有钉 Standard：{client.extra}——"
        "铁律 7：IA 从第 1 次操作起计费且按整单位向上取整，实账单 51 次 = $9.00")


def test_the_oci_write_does_not_pin_it(tmp_path: Path) -> None:
    """**别把 OCI 也钉上。** 它不认 AWS 的存储类名字，钉了会被拒。"""
    store, client, obj = _store(tmp_path, "oci")
    store.put_encrypted(obj)
    assert "StorageClass" not in client.extra, (
        f"给 OCI 也钉了存储类：{client.extra}——它不认这个名字，会被拒")


def test_the_metadata_still_goes_along(tmp_path: Path) -> None:
    """**正例**：钉存储类不能把原来的 Metadata 挤掉（挤掉了回读校验会炸）。"""
    store, client, obj = _store(tmp_path, "aws")
    store.put_encrypted(obj)
    assert (client.extra.get("Metadata") or {}).get("encryption") == "age-x25519", client.extra


def test_the_backup_script_pins_it_too(tmp_path: Path) -> None:
    """两个写入点，不是一个：`scripts/backup.py` 那条路也要钉。"""
    import importlib.util
    import sys

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("_backup_mod", root / "scripts/backup.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_backup_mod"] = module
    spec.loader.exec_module(module)
    assert hasattr(module, "_upload_args"), (
        "backup.py 里没有统一的上传参数构造——两个上传点会各写各的，"
        "而漏掉的那个不会有人发现")
    aws = module._upload_args({"s3_compatibility": "aws"}, {"k": "v"})
    oci = module._upload_args({"s3_compatibility": "oci"}, {"k": "v"})
    assert aws.get("StorageClass") == "STANDARD", aws
    assert "StorageClass" not in oci, oci
    assert aws.get("Metadata") == {"k": "v"} and oci.get("Metadata") == {"k": "v"}
