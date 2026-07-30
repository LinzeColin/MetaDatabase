from __future__ import annotations

from pathlib import Path
from typing import Any


class PrivateDatabasePolicyError(RuntimeError):
    """Raised when retired local-working-copy persistence is requested."""


class PrivateDatabaseWriter:
    """Compatibility facade that rejects the retired local Private-Database path.

    Private-Database must be reached through its API client, never by cloning or
    mounting a writable checkout.  SA-504 owns the compliant durable-sync
    implementation; retaining this facade makes accidental legacy calls fail
    before any local data is written.
    """

    def __init__(self, root: Path):
        self.root = root.resolve()

    def write_content_bundle(self, *, content: dict[str, Any], relations: list[dict[str, Any]], artifacts: list[dict[str, Any]]) -> dict[str, Any]:
        raise PrivateDatabasePolicyError(
            "本地 Private-Database 工作树写入已禁用；请使用配置的官方 API 同步。"
        )

    def write_object_reference(self, *, digest: str, byte_size: int, media_type: str | None, replicas: list[dict[str, Any]]) -> dict[str, Any]:
        raise PrivateDatabasePolicyError(
            "本地 Private-Database 工作树写入已禁用；请使用配置的官方 API 同步。"
        )
