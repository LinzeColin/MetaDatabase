from __future__ import annotations

import importlib
import json
import time
from pathlib import Path

from fastapi.testclient import TestClient



def test_pairing_requires_long_term_api_token_for_request_serving_core_only(tmp_path, monkeypatch):
    from social_archive.config import Settings
    data = tmp_path / "data"
    monkeypatch.setenv("SOCIAL_ARCHIVE_DATA_ROOT", str(data))
    monkeypatch.setenv("SOCIAL_ARCHIVE_RUNTIME_DB", str(data / "db.sqlite"))
    # 注意：PAIRING_REQUIRED 名字里带 pairing，但它是**总鉴权开关**，
    # 不是配对码开关。配对码链路已随 v0.0.0.7 / T03 删除，这个开关必须留着——
    # 删掉它 require_token 会第一行早退，全站不再鉴权。
    monkeypatch.setenv("SOCIAL_ARCHIVE_PAIRING_REQUIRED", "true")
    monkeypatch.delenv("SOCIAL_ARCHIVE_API_TOKEN_FILE", raising=False)
    settings = Settings.from_env()
    settings.ensure_directories()
    try:
        settings.ensure_directories(require_api_token=True)
    except RuntimeError as exc:
        assert "长期 API Token" in str(exc)
    else:
        raise AssertionError("pairing protection must require a long-term API token")


def test_secret_writer_preserves_existing_mode(tmp_path):
    """v0.0.0.7 / T03：判据从 generate_pairing_code.py 搬到 ensure_api_token.py。

    删配对码脚本时差点把这段一起删掉——那个脚本干了两件事，
    第二件（幂等创建长期 API 令牌）**还要**，且里面这条约束是生产上踩出来的：
    生产机的 secret 属于非 root 的 10001:10001（0640），以 root 刷新时不显式保留
    权限位就会重建成 root-only，Core 再也读不到自己的令牌。
    """
    import importlib.util

    script = Path(__file__).parents[2] / "scripts/ensure_api_token.py"
    spec = importlib.util.spec_from_file_location("ensure_api_token", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    secret = tmp_path / "api-token"
    secret.write_text("previous\n", encoding="utf-8")
    secret.chmod(0o640)

    module.atomic_secret(secret, "replacement")

    assert secret.read_text(encoding="utf-8") == "replacement\n"
    assert secret.stat().st_mode & 0o777 == 0o640


def test_api_token_provisioning_is_idempotent(tmp_path):
    """重新生成会把所有已连接的设备踢下线，所以已有非空令牌必须原样不动。"""
    import subprocess

    script = Path(__file__).parents[2] / "scripts/ensure_api_token.py"
    token_file = tmp_path / "api-token"
    subprocess.run(["python3", str(script), "--token-file", str(token_file)], check=True)
    first = token_file.read_text(encoding="utf-8")
    assert first.strip()
    subprocess.run(["python3", str(script), "--token-file", str(token_file)], check=True)
    assert token_file.read_text(encoding="utf-8") == first


# v0.0.0.7 / T03：`test_generated_pairing_code_is_human_readable` 与
# `test_pairing_generator_rejects_more_than_ten_minutes` 已删——它们测的是
# 一次性配对码的字母表和 10 分钟上限，而整条链路已被实测证伪并移除
# （连续失败三次；手抄字符本身违反 INV-ZERO-BARRIER）。
# 反向守卫见 tests/focused/test_superseded_paths_stay_removed.py。


def test_library_cloudflare_access_identity_is_host_scoped(tmp_path, monkeypatch):
    data = tmp_path / "data-access"
    pwa = tmp_path / "pwa-access"
    pwa.mkdir()
    (pwa / "index.html").write_text("ok", encoding="utf-8")
    token = tmp_path / "token-access"
    token.write_text("device-token\n", encoding="utf-8")
    token.chmod(0o600)
    monkeypatch.setenv("SOCIAL_ARCHIVE_DATA_ROOT", str(data))
    monkeypatch.setenv("SOCIAL_ARCHIVE_RUNTIME_DB", str(data / "db.sqlite"))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PWA_ROOT", str(pwa))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PAIRING_REQUIRED", "true")
    monkeypatch.setenv("SOCIAL_ARCHIVE_API_TOKEN_FILE", str(token))
    monkeypatch.setenv("SOCIAL_ARCHIVE_PUBLIC_BASE_URL", "https://social-archive-api.linzezhang.com")
    monkeypatch.setenv("SOCIAL_ARCHIVE_PUBLIC_LIBRARY_URL", "https://social-archive.linzezhang.com")
    import social_archive.api as api
    importlib.reload(api)
    client = TestClient(api.app)
    assertion = "a" * 128
    allowed = client.get("/v1/library", headers={"Host": "social-archive.linzezhang.com", "Cf-Access-Jwt-Assertion": assertion})
    assert allowed.status_code == 200
    denied = client.get("/v1/library", headers={"Host": "social-archive-api.linzezhang.com", "Cf-Access-Jwt-Assertion": assertion})
    assert denied.status_code == 401
    spoofed_forwarded_host = client.get(
        "/v1/library",
        headers={
            "Host": "social-archive-api.linzezhang.com",
            "X-Forwarded-Host": "social-archive.linzezhang.com",
            "Cf-Access-Jwt-Assertion": assertion,
        },
    )
    assert spoofed_forwarded_host.status_code == 401


