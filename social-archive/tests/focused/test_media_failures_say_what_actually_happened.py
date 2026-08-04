"""原始媒体没取到时，说的话要对（v0.0.0.7 / INV-NO-SILENT-ZERO）。

2026-08-04 生产实测：193 条内容里 34 条没有 L3 原文件，对应 33 个失败任务
（抖音 32、B站 1）。它们给用户看到的是

    JOB_FAILED  L3 下载未产生对象；WARNING: [Douyin] 7669577378074578239:
                Failed to parse JSON: Expecting va…

三处都不对：**码是通用的**、**正文是截断的英文工具输出**、**没有下一步**。

而真相说得清：抖音返回的东西 yt-dlp 解不了，B站回 HTTP 412 风控。
我们**不绕**（L0 边界），国内平台的 Cookie 又按 INV-DOMESTIC-COOKIE-STAYS
一步都不离开浏览器——服务端**结构上**就拿不到，重试多少次都一样。
"""

import pytest

from social_archive.worker import MediaUnavailable


@pytest.mark.parametrize("detail,expected", [
    ("WARNING: [Douyin] 7669577378074578239: Failed to parse JSON: Expecting value",
     "MEDIA_BLOCKED_BY_PLATFORM"),
    ("ERROR: [BiliBili] 1Xx411c7cH: Unable to download webpage: HTTP Error 412: Precondition Failed",
     "MEDIA_BLOCKED_BY_PLATFORM"),
    ("HTTP Error 403: Forbidden", "MEDIA_BLOCKED_BY_PLATFORM"),
    ("HTTP Error 429: Too Many Requests", "MEDIA_TEMPORARILY_UNAVAILABLE"),
    ("Read timed out", "MEDIA_TEMPORARILY_UNAVAILABLE"),
    ("something else entirely", "MEDIA_NOT_RETRIEVED"),
])
def test_the_code_matches_what_actually_happened(detail: str, expected: str) -> None:
    exc = MediaUnavailable([detail])
    assert exc.failure_code == expected


def test_a_structural_block_is_not_retryable() -> None:
    """平台挡住服务器这件事，重试多少次都一样。"""
    assert MediaUnavailable(["Failed to parse JSON"]).retryable is False
    assert MediaUnavailable(["HTTP Error 412"]).retryable is False
    assert MediaUnavailable(["HTTP Error 429"]).retryable is True


def test_every_new_code_has_a_chinese_sentence() -> None:
    from social_archive.failure_copy import describe_sync_outcome

    for code in ("MEDIA_BLOCKED_BY_PLATFORM", "MEDIA_NOT_RETRIEVED", "MEDIA_TEMPORARILY_UNAVAILABLE"):
        out = describe_sync_outcome(imported=0, failure_code=code, platform_label="抖音")
        assert out["message_zh"], f"{code} 说不出人话"
        assert "JOB_FAILED" not in out["message_zh"]


def test_the_worker_uses_the_exceptions_own_code_not_a_blanket_one() -> None:
    import inspect

    from social_archive import worker

    source = inspect.getsource(worker._finish_failed_job)
    code = "\n".join(l for l in source.splitlines() if not l.lstrip().startswith("#"))
    assert 'getattr(exc, "failure_code", None)' in code, "还是一律 JOB_FAILED"
    assert code.index('getattr(exc, "failure_code"') < code.index("store.finish_job")
