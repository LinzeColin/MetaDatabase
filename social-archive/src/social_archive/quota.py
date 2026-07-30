from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .db import RuntimeStore


@dataclass(frozen=True)
class QuotaDecision:
    store_id: str
    measured_bytes: int
    soft_limit_bytes: int
    hard_limit_bytes: int
    action: str
    allow_l3: bool
    message_zh: str


class QuotaGuard:
    def __init__(self, settings: Settings, store: RuntimeStore):
        self.settings = settings
        self.store = store

    @staticmethod
    def directory_size(root: Path) -> int:
        if not root.exists():
            return 0
        total = 0
        for path in root.rglob("*"):
            try:
                if path.is_file() and not path.is_symlink():
                    total += path.stat().st_size
            except FileNotFoundError:
                continue
        return total

    def evaluate_local_staging(self, incoming_bytes: int = 0) -> QuotaDecision:
        measured = self.directory_size(self.settings.staging_root)
        # R2 budget is the conservative admission budget because each staged L3 object must reach R2.
        projected = measured + max(incoming_bytes, 0)
        if not self.settings.l3_enabled:
            action, allow, message = "pause_l3", False, "L3 已由配置关闭；L0/L1 正常保存。"
        elif projected >= self.settings.r2_hard_bytes:
            action, allow, message = "pause_l3", False, "免费存储已到硬门，已暂停媒体归档；不会产生费用，L0/L1 正常保存。"
        elif projected >= self.settings.r2_soft_bytes:
            action, allow, message = "warn", True, "免费存储接近硬门；本次允许，但请先清理重复或扩展免费副本。"
        else:
            action, allow, message = "allow", True, "配额正常。"
        self.store.set_quota_state("r2-admission", measured, self.settings.r2_soft_bytes, self.settings.r2_hard_bytes, action)
        return QuotaDecision("r2-admission", measured, self.settings.r2_soft_bytes, self.settings.r2_hard_bytes, action, allow, message)
